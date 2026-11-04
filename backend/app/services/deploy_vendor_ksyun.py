"""金山云 CDN 证书更新。

走金山云 CDN 的证书接口（AWS SigV4 风格签名）：
- `POST /2016-09-01/cert/GetCertificates` 查证书（拿 CertificateName）
- `POST /2016-09-01/cert/SetCertificate` 用同一个 CertificateId 覆盖证书内容

签名：AWS4-HMAC-SHA256，service=cdn，region 默认 cn-beijing-6，
body 是 form-urlencoded（字段按插入顺序：业务字段 → Action → Version）。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from typing import Callable
from urllib.parse import quote, urlencode

from .deploy import CertContext, DeployError, _cloud_request

API_HOST = "cdn.api.ksyun.com"


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToKsyunCdn",
        "name": "金山云-更新CDN证书",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "按证书 ID 覆盖金山云 CDN 上已绑定域名的证书",
        "logo": "",
        "color": "#e60012",
        "inputs": [
            f("accessId", "金山云授权", "access", accessCategory="cloud",
              accessTypes=["ksyun"], required=True),
            f("certList", "证书 ID", "tags", required=True,
              helper="金山云 CDN 控制台证书列表里的 CertificateId；"
                     "如果这里没有，请先在控制台给 CDN 域名手动绑定一次证书"),
            f("region", "地域", default="cn-beijing-6",
              helper="金山云 CDN 固定用 cn-beijing-6，一般不用改"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "ksyun": {
        "name": "金山云",
        "category": "cloud",
        "desc": "金山云 CDN 证书更新（AccessKey）",
        "inputs": [
            f("accessKeyId", "AccessKey ID", required=True,
              helper="https://uc.console.ksyun.com/pro/iam/#/set/keyManage"),
            f("accessKeySecret", "AccessKey Secret", "password", required=True),
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


def _hmac(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def ksyun_request(config: dict, action: str, version: str, path: str, data: dict) -> dict:
    access_key = str(config.get("accessKeyId") or "").strip()
    secret_key = str(config.get("accessKeySecret") or "").strip()
    if not access_key or not secret_key:
        raise DeployError("金山云授权缺少 AccessKey ID / Secret")
    region = str(config.get("region") or "cn-beijing-6")
    service = "cdn"

    payload = dict(data or {})
    payload["Action"] = action
    payload["Version"] = version
    body = urlencode(payload, quote_via=quote)
    now = dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")

    signed_headers = "content-type;host;x-amz-date"
    canonical_headers = (f"content-type:application/x-www-form-urlencoded\n"
                         f"host:{API_HOST}\nx-amz-date:{amz_date}\n")
    canonical_request = "\n".join(["POST", path, "", canonical_headers,
                                   signed_headers, _sha256_hex(body)])
    scope = f"{date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                _sha256_hex(canonical_request)])
    k_date = _hmac(("AWS4" + secret_key).encode(), date)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                     f"SignedHeaders={signed_headers}, Signature={signature}")

    resp = _cloud_request("POST", f"https://{API_HOST}{path}",
                          headers={"Content-Type": "application/x-www-form-urlencoded",
                                   "X-Amz-Date": amz_date,
                                   "Authorization": authorization},
                          content=body.encode("utf-8"))
    try:
        payload_json = resp.json()
    except ValueError:
        raise DeployError(f"金山云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code >= 400:
        err = payload_json.get("Error") or {}
        raise DeployError(f"金山云 {action} 失败：{err.get('Message') or payload_json}")
    if isinstance(payload_json.get("Error"), dict) and payload_json["Error"].get("Message"):
        raise DeployError(f"金山云 {action} 失败：{payload_json['Error']['Message']}")
    return payload_json


def _cert_name(config: dict, cert_id: str) -> str:
    data = ksyun_request(config, "GetCertificates", "2016-09-01",
                         "/2016-09-01/cert/GetCertificates",
                         {"CertificateId": cert_id})
    rows = data.get("Certificates") or []
    if not rows:
        raise DeployError(f"金山云里找不到证书 {cert_id}")
    return str(rows[0].get("CertificateName") or cert_id)


@_register("DeployToKsyunCdn")
def deploy_to_ksyun_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    cert_ids = _as_list(config.get("certList"))
    if not cert_ids:
        raise DeployError("请选择要更新的金山云证书 ID")

    for cert_id in cert_ids:
        name = _cert_name(config, cert_id)
        log(f"更新金山云证书 {cert_id}（{name}）")
        ksyun_request(config, "SetCertificate", "2016-09-01",
                      "/2016-09-01/cert/SetCertificate", {
                          "CertificateId": cert_id,
                          "CertificateName": name,
                          "ServerCertificate": ctx.crt,
                          "PrivateKey": ctx.key,
                      })
        log(f"金山云证书 {cert_id} 已更新")
    log("金山云 CDN 证书更新完成")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
