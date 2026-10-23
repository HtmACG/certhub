"""腾讯云 SSL 证书（ssl.tencentcloudapi.com）客户端。

只实现免费 DV 证书需要的部分：
- 签名：TC3-HMAC-SHA256（与 services/deploy.py 里 CDN 那份逻辑一致，
  改动签名时两边要一起改）
- 申请：ApplyCertificate（PackageType=83 即 TrustAsia C1 DV Free）
- 轮询：DescribeCertificate（Status + DvAuthDetail 里的 DNS 验证记录）
- 取证书：DownloadCertificate 返回 ZIP(base64)，解出 crt / key

官方文档要点（已核对）：
- ApplyCertificate：DvAuthMethod=DNS_AUTO|DNS|FILE，DomainName，PackageType=83，
  CsrEncryptAlgo=RSA|ECC（ECC 必须带 CsrKeyParameter=prime256v1）
- DescribeCertificate：Status 1=已签发，2=审核失败，3=已过期，4=已自动添加DNS记录，
  13=免费证书待提交资料；DvAuthDetail 给出 DvAuthKey / DvAuthValue
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import re
import time
import zipfile
from typing import Callable

import httpx

from . import net

HOST = "ssl.tencentcloudapi.com"
SERVICE = "ssl"
VERSION = "2019-12-05"

# DescribeCertificate.Status 取值
STATUS_TEXT = {
    0: "审核中", 1: "已签发", 2: "审核失败", 3: "已过期", 4: "已自动添加 DNS 记录",
    5: "企业证书待提交资料", 6: "订单取消中", 7: "已取消", 8: "待上传确认函",
    9: "吊销中", 10: "已吊销", 11: "重颁发中", 12: "待上传吊销确认函",
    13: "免费证书待提交资料", 14: "已退款", 15: "迁移中",
}
ISSUED = 1
FAILED = {2, 3, 10, 14}


class TencentSslError(RuntimeError):
    pass


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def call(config: dict, action: str, body: dict | None = None, timeout: int = 30) -> dict:
    """调用一次 SSL 接口，返回 Response 里的内容体。"""
    return call_api(config, HOST, SERVICE, VERSION, action, body, timeout=timeout)


def call_api(config: dict, host: str, service: str, version: str, action: str,
             body: dict | None = None, timeout: int = 30) -> dict:
    """通用 TC3-HMAC-SHA256 调用（SSL / CLB 等服务共用）。"""
    secret_id = config.get("secretId") or ""
    secret_key = config.get("secretKey") or ""
    if not secret_id or not secret_key:
        raise TencentSslError("腾讯云授权缺少 SecretId / SecretKey")

    payload = json.dumps(body or {}, ensure_ascii=False, separators=(",", ":"))
    ts = int(time.time())
    date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
    ct = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{action.lower()}\n"
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join([
        "POST", "/", "", canonical_headers, signed_headers,
        hashlib.sha256(payload.encode()).hexdigest(),
    ])
    scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join([
        "TC3-HMAC-SHA256", str(ts), scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])
    key = _hmac(("TC3" + secret_key).encode(), date)
    key = _hmac(key, service)
    key = _hmac(key, "tc3_request")
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    headers = {
        "Authorization": (f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, "
                          f"SignedHeaders={signed_headers}, Signature={signature}"),
        "Content-Type": ct, "Host": host,
        "X-TC-Action": action, "X-TC-Timestamp": str(ts), "X-TC-Version": version,
    }
    token = config.get("sessionToken") or ""
    if token:
        headers["X-TC-Token"] = token

    try:
        resp = net.post(f"https://{host}/", content=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise TencentSslError(f"请求腾讯云 SSL 失败：{exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        raise TencentSslError(f"腾讯云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:300]}")

    res = (data or {}).get("Response") or {}
    err = res.get("Error")
    if err:
        raise TencentSslError(f"腾讯云 {action} 失败：[{err.get('Code')}] {err.get('Message')}")
    if resp.status_code >= 400:
        raise TencentSslError(f"腾讯云 {action} 失败：HTTP {resp.status_code} {resp.text[:200]}")
    return res


# ---------------------------------------------------------------- 业务封装

def test_connection(config: dict) -> str:
    """连通性测试：能列出证书就说明 SecretId/SecretKey 与签名都正确。"""
    res = call(config, "DescribeCertificates", {"Limit": 1})
    total = res.get("TotalCount") or 0
    return f"连接成功，账号下共有 {total} 张证书"


_KEY_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                        re.S)
_CERT_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def _unzip_cert(content_b64: str) -> tuple[str, str]:
    """DownloadCertificate 返回 ZIP(base64)，里面按服务器类型分目录（Nginx/Apache/IIS/Tomcat…）。

    **按内容判断哪份是证书、哪份是私钥，不能只看扩展名**：
    腾讯云的包里除了 xxx.crt / xxx.key，还有 xxx.pem 之类的合并文件，
    早先按 .key/.pem 抓私钥的结果是把一张证书当私钥存进了库（导出 pfx/jks 全报错）。
    """
    raw = base64.b64decode(content_b64)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise TencentSslError("腾讯云返回的证书包不是合法 ZIP") from exc

    names = [n for n in zf.namelist() if not n.endswith("/")]
    key_pem = ""
    cert_pem = ""
    for name in names:
        text = zf.read(name).decode("utf-8", "ignore")
        if not key_pem:
            match = _KEY_BLOCK.search(text)
            if match:
                key_pem = match.group(0).strip()
        # 站点证书优先：文件名里带 ca / chain / bundle 的先跳过
        if not cert_pem and not any(x in name.lower() for x in ("ca", "chain", "bundle")):
            match = _CERT_BLOCK.search(text)
            if match:
                cert_pem = match.group(0).strip()
        if key_pem and cert_pem:
            break
    if not cert_pem:
        for name in names:
            match = _CERT_BLOCK.search(zf.read(name).decode("utf-8", "ignore"))
            if match:
                cert_pem = match.group(0).strip()
                break

    if not cert_pem or not key_pem:
        raise TencentSslError(
            f"证书包里没找到证书或私钥（文件：{', '.join(names[:8])}），请到控制台手动下载")
    return cert_pem, key_pem


def apply_free_certificate(config: dict, domain: str, log: Callable,
                           key_type: str = "RSA", poll_seconds: int = 10,
                           timeout_seconds: int = 900,
                           dcv_handler: Callable[[str, str], None] | None = None) -> dict:
    """申请一张 TrustAsia C1 DV Free（3 个月），返回证书与私钥。"""
    algo = "ECC" if str(key_type).upper().startswith("EC") else "RSA"
    body = {
        "DvAuthMethod": "DNS",          # 手动 DNS：由本系统写解析记录，不依赖云解析托管
        "DomainName": domain,
        "PackageType": "83",            # 83 = TrustAsia C1 DV Free
        "CsrEncryptAlgo": algo,
        "CsrKeyParameter": "prime256v1" if algo == "ECC" else "2048",
        "Alias": f"certd-{domain}",
    }
    log(f"向腾讯云申请免费 DV 证书：{domain}（{algo}）")
    res = call(config, "ApplyCertificate", body)
    cert_id = res.get("CertificateId") or ""
    if not cert_id:
        raise TencentSslError(f"未拿到证书 ID：{json.dumps(res, ensure_ascii=False)[:300]}")
    log(f"已创建证书订单 {cert_id}，等待签发 ...")

    deadline = time.time() + timeout_seconds
    dcv_done = False
    last = ""
    while time.time() < deadline:
        detail = call(config, "DescribeCertificate", {"CertificateId": cert_id})
        status = detail.get("Status")
        status_name = STATUS_TEXT.get(status) or str(status)
        if status_name != last:
            log(f"当前状态：{status_name}")
            last = status_name

        # 域名验证阶段：把腾讯给的记录交给调用方写进解析
        if not dcv_done and dcv_handler:
            dv = detail.get("DvAuthDetail") or {}
            name, value = dv.get("DvAuthKey") or "", dv.get("DvAuthValue") or ""
            if name and value:
                log(f"DNS 验证记录：{name} TXT {value}")
                dcv_handler(name, value)
                dcv_done = True
            elif status in (0, 4):
                log("暂未取到 DNS 验证记录，稍后重试（若持续为空请到控制台手动添加）")

        if status == ISSUED:
            cert_pem, key_pem = _unzip_cert(
                (call(config, "DownloadCertificate", {"CertificateId": cert_id})
                 .get("Content") or ""))
            return {
                "certificateId": cert_id,
                "certificate": cert_pem,
                "privateKey": key_pem,
                "notAfter": detail.get("CertEndTime") or "",
            }
        if status in FAILED:
            msg = detail.get("StatusMsg") or ""
            raise TencentSslError(f"证书签发失败（{status_name}）{msg}")

        time.sleep(poll_seconds)

    raise TencentSslError(f"等待腾讯云签发超时（{timeout_seconds} 秒），最后状态：{last or '未知'}")
