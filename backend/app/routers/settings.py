"""系统设置与审计日志接口"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings as app_settings
from ..db import get_db
from ..defaults import merge_defaults
from ..deps import audit, fail, get_current_user, ok, require_admin, page_no
from ..models import AuditLog, Setting, User
from ..services import net

router = APIRouter(prefix="/api/settings", tags=["settings"])

# ACME 账户 / EAB 凭据都在「授权管理」里维护，系统设置只放站点、安全、通知、网络
ALLOWED_KEYS = ("site", "security", "notify", "network")

# 历史遗留的打码值：老前端提交回来的 ****** 视为「这一项没改」
SECRET_MASK = "******"

#: 项目 / 开发者信息（只读），前端「系统设置 → 项目信息」原样展示。
#: 改这里就能改页面上显示的内容，不用动前端。
ABOUT_INFO = {
    "name": "CertHub",
    "version": app_settings.VERSION,
    "developer": "北幕林奈",
    "email": "htmacg@163.com",
    "website": "www.htmacg.cn",
    "websiteUrl": "http://www.htmacg.cn",
}

#: 代理测试的目标：都来自「国内服务器连不通就得靠代理」的场景
PROXY_TEST_TARGETS = [
    {"name": "Google Trust Services", "url": "https://dv.acme-v02.api.pki.goog/directory"},
    {"name": "ZeroSSL", "url": "https://acme.zerossl.com/v2/DV90"},
    {"name": "Let's Encrypt", "url": "https://acme-v02.api.letsencrypt.org/directory"},
]


def _clean(key: str, value: dict) -> dict:
    """凭据一律明文回显（规范第一条），只需把历史打码值当作空处理。"""
    if key == "network" and isinstance(value, dict):
        value = {k: ("" if v == SECRET_MASK else v) for k, v in value.items()}
    if key == "network":
        proxies = value.get("reverseProxies")
        if not isinstance(proxies, dict):
            proxies = {}
        value = {**value,
                 "reverseProxies": {str(k).strip(): str(v).strip()
                                    for k, v in proxies.items() if str(k).strip()}}
    return value


@router.get("")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = {}
    for key in ALLOWED_KEYS:
        row = db.get(Setting, key)
        try:
            stored = json.loads(row.value) if row else {}
        except Exception:
            stored = {}
        result[key] = _clean(key, merge_defaults(key, stored))
        if key == "network":
            # 前端要展示「内置默认反代」与「最终生效值」，不然用户不知道现在用的是哪个
            result[key]["reverseProxyDefaults"] = net.DEFAULT_REVERSE_PROXIES
            result[key]["resolvedReverseProxies"] = net.reverse_proxy_map()
    if user.role != "admin":
        result.pop("security", None)
        result.pop("network", None)
    # 只读：项目信息 / 开发者 / 版本号
    result["about"] = dict(ABOUT_INFO)
    return ok(result)


class SettingsParams(BaseModel):
    values: dict


@router.put("")
def update_settings(params: SettingsParams, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    for key, value in (params.values or {}).items():
        if key not in ALLOWED_KEYS:
            continue
        if key == "network" and isinstance(value, dict):
            # 只读字段（内置默认/最终生效值）不落库
            value = {k: v for k, v in value.items()
                     if k not in ("reverseProxyDefaults", "resolvedReverseProxies")}
        row = db.get(Setting, key)
        # 老前端把打码值原样提交回来时，别把真实密钥覆盖成 ******
        if key == "network" and isinstance(value, dict):
            old = {}
            try:
                old = json.loads(row.value) if row else {}
            except Exception:
                old = {}
            value = {k: (old.get(k, "") if v == SECRET_MASK else v)
                     for k, v in value.items()}
        payload = json.dumps(value, ensure_ascii=False)
        if row:
            row.value = payload
        else:
            db.add(Setting(key=key, value=payload))
    db.commit()
    # 代理配置有 5 秒缓存，改完要立刻生效，否则用户会以为「保存了没反应」
    net.invalidate()
    audit(db, admin, "修改系统设置")
    return ok(True)


class NetworkTestParams(BaseModel):
    httpProxy: str = ""
    httpsProxy: str = ""
    reverseProxy: str = ""
    target: str = ""


@router.post("/proxy/test")
def test_proxy(params: NetworkTestParams | None = None,
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """网络连通性测试：直连 / 走 HTTP 代理 / 走反代域名，各测一次。

    直连先试、连不上再上代理是常规做法，这里把三条路都摆出来，
    用户一眼能看出自己该配哪一个。
    """
    incoming = params or NetworkTestParams()
    saved = net.config()
    http_p = incoming.httpProxy.strip() or str(saved.get("httpProxy") or "")
    https_p = incoming.httpsProxy.strip() or str(saved.get("httpsProxy") or "")

    target = PROXY_TEST_TARGETS[0]
    for item in PROXY_TEST_TARGETS:
        if item["url"] == incoming.target or item["name"] == incoming.target:
            target = item
            break

    proxy = ""
    try:
        proxy = net._with_scheme(https_p or http_p)
    except net.ProxyError as exc:
        return fail(str(exc))

    direct = net.probe(target["url"], proxy=None)
    proxied = net.probe(target["url"], proxy=proxy) if proxy else None

    reverse_host = incoming.reverseProxy.strip() or net.reverse_proxy_for(target["url"])
    reverse = None
    reverse_url = ""
    if reverse_host:
        parts = target["url"].split("/", 3)
        reverse_url = "https://" + reverse_host.strip("/") + "/" + (parts[3] if len(parts) > 3 else "")
        reverse = net.probe(reverse_url, proxy=None)

    # 给一句结论，前端直接展示，不用用户自己比对
    if direct["ok"]:
        verdict = "直连可用，不需要代理"
    elif proxied and proxied["ok"]:
        verdict = "直连不通，HTTP/HTTPS 代理可用"
    elif reverse and reverse["ok"]:
        verdict = "直连不通，反向代理域名可用"
    else:
        verdict = "直连、代理、反代都不通，请检查网络与设置"

    audit(db, admin, "测试网络连通性", f"{target['name']} → {verdict}")
    return ok({
        "target": target,
        "verdict": verdict,
        "proxy": net._with_scheme(https_p or http_p) if proxy else "",
        "reverseProxy": reverse_host,
        "reverseUrl": reverse_url,
        "direct": direct,
        "proxied": proxied,
        "reverse": reverse,
    })


@router.get("/audit/list")
def list_audit(page: int = Depends(page_no), size: int = Query(20), keyword: str = "",
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if keyword:
        query = query.filter(AuditLog.action.like(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [{
        "id": r.id, "username": r.username, "action": r.action, "detail": r.detail,
        "ip": r.ip,
        "createTime": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
    } for r in rows], "total": total, "current": page, "size": size})