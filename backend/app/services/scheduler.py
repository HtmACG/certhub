"""
后台调度器
==========
- 定时触发流水线（cron 表达式，5 段）
- 站点证书监控
- 证书到期提醒
"""
from __future__ import annotations

import datetime as dt
import json
import socket
import ssl
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..db import SessionLocal
from ..models import Certificate, Notification, Pipeline, SiteMonitor
from ..security import decrypt_json
from . import notify
from .engine import is_running, run_pipeline_async

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
_lock = threading.Lock()


# ---------------------------------------------------------------- cron

def parse_cron(expr: str) -> CronTrigger:
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("cron 表达式为空")
    parts = expr.split()
    if len(parts) == 6:  # 兼容秒级表达式，忽略秒
        parts = parts[1:]
    if len(parts) != 5:
        raise ValueError("cron 表达式需要 5 段，例如 0 3 * * *")
    return CronTrigger(minute=parts[0], hour=parts[1], day=parts[2],
                       month=parts[3], day_of_week=parts[4])


def next_run(expr: str, base: dt.datetime | None = None) -> dt.datetime | None:
    try:
        trigger = parse_cron(expr)
        base = base or dt.datetime.now()
        return trigger.get_next_fire_time(None, base)
    except Exception:
        return None


def _pipeline_triggers(content: dict) -> list[dict]:
    return [t for t in (content.get("triggers") or [])
            if t.get("type") == "timer" and t.get("enabled", True) and t.get("cron")]


# ---------------------------------------------------------------- 定时流水线

def refresh_next_run_times():
    db = SessionLocal()
    try:
        for p in db.query(Pipeline).filter(Pipeline.disabled.is_(False)).all():
            try:
                content = json.loads(p.content or "{}")
            except Exception:
                continue
            triggers = _pipeline_triggers(content)
            if not triggers:
                p.next_run_time = None
                continue
            times = [t for t in (next_run(tr["cron"]) for tr in triggers) if t]
            p.next_run_time = min(times) if times else None
        db.commit()
    finally:
        db.close()


def tick_pipelines():
    if not _lock.acquire(blocking=False):
        return
    try:
        db = SessionLocal()
        due: list[int] = []
        try:
            now = dt.datetime.now()
            for p in db.query(Pipeline).filter(Pipeline.disabled.is_(False)).all():
                try:
                    content = json.loads(p.content or "{}")
                except Exception:
                    continue
                triggers = _pipeline_triggers(content)
                if not triggers:
                    continue
                if p.next_run_time is None:
                    times = [t for t in (next_run(tr["cron"]) for tr in triggers) if t]
                    p.next_run_time = min(times) if times else None
                    db.commit()
                    continue
                if p.next_run_time <= now and not is_running(p.id):
                    due.append(p.id)
                    times = [t for t in (next_run(tr["cron"], now) for tr in triggers) if t]
                    p.next_run_time = min(times) if times else None
            db.commit()
        finally:
            db.close()
        for pid in due:
            try:
                run_pipeline_async(pid, "timer")
            except Exception:
                pass
    finally:
        _lock.release()


# ---------------------------------------------------------------- 站点监控

def check_site(url: str, port: int = 443) -> dict:
    host = url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            der = ssock.getpeercert(binary_form=True)
    from cryptography import x509

    from .certutil import to_local

    cert = x509.load_der_x509_certificate(der)
    not_after = to_local(cert.not_valid_after_utc)
    try:
        issuer = cert.issuer.get_attributes_for_oid(
            x509.oid.NameOID.ORGANIZATION_NAME)[0].value
    except Exception:
        issuer = cert.issuer.rfc4514_string()
    return {
        "not_before": to_local(cert.not_valid_before_utc),
        "not_after": not_after,
        "issuer": issuer,
        "days_left": (not_after - dt.datetime.now()).days,
    }


def tick_sites():
    db = SessionLocal()
    try:
        sites = db.query(SiteMonitor).filter(SiteMonitor.enabled.is_(True)).all()
        for site in sites:
            try:
                info = check_site(site.url, site.port or 443)
                site.status = "ok"
                site.error = ""
                site.issuer = info["issuer"]
                site.not_before = info["not_before"]
                site.expire_time = info["not_after"]
                site.last_check_time = dt.datetime.now()
                if info["days_left"] <= 15 and site.notify_enabled:
                    _notify_user(site.user_id, "站点证书即将到期",
                                 f"站点 <b>{site.url}</b> 证书将在 {info['days_left']} 天后到期"
                                 f"（{info['not_after']:%Y-%m-%d}），请及时处理。")
            except Exception as exc:
                site.status = "error"
                site.error = str(exc)[:300]
                site.last_check_time = dt.datetime.now()
                if site.notify_enabled:
                    _notify_user(site.user_id, "站点证书检测失败",
                                 f"站点 <b>{site.url}</b> 检测失败：{exc}")
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- 到期提醒

def tick_cert_expiry():
    db = SessionLocal()
    try:
        today = dt.date.today()
        for cert in db.query(Certificate).all():
            if not cert.not_after:
                continue
            days = (cert.not_after.date() - today).days
            if days in (30, 15, 7, 3, 1):
                _notify_user(cert.user_id, "证书到期提醒",
                             f"证书 <b>{cert.domains}</b> 将在 {days} 天后到期"
                             f"（{cert.not_after:%Y-%m-%d}）。")
    finally:
        db.close()


def _notify_user(user_id: int, title: str, content: str):
    db = SessionLocal()
    try:
        row = (db.query(Notification)
               .filter(Notification.user_id == user_id, Notification.enabled.is_(True))
               .order_by(Notification.is_default.desc(), Notification.id.asc()).first())
        if not row:
            return
        ntype, nconf = row.type, decrypt_json(row.config)
    finally:
        db.close()
    try:
        notify.send(ntype, nconf, title, content)
    except Exception:
        pass


# ---------------------------------------------------------------- 启动

def start():
    scheduler.add_job(tick_pipelines, "interval", seconds=20, id="pipelines",
                      max_instances=1, coalesce=True)
    scheduler.add_job(tick_sites, "interval", minutes=10, id="sites",
                      max_instances=1, coalesce=True)
    scheduler.add_job(tick_cert_expiry, "cron", hour=9, minute=30, id="cert_expiry")
    scheduler.start()
    refresh_next_run_times()


def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
