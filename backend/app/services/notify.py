"""通知渠道实现：邮件、Webhook、钉钉、飞书、企业微信、Server酱、PushPlus、Telegram、Bark"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import smtplib
import time
import urllib.parse
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx

from . import net


class NotifyError(Exception):
    pass


def _safe_url(url: str) -> str:
    """错误信息里只保留主机名。

    钉钉/飞书把 token 放在 query，Telegram/Bark 放在 path，
    整条 URL 打出来等于把密钥写进执行日志（任何能看流水线的人都看得到）。
    """
    try:
        u = urllib.parse.urlsplit(url or "")
    except Exception:
        return "(地址无效)"
    return f"{u.scheme}://{u.netloc}" if u.netloc else "(地址无效)"


def _http_error(name: str, resp) -> str:
    """HTTP 4xx/5xx 时优先取响应体里的说明，别把整段 JSON 甩给用户。"""
    try:
        data = resp.json()
    except Exception:
        return f"{name} 返回 HTTP {resp.status_code}：{resp.text[:150]}"
    if isinstance(data, dict):
        for k in ("message", "msg", "errmsg", "info", "error", "description"):
            if data.get(k):
                return f"{name} 返回 HTTP {resp.status_code}：{data[k]}"
    return f"{name} 返回 HTTP {resp.status_code}：{resp.text[:150]}"


def _post_json(url: str, body: dict, timeout: int = 20, name: str = "通知") -> dict:
    try:
        resp = net.post(url, json=body, timeout=timeout)
    except httpx.HTTPError as exc:
        raise NotifyError(f"请求 {_safe_url(url)} 失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}）") from exc
    if resp.status_code >= 400:
        raise NotifyError(_http_error(name, resp))
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text[:200]}


def _check_biz(name: str, data: dict, code_key: str, ok_values: tuple, msg_keys: tuple) -> None:
    """校验渠道的业务返回码。

    钉钉 / 企业微信 / 飞书 / Server酱 / PushPlus 在密钥错误、被限流、机器人被移出群
    这类情况下依然返回 HTTP 200，只在响应体里给一个非成功的 errcode / code。
    只看 HTTP 状态码会把「没发出去」记成「执行成功」——证书到期提醒静默丢失，
    比报错更难发现。
    """
    if not isinstance(data, dict) or code_key not in data:
        return
    code = data.get(code_key)
    if code in ok_values:
        return
    msg = ""
    for k in msg_keys:
        if data.get(k):
            msg = str(data[k])
            break
    if len(msg) > 120:
        msg = msg[:120] + "…"
    raise NotifyError(f"{name} 发送失败：{msg or '返回体未说明原因'}（{code_key}={code}）")


def send_email(config: dict, title: str, content: str) -> None:
    host = config.get("smtpHost")
    port = int(config.get("smtpPort") or 465)
    username = config.get("username") or ""
    password = config.get("password") or ""
    sender = config.get("from") or username
    to = config.get("to") or []
    if isinstance(to, str):
        to = [x.strip() for x in to.replace(";", ",").split(",") if x.strip()]
    if not to:
        raise NotifyError("邮件通知未配置收件人")
    if not host:
        raise NotifyError("邮件通知未配置 SMTP 服务器")

    msg = MIMEText(content, "html", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = formataddr((str(Header("CertHub", "utf-8")), sender))
    msg["To"] = ", ".join(to)

    server = None
    try:
        if config.get("ssl", True):
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            try:
                server.starttls()
            except Exception:
                pass
        if username:
            server.login(username, password)
        server.sendmail(sender, to, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise NotifyError(f"SMTP 认证失败（{host}:{port}）：用户名或密码不对，"
                          f"多数邮箱这里要填「授权码」而不是登录密码")
    except smtplib.SMTPException as exc:
        raise NotifyError(f"SMTP 发送失败（{host}:{port}）：{exc}")
    except OSError as exc:
        raise NotifyError(f"无法连接 SMTP 服务器 {host}:{port}：{exc.__class__.__name__}")
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def send_webhook(config: dict, title: str, content: str) -> None:
    url = config.get("url")
    if not url:
        raise NotifyError("Webhook 未配置地址")
    headers = config.get("headers") or "{}"
    if isinstance(headers, str):
        try:
            headers = json.loads(headers or "{}")
        except Exception:
            headers = {}
    body = {"title": title, "content": content, "timestamp": int(time.time())}
    try:
        if (config.get("method") or "POST").upper() == "GET":
            resp = net.get(url, params=body, headers=headers, timeout=20)
        else:
            resp = net.post(url, json=body, headers=headers, timeout=20)
    except httpx.HTTPError as exc:
        raise NotifyError(f"请求 {url} 失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}）") from exc
    if resp.status_code >= 400:
        raise NotifyError(_http_error("Webhook", resp))


def send_dingtalk(config: dict, title: str, content: str) -> None:
    url = config.get("webhook")
    secret = config.get("secret")
    if secret:
        ts = str(round(time.time() * 1000))
        sign = base64.b64encode(
            hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
        ).decode()
        url = f"{url}&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"
    data = _post_json(url, {"msgtype": "markdown",
                            "markdown": {"title": title, "text": f"### {title}\n\n{content}"}},
                      name="钉钉")
    _check_biz("钉钉", data, "errcode", (0,), ("errmsg", "message"))


def send_feishu(config: dict, title: str, content: str) -> None:
    url = config.get("webhook")
    secret = config.get("secret")
    body = {"msg_type": "text", "content": {"text": f"{title}\n{content}"}}
    if secret:
        ts = str(int(time.time()))
        sign = base64.b64encode(
            hmac.new(f"{ts}\n{secret}".encode(), b"", hashlib.sha256).digest()
        ).decode()
        body.update({"timestamp": ts, "sign": sign})
    data = _post_json(url, body, name="飞书")
    _check_biz("飞书", data, "code", (0,), ("msg", "message"))


def send_wecom(config: dict, title: str, content: str) -> None:
    data = _post_json(config.get("webhook"), {
        "msgtype": "markdown",
        "markdown": {"content": f"**{title}**\n{content}"},
    }, name="企业微信")
    _check_biz("企业微信", data, "errcode", (0,), ("errmsg", "message"))


def send_serverchan(config: dict, title: str, content: str) -> None:
    key = config.get("sendKey")
    url = f"https://sctapi.ftqq.com/{key}.send"
    try:
        resp = net.post(url, data={"title": title, "desp": content}, timeout=20)
    except httpx.HTTPError as exc:
        raise NotifyError(f"请求 {_safe_url(url)} 失败：{exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise NotifyError(_http_error("Server酱", resp))
    try:
        data = resp.json()
    except Exception:
        return
    _check_biz("Server酱", data, "code", (0,), ("message", "info"))


def send_pushplus(config: dict, title: str, content: str) -> None:
    data = _post_json("https://www.pushplus.plus/send", {
        "token": config.get("token"), "title": title, "content": content,
        "template": "html", "topic": config.get("topic") or "",
    }, name="PushPlus")
    _check_biz("PushPlus", data, "code", (200,), ("msg", "message"))


def send_telegram(config: dict, title: str, content: str) -> None:
    token = config.get("botToken")
    data = _post_json(f"https://api.telegram.org/bot{token}/sendMessage", {
        "chat_id": config.get("chatId"), "text": f"{title}\n\n{content}",
        "parse_mode": "HTML",
    }, name="Telegram")
    _check_biz("Telegram", data, "ok", (True,), ("description",))


def send_bark(config: dict, title: str, content: str) -> None:
    base = (config.get("url") or "https://api.day.app").rstrip("/")
    data = _post_json(f"{base}/{config.get('deviceKey')}", {
        "title": title, "body": content, "group": "certd",
    }, name="Bark")
    _check_biz("Bark", data, "code", (200,), ("message", "msg"))


def send_anpush(config: dict, title: str, content: str) -> None:
    """AnPush 推送（专业版渠道）。

    AnPush 的接口形态在不同版本间有过调整，这里按其公开的
    /api/push 约定实现：Bearer Token + channel 可选。
    """
    base = (config.get("url") or "https://api.anpush.com").rstrip("/")
    token = config.get("token") or ""
    if not token:
        raise NotifyError("未配置 AnPush Token")
    payload = {"title": title, "content": content}
    if config.get("channel"):
        payload["channel"] = config.get("channel")
    try:
        resp = net.post(f"{base}/api/push", json=payload,
                          headers={"Authorization": f"Bearer {token}"}, timeout=30)
    except httpx.HTTPError as exc:
        raise NotifyError(f"请求 {_safe_url(base)} 失败：{exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise NotifyError(_http_error("AnPush", resp))


SENDERS = {
    "email": send_email,
    "webhook": send_webhook,
    "dingtalk": send_dingtalk,
    "feishu": send_feishu,
    "wecom": send_wecom,
    "serverchan": send_serverchan,
    "pushplus": send_pushplus,
    "anpush": send_anpush,
    "telegram": send_telegram,
    "bark": send_bark,
}


def send(notify_type: str, config: dict, title: str, content: str) -> None:
    sender = SENDERS.get(notify_type)
    if not sender:
        raise NotifyError(f"不支持的通知类型：{notify_type}")
    sender(config or {}, title, content)
