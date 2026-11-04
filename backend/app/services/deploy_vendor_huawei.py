"""华为云 CDN 证书部署。

华为云开放接口用 AK/SK 的 `SDK-HMAC-SHA256` 签名（APIG 风格）：
    CanonicalRequest = METHOD\\nURI\\nQuery\\nCanonicalHeaders\\nSignedHeaders\\nSHA256(body)
    StringToSign     = "SDK-HMAC-SHA256"\\nX-Sdk-Date\\nSHA256(CanonicalRequest)
    Signature        = HMAC-SHA256(SK, StringToSign)
    Authorization    = SDK-HMAC-SHA256 Access=<AK>, SignedHeaders=..., Signature=...

CDN 接口：
- GET  /v1.0/cdn/domains/{domain}/detail          查域名详情（拿状态、企业项目）
- PUT  /v1.1/cdn/configuration/domains/{domain}/configs  整段更新（含 https 证书）
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from typing import Callable
from urllib.parse import quote

from .deploy import CertContext, DeployError, _cloud_request


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToHuaweiCdn",
        "name": "华为云-部署证书至CDN",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "把证书更新到华为云 CDN 的 HTTPS 配置（直接传证书内容）",
        "logo": "",
        "color": "#c7000b",
        "inputs": [
            f("accessId", "华为云授权", "access", accessCategory="cloud",
              accessTypes=["huawei"], required=True),
            f("domains", "CDN 域名", "tags", required=True,
              helper="华为云 CDN 控制台里的加速域名"),
            f("enterpriseProjectId", "企业项目 ID", default="all",
              helper="子账号建议填具体项目 ID；主账号可以留 all"),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {}
HANDLERS: dict[str, Callable] = {}


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _quote(value: str) -> str:
    return quote(str(value), safe="~")


def huawei_request(config: dict, method: str, path: str,
                   query: dict | None = None, body: str | None = None,
                   host: str = "cdn.myhuaweicloud.com") -> dict:
    ak = str(config.get("accessKeyId") or "").strip()
    sk = str(config.get("accessKeySecret") or "").strip()
    if not ak or not sk:
        raise DeployError("华为云授权缺少 AccessKeyId / AccessKeySecret")

    body_bytes = (body or "").encode("utf-8")
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    headers = {"host": host, "x-sdk-date": timestamp}
    if body is not None:
        headers["content-type"] = "application/json"

    canonical_query = "&".join(
        f"{_quote(k)}={_quote(v)}" for k, v in sorted((query or {}).items())
    )
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    signed_headers = ";".join(sorted(headers))
    canonical_request = "\n".join([
        method.upper(), path, canonical_query, canonical_headers,
        signed_headers, _sha256_hex(body_bytes),
    ])
    string_to_sign = "\n".join([
        "SDK-HMAC-SHA256", timestamp, _sha256_hex(canonical_request.encode("utf-8")),
    ])
    signature = _hmac(sk.encode("utf-8"), string_to_sign)
    headers["Authorization"] = (f"SDK-HMAC-SHA256 Access={ak}, "
                                f"SignedHeaders={signed_headers}, Signature={signature}")

    url = f"https://{host}{path}"
    resp = _cloud_request(method.upper(), url, params=query or None,
                          content=body_bytes if body is not None else None,
                          headers=headers, verify=True)
    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        raise DeployError(f"华为云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code >= 400:
        err = data.get("error") or data
        message = (err.get("message") or err.get("error_msg")
                   or data.get("error_msg") or data.get("message"))
        code = err.get("code") or data.get("error_code") or ""
        raise DeployError(f"华为云 {method} {path} 失败"
                          f"{('[' + str(code) + ']') if code else ''}：{message or data}")
    return data


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


@_register("DeployToHuaweiCdn")
def deploy_to_huawei_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    domains = _as_list(config.get("domains"))
    if not domains:
        raise DeployError("请填写要部署的华为云 CDN 域名")
    project = str(config.get("enterpriseProjectId") or "").strip()
    query = {"enterprise_project_id": project} if project else None

    for domain in domains:
        detail = huawei_request(config, "GET",
                                f"/v1.0/cdn/domains/{_quote(domain)}/detail",
                                query=query)
        info = detail.get("domain") or {}
        status = info.get("domain_status") or info.get("domainStatus") or ""
        log(f"域名 {domain} 当前状态：{status or '未知'}")

        body = {
            "configs": {
                "https": {
                    "https_status": "on",
                    "certificate_type": "server",
                    "certificate_source": 0,
                    "certificate_name": ctx.render(config.get("certName")
                                                   or "{domain}-{timestamp}"),
                    "certificate_value": ctx.crt,
                    "private_key": ctx.key,
                }
            }
        }
        try:
            huawei_request(config, "PUT",
                           f"/v1.1/cdn/configuration/domains/{_quote(domain)}/configs",
                           query=query, body=json.dumps(body, ensure_ascii=False))
        except DeployError as exc:
            if status == "offline":
                log(f"域名 {domain} 处于停用状态，忽略部署错误：{exc}")
                continue
            raise
        log(f"华为云 CDN 域名 {domain} 的 HTTPS 证书已更新")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
