"""火山引擎（Volcengine）API 客户端。

只实现证书中心需要的部分：
- 签名：火山引擎 HMAC-SHA256（结构与 AWS SigV4 一致）
- 免费证书申请：QuickApplyCertificate → 轮询 CertificateGetInstance → 下载
- 证书上传：ImportCertificate（把本系统签发的证书托管到火山引擎）

官方文档要点（已核对）：
- 新版接口域名 certificate-service.volcengineapi.com，Version=2024-10-01
- 旧版域名 open.volcengineapi.com，Version=2021-06-01
- 签名头：Authorization: HMAC-SHA256 Credential=<AK>/<date>/<region>/<service>/request,
          SignedHeaders=..., Signature=...
- 证书状态：NotSubmitted / Pending / Issued / Failed / Canceled / Revoked
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Callable

import httpx

from . import net

DEFAULT_HOST = "certificate-service.volcengineapi.com"
DEFAULT_REGION = "cn-north-1"
DEFAULT_SERVICE = "certificate_service"
DEFAULT_VERSION = "2024-10-01"

ALGORITHM = "HMAC-SHA256"


class VolcError(RuntimeError):
    pass


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="-_.~")


def sign(config: dict, method: str, action: str, body: dict | None = None,
         version: str = DEFAULT_VERSION) -> tuple[str, dict, bytes]:
    """生成签名，返回 (完整 URL, 请求头, 请求体字节)。

    canonical request 的顺序与官方一致：
        METHOD \\n URI \\n QUERY \\n CANONICAL_HEADERS \\n SIGNED_HEADERS \\n HASH(PAYLOAD)
    """
    ak = config.get("accessKeyId") or config.get("accessKey") or ""
    sk = config.get("accessKeySecret") or config.get("secretKey") or ""
    if not ak or not sk:
        raise VolcError("火山引擎授权缺少 AccessKey / SecretKey")

    host = config.get("host") or DEFAULT_HOST
    region = config.get("region") or DEFAULT_REGION
    service = config.get("service") or DEFAULT_SERVICE

    now = dt.datetime.now(dt.timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]

    payload = b""
    if method.upper() == "POST":
        payload = json.dumps(body or {}, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
    content_sha = hashlib.sha256(payload).hexdigest()

    query = {"Action": action, "Version": version}
    canonical_query = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(query.items()))

    headers = {
        "content-type": "application/json",
        "host": host,
        "x-content-sha256": content_sha,
        "x-date": x_date,
    }
    token = config.get("sessionToken") or ""
    if token:
        headers["x-security-token"] = token

    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    canonical_request = "\n".join([
        method.upper(), "/", canonical_query, canonical_headers, signed_headers, content_sha,
    ])

    credential_scope = f"{short_date}/{region}/{service}/request"
    string_to_sign = "\n".join([
        ALGORITHM, x_date, credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    key = _hmac(sk.encode("utf-8"), short_date)
    key = _hmac(key, region)
    key = _hmac(key, service)
    key = _hmac(key, "request")
    signature = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    headers["Authorization"] = (
        f"{ALGORITHM} Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    url = f"https://{host}/?{canonical_query}"
    return url, headers, payload


def call(config: dict, action: str, body: dict | None = None, method: str = "POST",
         version: str = DEFAULT_VERSION, timeout: int = 30) -> dict:
    """调用一次火山引擎接口，返回 ResponseMetadata + Result。"""
    url, headers, payload = sign(config, method, action, body, version)
    try:
        resp = net.request(method, url, headers=headers, content=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise VolcError(f"请求火山引擎失败：{exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        raise VolcError(f"火山引擎返回非 JSON（HTTP {resp.status_code}）：{resp.text[:300]}")

    meta = (data or {}).get("ResponseMetadata") or {}
    error = meta.get("Error")
    if error:
        code = error.get("Code") or error.get("CodeN")
        message = error.get("Message") or ""
        raise VolcError(f"火山引擎 {action} 失败：[{code}] {message}")
    if resp.status_code >= 400:
        raise VolcError(f"火山引擎 {action} 失败：HTTP {resp.status_code} {resp.text[:300]}")
    return data.get("Result") or data


# ---------------------------------------------------------------- 业务封装

def test_connection(config: dict) -> str:
    """连通性测试：拉一页证书实例，能返回就说明 AK/SK 与签名都对。"""
    result = call(config, "CertificateGetInstanceList", {"PageSize": 1, "PageNumber": 1})
    total = result.get("Total") or result.get("TotalCount") or 0
    return f"连接成功，账号下共有 {total} 张证书实例"


def _pick(node, *names):
    """在嵌套结构里按候选字段名找一个值（各版本字段名不一致时的兜底）"""
    if isinstance(node, dict):
        for name in names:
            for key, value in node.items():
                if key.lower() == name.lower() and isinstance(value, str) and value:
                    return value
        for value in node.values():
            found = _pick(value, *names)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _pick(item, *names)
            if found:
                return found
    return ""


def get_dcv_param(config: dict, instance_id: str) -> tuple[str, str]:
    """取 DNS 验证记录，返回 (记录名, 记录值)；取不到时返回空串。"""
    try:
        data = call(config, "CertificateGetDcvParam", {"InstanceId": instance_id})
    except VolcError:
        return "", ""
    name = _pick(data, "DcvKey", "RecordName", "DnsRecordName", "HostRecord", "Name")
    value = _pick(data, "DcvValue", "RecordValue", "DnsRecordValue", "Value")
    return name, value


def organization_id(config: dict, preferred: str = "") -> str:
    """取证书中心的组织机构 ID（QuickApplyCertificate 的必填参数）。

    用户可以在授权/任务里手填，留空则自动取第一个组织机构。
    """
    if preferred:
        return preferred
    data = call(config, "CertificateGetOrganizationList", {"PageNumber": 1, "PageSize": 10})
    orgs = data.get("Organizations") or []
    if not orgs:
        raise VolcError("火山引擎证书中心还没有组织机构，请先在控制台创建（企业/个人认证信息）")
    return orgs[0].get("OrganizationId") or ""


def apply_free_certificate(config: dict, domain: str, log: Callable,
                           key_type: str = "RSA", poll_seconds: int = 5,
                           timeout_seconds: int = 600,
                           dcv_handler: Callable[[str, str], None] | None = None,
                           plan: str = "", org_id: str = "") -> dict:
    """申请一张免费 DV 证书，返回 {instanceId, certificate, privateKey}。

    接口真实契约（对照火山引擎 Go SDK 的 QuickApplyCertificateInput 核对）：

        CommonName / Plan / OrganizationId / ValidationType 都是必填，
        KeyAlg 取 rsa | ecc | SM2，ValidationType 取 dns_txt | dns_cname | http | https，
        返回 {InstanceId}。

    旧实现发的是 {Domain, InstanceType, KeyType, CsrType}——参数名全错，
    真实接口会直接回 [MissingParameter.Plan]。注意 Plan 是账号维度的套餐编码，
    各家账号/套餐不同，所以做成可配置项，而不是写死一个猜的值。
    """
    if not plan:
        raise VolcError(
            "火山引擎免费证书需要填写「套餐 Plan」："
            "在证书中心购买/领取免费证书时能看到对应套餐编码，填到插件配置里。"
            "（接口会返回 Unsupported.OrderPlan，说明 Plan 值不被该账号支持）")

    log(f"向火山引擎申请免费证书：{domain}（{key_type}，Plan={plan}）")
    org = organization_id(config, org_id)
    log(f"使用组织机构 {org}")
    body = {
        "CommonName": domain,
        "Plan": plan,
        "OrganizationId": org,
        "ValidationType": "dns_txt",
        "KeyAlg": "ecc" if str(key_type).upper().startswith("EC") else "rsa",
    }
    result = call(config, "QuickApplyCertificate", body)
    instance_id = (result.get("InstanceId") or result.get("instanceId")
                   or result.get("CertificateId") or "")
    if not instance_id:
        raise VolcError(f"未拿到证书实例 ID：{json.dumps(result, ensure_ascii=False)[:300]}")
    log(f"已创建证书实例 {instance_id}，等待签发 ...")

    deadline = time.time() + timeout_seconds
    status = ""
    dcv_done = False
    while time.time() < deadline:
        # 第一次轮询时顺便把 DNS 验证记录写进去
        if dcv_handler and not dcv_done:
            name, value = get_dcv_param(config, instance_id)
            if name and value:
                log(f"DNS 验证记录：{name} TXT {value}")
                dcv_handler(name, value)
                dcv_done = True
            else:
                log("暂未取到 DNS 验证记录，稍后重试（若持续为空请到控制台手动添加）")

        time.sleep(poll_seconds)
        detail = call(config, "CertificateGetInstance", {"InstanceId": instance_id})
        status = (detail.get("Status") or detail.get("status") or "").strip()
        log(f"当前状态：{status or '未知'}")
        if status == "Issued":
            return {
                "instanceId": instance_id,
                "certificate": detail.get("Certificate") or detail.get("CertificatePem") or "",
                "privateKey": detail.get("PrivateKey") or detail.get("PrivateKeyPem") or "",
                "notAfter": detail.get("NotAfter") or detail.get("ExpiredTime") or "",
                "raw": detail,
            }
        if status in ("Failed", "Canceled", "Revoked"):
            reason = detail.get("StatusMessage") or detail.get("Message") or ""
            raise VolcError(f"证书签发失败（{status}）{reason}")
    raise VolcError(f"等待证书签发超时（{timeout_seconds} 秒），最后状态：{status or '未知'}")


def import_certificate(config: dict, domain: str, cert_pem: str, key_pem: str,
                       log: Callable, alias: str = "") -> dict:
    """把已有证书上传到火山引擎证书中心，便于 CDN / CLB 直接引用。"""
    log(f"上传证书到火山引擎证书中心：{domain}")
    body = {
        "CertificateName": alias or domain,
        "Certificate": cert_pem,
        "PrivateKey": key_pem,
    }
    result = call(config, "ImportCertificate", body)
    instance_id = result.get("InstanceId") or result.get("instanceId") or ""
    log(f"上传完成，实例 ID：{instance_id or '未返回'}")
    return {"instanceId": instance_id, "raw": result}
