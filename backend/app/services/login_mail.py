"""登录邮件提醒。

用户登录成功后，如果：
1. 系统设置里开了「登录邮件提醒」；
2. 这个账号填了邮箱；
3. 「通知渠道」里至少有一个可用的邮件渠道（拿它的 SMTP 参数发信）；
就把「登录时间 / IP / 浏览器」发到用户自己的邮箱，并提示异常登录要改密码。

任何一步不满足都静默跳过，失败也只打一行日志 —— 提醒是附加能力，不能影响登录。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import threading

from ..db import SessionLocal
from ..models import Notification, Setting, User
from ..security import decrypt_json
from . import notify


def _enabled(db) -> bool:
    row = db.get(Setting, "security")
    try:
        security = json.loads(row.value) if row else {}
    except Exception:
        security = {}
    return bool(security.get("loginNotify", True))


def _email_channel(db, user_id: int) -> dict | None:
    """优先用这个账号自己的邮件渠道，其次用任意一个可用的邮件渠道。"""
    rows = (db.query(Notification)
            .filter(Notification.type == "email", Notification.enabled.is_(True))
            .order_by((Notification.user_id == user_id).desc(),
                      Notification.is_default.desc(), Notification.id.desc())
            .all())
    for row in rows:
        config = decrypt_json(row.config) or {}
        if config.get("smtpHost"):
            return config
    return None


def _body(username: str, ip: str, ua: str, when: str, site: str) -> str:
    ua = (ua or "未知").strip()
    if len(ua) > 180:
        ua = ua[:180] + "…"
    return f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            max-width:560px;margin:0 auto;padding:24px;color:#18181b">
  <h2 style="font-size:18px;margin:0 0 16px">登录提醒</h2>
  <p style="margin:0 0 16px;line-height:1.7">
    <b>{html.escape(username)}</b>，你的 {html.escape(site)} 账号刚刚登录成功。
  </p>
  <table style="border-collapse:collapse;width:100%;font-size:14px;margin-bottom:20px">
    <tr><td style="padding:8px 0;color:#71717a;width:88px">登录时间</td>
        <td style="padding:8px 0">{html.escape(when)}</td></tr>
    <tr><td style="padding:8px 0;color:#71717a">登录 IP</td>
        <td style="padding:8px 0">{html.escape(ip or "未知")}</td></tr>
    <tr><td style="padding:8px 0;color:#71717a">浏览器</td>
        <td style="padding:8px 0;word-break:break-all">{html.escape(ua)}</td></tr>
  </table>
  <p style="margin:0 0 8px;padding:12px;border-radius:8px;background:#fef3c7;color:#92400e;
            font-size:13px;line-height:1.7">
    如果这不是你本人的操作，请立刻修改密码，并到「账号安全」检查两步验证与登录记录。
  </p>
  <p style="margin:16px 0 0;color:#a1a1aa;font-size:12px">
    本邮件由系统自动发送，请勿直接回复；如需关闭提醒，请让管理员在「系统设置 → 登录安全」里关闭。
  </p>
</div>"""


def _send(user_id: int, ip: str, ua: str, when: str, site: str) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        email = (user.email or "").strip() if user else ""
        if not user or not email or not _enabled(db):
            return
        config = _email_channel(db, user.id)
        if not config:
            return
        title = f"【{site}】登录提醒：{when}"
        notify.send_email({**config, "to": [email]}, title,
                          _body(user.nickname or user.username, ip, ua, when, site))
    except Exception as exc:  # noqa: BLE001 - 提醒失败不影响登录
        print(f"[login-mail] 发送登录提醒失败：{exc}")
    finally:
        db.close()


def schedule_login_alert(user_id: int, ip: str, ua: str = "", site: str = "CertHub") -> None:
    """登录接口里调用；后台线程发信，不拖慢登录响应。"""
    when = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    threading.Thread(target=_send, args=(user_id, ip, ua, when, site),
                     name="login-mail", daemon=True).start()
