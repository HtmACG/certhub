"""中国移动（移动云 CDN）证书部署。

认证分两步：
1. POST /api/authentication：sign = sha256(tenantId + datetime + tenantKey)，换 12 小时 token；
2. 业务请求带 `CMCDN-Auth-Token`，并额外带 `HTTP-X-CMCDN-Signature`：
   POST/PUT 用 sha256(JSON(body) + token)，GET 用 sha256(token)。
默认接口地址 https://p.cdn.10086.cn/。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Callable

from .deploy import CertContext, DeployError, _cloud_request


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToCmccCdn",
        "name": "中国移动-部署证书到CDN",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "上传证书到中国移动 CDN 并绑定到加速域名",
        "logo": "",
        "color": "#0084c8",
        "inputs": [
            f("accessId", "中国移动授权", "access", accessCategory="cloud",
              accessTypes=["cmcc"], required=True),
            f("domainList", "加速域名", "tags", required=True,
              helper="中国移动 CDN 控制台里的加速域名，可多选"),
            f("certName", "证书名称", default="{domain}-{timestamp}",
              helper="只能包含字母、数字、下划线，最长 32 个字符"),
            f("waitSeconds", "等待秒数", "number", default=10,
              helper="下发后等 CDN 生效再继续后续任务"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "cmcc": {
        "name": "中国移动 CDN",
        "category": "cloud",
        "desc": "移动云 CDN 开放接口（tenantId + tenantKey）",
        "inputs": [
            f("tenantId", "租户 ID（tenant_id）", required=True),
            f("tenantKey", "租户密钥（tenant_key）", "password", required=True,
              helper="移动云 CDN 控制台申请开放接口后获得"),
            f("endpoint", "接口地址", default="https://p.cdn.10086.cn/",
              helper="一般不用改"),
        ],
    },
}

HANDLERS: dict[str, Callable] = {}


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _cmcc_token(config: dict) -> str:
    tenant_id = str(config.get("tenantId") or "").strip()
    tenant_key = str(config.get("tenantKey") or "").strip()
    if not tenant_id or not tenant_key:
        raise DeployError("移动云授权缺少 tenantId / tenantKey")
    endpoint = str(config.get("endpoint") or "https://p.cdn.10086.cn/").rstrip("/")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    body = json.dumps({"datetime": now,
                       "authorization": {"tenant_id": tenant_id,
                                         "sign": _sha256(tenant_id + now + tenant_key)}},
                      ensure_ascii=False, separators=(",", ":"))
    resp = _cloud_request("POST", endpoint + "/api/authentication",
                          content=body.encode("utf-8"),
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json"}, verify=False)
    try:
        data = resp.json()
    except ValueError:
        raise DeployError(f"移动云认证返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code >= 400:
        raise DeployError(f"移动云认证失败（HTTP {resp.status_code}）：{data.get('error_msg') or data}")
    token = data.get("token")
    if not token:
        raise DeployError(f"移动云认证成功但没有返回 token：{str(data)[:200]}")
    return token


def _cmcc_request(config: dict, method: str, path: str, data: dict | None = None) -> dict:
    endpoint = str(config.get("endpoint") or "https://p.cdn.10086.cn/").rstrip("/")
    token = _cmcc_token(config)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if data is not None else ""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.cmcdn+json",
        "CMCDN-Auth-Token": token,
        "HTTP-X-CMCDN-Signature": _sha256(body + token) if body else _sha256(token),
    }
    resp = _cloud_request(method.upper(), endpoint + path, headers=headers,
                          content=body.encode("utf-8") if body else None, verify=False)
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        raise DeployError(f"移动云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code >= 400:
        raise DeployError(f"移动云接口失败（HTTP {resp.status_code}）："
                          f"{payload.get('error_msg') or payload}")
    if payload.get("error_code") not in (None, 0, "0"):
        raise DeployError(f"移动云接口失败：{payload.get('error_msg') or payload}")
    return payload.get("data") or {}


@_register("DeployToCmccCdn")
def deploy_to_cmcc_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    domains = _as_list(config.get("domainList"))
    if not domains:
        raise DeployError("请选择要更新的中国移动 CDN 加速域名")

    name = ctx.render(config.get("certName") or "{domain}-{timestamp}")[:32]
    log(f"上传证书 {name}")
    uploaded = _cmcc_request(config, "POST", "/api/config/action?commandType=saveCrt&version=1", {
        "certificate": ctx.crt,
        "private_key": ctx.key,
        "crt_name": name,
    })
    cert_id = uploaded.get("unique_id")
    if not cert_id:
        raise DeployError(f"证书上传成功但没有返回 unique_id：{str(uploaded)[:200]}")
    log(f"证书上传成功，unique_id={cert_id}")

    _cmcc_request(config, "PUT", "/api/config/action?commandType=manageDomainBaseConfig&version=1", {
        "modify_type": 0,
        "domains": domains,
        "https_enable": True,
        "unique_id": cert_id,
    })
    log(f"域名 {', '.join(domains)} 已绑定证书 {cert_id}")

    wait = int(config.get("waitSeconds") or 10)
    if wait > 0:
        import time

        log(f"等待 {wait} 秒让 CDN 生效 ...")
        time.sleep(min(wait, 300))


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
