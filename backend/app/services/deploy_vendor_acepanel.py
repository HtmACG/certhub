"""AcePanel 面板证书部署。

AcePanel 的开放接口用 HMAC-SHA256 签名：
    canonical = METHOD\\nPATH\\nQUERY\\nSHA256(body)
    stringToSign = "HMAC-SHA256"\\n<timestamp>\\nSHA256(canonical)
    signature = HMAC-SHA256(accessToken, stringToSign)
请求头带 `X-Timestamp` 与 `Authorization: HMAC-SHA256 Credential=<tokenId>, Signature=<sig>`。

两个插件：上传证书并绑定网站、替换面板自身证书。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Callable
from urllib.parse import urlsplit

from .deploy import CertContext, DeployError, _cloud_error, _cloud_request


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToAcePanelWebsite",
        "name": "AcePanel-部署到网站",
        "group": "deploy",
        "icon": "cloud",
        "category": "面板",
        "desc": "上传证书到 AcePanel，并绑定到指定网站的 HTTPS",
        "logo": "",
        "color": "#0ea5e9",
        "inputs": [
            f("accessId", "AcePanel 授权", "access", accessCategory="panel",
              accessTypes=["acepanel"], required=True),
            f("websiteIds", "部署网站", "tags", required=True,
              helper="AcePanel 控制台 → 网站列表里的网站 ID，可填多个；"
                     "证书会上传一次，再逐个绑定"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToAcePanelCert",
        "name": "AcePanel-面板证书",
        "group": "deploy",
        "icon": "cloud",
        "category": "面板",
        "desc": "替换 AcePanel 面板自身的 HTTPS 证书",
        "logo": "",
        "color": "#0ea5e9",
        "inputs": [
            f("accessId", "AcePanel 授权", "access", accessCategory="panel",
              accessTypes=["acepanel"], required=True),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "acepanel": {
        "name": "AcePanel",
        "category": "panel",
        "desc": "AcePanel 面板的开放接口（访问令牌 + HMAC 签名）",
        "inputs": [
            f("endpoint", "AcePanel 管理地址", required=True,
              placeholder="http://127.0.0.1:25475/entrance",
              helper="带安全入口，结尾不要加 /"),
            f("tokenId", "访问令牌 ID", "number", required=True,
              helper="AcePanel 控制台 → 设置 → 用户 → 访问令牌"),
            f("accessToken", "访问令牌", "password", required=True),
            f("skipSslVerify", "忽略证书校验", "switch", default=True,
              helper="面板用自签名 https 时保持开启"),
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


def acepanel_request(config: dict, method: str, path: str, data: dict | None = None) -> dict:
    endpoint = (config.get("endpoint") or "").strip().rstrip("/")
    token = config.get("accessToken") or ""
    token_id = config.get("tokenId")
    if not endpoint:
        raise DeployError("AcePanel 授权缺少管理地址（形如 http://host:25475/entrance）")
    if not token or not token_id:
        raise DeployError("AcePanel 授权缺少访问令牌 ID 或令牌内容")

    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if data is not None else ""
    url = endpoint + path
    parsed = urlsplit(url)
    canonical_path = parsed.path
    # 安全入口形如 /entrance/api/...，签名只认 /api 之后的部分
    api_pos = canonical_path.find("/api")
    if api_pos > 0:
        canonical_path = canonical_path[api_pos:]
    timestamp = int(time.time())
    canonical = "\n".join([method.upper(), canonical_path, parsed.query, _sha256(body)])
    string_to_sign = "\n".join(["HMAC-SHA256", str(timestamp), _sha256(canonical)])
    signature = hmac.new(token.encode("utf-8"), string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": str(timestamp),
        "Authorization": f"HMAC-SHA256 Credential={token_id}, Signature={signature}",
    }
    verify = not bool(config.get("skipSslVerify", True))
    resp = _cloud_request(method.upper(), url, headers=headers,
                          content=body.encode("utf-8") if body else None, verify=verify)
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        raise DeployError(f"AcePanel 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code >= 400:
        raise DeployError(f"AcePanel 接口失败：{_cloud_error(resp)}")
    code = payload.get("code")
    if code not in (None, 0, 200):
        raise DeployError(f"AcePanel 接口失败：{payload.get('msg') or payload}")
    return payload.get("data") or {}


def _as_ids(value) -> list[int]:
    if value is None or value == "":
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    result: list[int] = []
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        try:
            result.append(int(raw))
        except ValueError:
            raise DeployError(f"网站 ID 必须是数字：{raw}")
    return result


@_register("DeployToAcePanelWebsite")
def deploy_to_acepanel_website(ctx: CertContext, config: dict, log: Callable) -> None:
    website_ids = _as_ids(config.get("websiteIds"))
    if not website_ids:
        raise DeployError("请选择要部署的 AcePanel 网站")

    log("上传证书到 AcePanel")
    data = acepanel_request(config, "POST", "/api/cert/cert/upload",
                            {"cert": ctx.crt, "key": ctx.key})
    cert_id = data.get("id")
    if not cert_id:
        raise DeployError(f"证书上传成功但没有返回证书 ID：{str(data)[:200]}")
    domains = data.get("domains") or []
    log(f"证书上传成功，ID={cert_id}" + (f"，域名 {', '.join(domains)}" if domains else ""))

    for website_id in website_ids:
        acepanel_request(config, "POST", f"/api/cert/cert/{cert_id}/deploy",
                         {"id": cert_id, "website_id": website_id})
        log(f"证书已绑定到网站 {website_id}")
    log("AcePanel 网站证书部署完成")


@_register("DeployToAcePanelCert")
def deploy_to_acepanel_cert(ctx: CertContext, config: dict, log: Callable) -> None:
    log("读取 AcePanel 当前设置")
    setting = acepanel_request(config, "GET", "/api/setting")
    payload = dict(setting or {})
    payload.update({"acme": False, "https": True, "cert": ctx.crt, "key": ctx.key})
    acepanel_request(config, "POST", "/api/setting", payload)
    log("AcePanel 面板证书已替换")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
