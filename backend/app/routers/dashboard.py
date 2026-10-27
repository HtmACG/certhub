"""仪表盘统计接口"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, ok
from ..models import Certificate, History, Pipeline, SiteMonitor, User
from ..plugins import DEPLOY_TARGETS, SUPPORTED_CERTS
from ..services.system_info import collect_system_info

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = dt.datetime.now()
    pipelines = db.query(Pipeline).filter(Pipeline.user_id == user.id).all()
    certs = db.query(Certificate).filter(Certificate.user_id == user.id).all()
    sites = db.query(SiteMonitor).filter(SiteMonitor.user_id == user.id).all()
    histories = (db.query(History).filter(History.user_id == user.id)
                 .order_by(History.id.desc()).limit(10).all())

    expiring = sorted(
        [c for c in certs if c.not_after and 0 <= (c.not_after - now).days <= 30],
        key=lambda c: c.not_after,
    )[:8]

    # 近 7 天趋势：必须单独查，不能拿"最近 10 条"去凑，
    # 否则流水线跑得多的时候趋势会被截断成 0。
    since = now - dt.timedelta(days=6)
    week_histories = (db.query(History)
                      .filter(History.user_id == user.id, History.start_time >= since)
                      .all())
    trend = []
    for i in range(6, -1, -1):
        day = (now - dt.timedelta(days=i)).date()
        rows = [h for h in week_histories if h.start_time and h.start_time.date() == day]
        trend.append({
            "date": day.strftime("%m-%d"),
            "count": len(rows),
            "success": len([h for h in rows if h.status == "success"]),
            "failed": len([h for h in rows if h.status == "failed"]),
        })

    # 近 30 天签发质量：成功率与平均耗时
    month_ago = now - dt.timedelta(days=30)
    month_histories = (db.query(History)
                       .filter(History.user_id == user.id, History.start_time >= month_ago)
                       .all())
    finished = [h for h in month_histories if h.status in ("success", "failed")]
    succeeded = [h for h in finished if h.status == "success"]
    durations = [
        (h.end_time - h.start_time).total_seconds()
        for h in succeeded if h.end_time and h.start_time
    ]

    # 按签发机构分布
    issuer_map: dict[str, int] = {}
    for c in certs:
        key = (c.issuer or "未知").strip() or "未知"
        issuer_map[key] = issuer_map.get(key, 0) + 1
    issuer_dist = sorted(
        [{"issuer": k, "count": v} for k, v in issuer_map.items()],
        key=lambda x: x["count"], reverse=True,
    )[:6]

    return ok({
        "stats": {
            "pipelineTotal": len(pipelines),
            "pipelineEnabled": len([p for p in pipelines if not p.disabled]),
            "certTotal": len(certs),
            "certValid": len([c for c in certs if c.not_after and c.not_after > now]),
            "certExpiring": len([c for c in certs if c.not_after and 0 <= (c.not_after - now).days <= 30]),
            "certExpired": len([c for c in certs if c.not_after and c.not_after <= now]),
            "siteTotal": len(sites),
            "siteError": len([s for s in sites if s.status == "error"]),
            # 近 30 天签发质量
            "successRate": round(len(succeeded) / len(finished) * 100, 1) if finished else 0,
            "avgDuration": round(sum(durations) / len(durations), 1) if durations else 0,
            "runTotal30d": len(finished),
        },
        "expiringCerts": [{
            "id": c.id, "domains": c.domains, "issuer": c.issuer or "",
            "notAfter": _fmt(c.not_after),
            "daysLeft": (c.not_after - now).days if c.not_after else 0,
        } for c in expiring],
        "recentHistories": [{
            "id": h.id, "pipelineId": h.pipeline_id, "pipelineTitle": h.pipeline_title,
            "status": h.status, "triggerType": h.trigger_type,
            "startTime": _fmt(h.start_time),
        } for h in histories[:8]],
        "trend": trend,
        "issuerDist": issuer_dist,
        # 概览页「支持的证书」：来源是签发注册表，不是用户数据
        "supportedCerts": SUPPORTED_CERTS,
        "supportedCertsApply": len([c for c in SUPPORTED_CERTS if c.get("group") == "apply"]),
        # 证书能部署到哪些平台（按插件分类汇总）
        "deployTargets": DEPLOY_TARGETS,
        "deployTargetTotal": sum(t["count"] for t in DEPLOY_TARGETS),
        "sites": [{
            "id": s.id, "url": s.url, "status": s.status,
            "daysLeft": (s.expire_time - now).days if s.expire_time else None,
            "expireTime": _fmt(s.expire_time),
        } for s in sites[:6]],
    })


@router.get("/system")
def system_info(user: User = Depends(get_current_user)):
    """系统信息：CPU / 内存 / 硬盘使用率（工作台系统信息看板）。

    用普通 def 而非 async：CPU 使用率要在两次采样之间阻塞约 0.4 秒，
    交给 FastAPI 线程池跑，不卡住事件循环。
    """
    return ok(collect_system_info())
