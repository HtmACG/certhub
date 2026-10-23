"""百度智能云（BCE）CDN 客户端
=========================================================
只实现「把证书装到 CDN 域名」需要的部分：

- 签名：BCE 的 bce-auth-v1（HMAC-SHA256）
  ```
  authStringPrefix = bce-auth-v1/{ak}/{timestamp}/{expiration}
  signingKey       = hex(HMAC-SHA256(sk, authStringPrefix))
  canonicalRequest = METHOD \n URI \n QUERY \n "host:...\nx-bce-date:..."
  signature        = hex(HMAC-SHA256(signingKey, canonicalRequest))
  Authorization    = authStringPrefix/{signedHeaders}/{signature}
  ```
- 接口（已按官方 SDK baidubce/bce-sdk-go services/cdn/api/cert.go 核对）：
  - 域名列表：`GET /v2/domain` → {"domains": [...]}
  - 上传/更新域名证书：`PUT /v2/{domain}/certificates`
      body: {"certificate": {"certName","certServerData","certPrivateData","certLinkData"},
             "httpsEnable": "ON"}
      → {"certId": "ssl-xxxx"}
  - 查询域名证书：`GET /v2/{domain}/certificates`

注意：证书是**按域名**挂的，百度云 CDN 没有全局证书库，
所以「部署」= 给每个加速域名各传一次证书。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import urllib.parse

import httpx

from . import net

HOST = "cdn.baidubce.com"


class BaiduError(RuntimeError):
    pass


def _encode(value) -> str:
    """BCE 的 URI 编码规则：只保留 -_.~ 不转义，其余一律 %XX（空格是 %20）。"""
    return urllib.parse.quote(str(value), safe="-_.~")


def _sign(config: dict, method: str, path: str,
          params: dict | None = None, expiration: int = 1800) -> dict:
    ak = (config.get("accessKeyId") or "").strip()
    sk = (config.get("accessKeySecret") or "").strip()
    if not ak or not sk:
        raise BaiduError("百度云授权缺少 AccessKeyID / AccessKeySecret")

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    auth_prefix = f"bce-auth-v1/{ak}/{timestamp}/{expiration}"
    signing_key = hmac.new(sk.encode(), auth_prefix.encode(), hashlib.sha256).hexdigest()

    canonical_uri = _encode(path or "/").replace("%2F", "/")
    query = "&".join(
        f"{_encode(k)}={_encode(v)}" for k, v in sorted((params or {}).items())
    )
    signed = {"host": HOST, "x-bce-date": timestamp}
    canonical_headers = "\n".join(f"{k}:{_encode(v)}" for k, v in sorted(signed.items()))
    signed_headers = ";".join(sorted(signed))

    canonical_request = "\n".join([
        method.upper(), canonical_uri, query, canonical_headers,
    ])
    signature = hmac.new(signing_key.encode(), canonical_request.encode(),
                         hashlib.sha256).hexdigest()
    return {
        "Host": HOST,
        "x-bce-date": timestamp,
        "Authorization": f"{auth_prefix}/{signed_headers}/{signature}",
    }


def call(config: dict, method: str, path: str, params: dict | None = None,
         body: dict | None = None, timeout: int = 30) -> dict:
    """调一次 CDN 接口，返回 JSON（错误压成一行人话）。"""
    headers = _sign(config, method, path, params)
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    url = f"https://{HOST}{path}"
    try:
        resp = net.request(method.upper(), url, params=params, json=body,
                           headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise BaiduError(f"请求百度云失败：{exc.__class__.__name__}"
                         f"（{str(exc) or '无详细原因'}）") from exc

    text = resp.text or ""
    try:
        data = resp.json() or {}
    except ValueError:
        data = {}

    if resp.status_code >= 400:
        code = data.get("code") or ""
        message = data.get("message") or text[:200]
        hint = ""
        if code == "NoSuchDomain":
            hint = "（加速域名不在当前账号下，或者还没在 CDN 控制台添加）"
        elif code in ("AccessDenied", "SignatureNotMatch", "InvalidAccessKeyId"):
            hint = "（AccessKeyID / AccessKeySecret 不正确，或该 AK 没有 CDN 权限）"
        raise BaiduError(f"百度云 {method} {path} 失败：[{code}] {message}{hint}")
    return data


# ---------------------------------------------------------------- 业务封装
def list_domains(config: dict) -> list[str]:
    """加速域名列表（分页拉全，marker 游标）。"""
    names: list[str] = []
    marker = ""
    for _ in range(20):  # 保险丝，最多 20 页
        params = {"maxKeys": "100"}
        if marker:
            params["marker"] = marker
        data = call(config, "GET", "/v2/domain", params)
        rows = data.get("domains") or []
        names.extend([row for row in rows if isinstance(row, str)])
        if not data.get("isTruncated"):
            break
        marker = data.get("nextMarker") or ""
        if not marker:
            break
    return names


def domain_cert(config: dict, domain: str) -> dict:
    """查询某个加速域名当前挂的证书（没有证书时百度云回 404，这里当空处理）。"""
    try:
        return call(config, "GET", f"/v2/{domain}/certificates")
    except BaiduError as exc:
        if "NotFound" in str(exc) or "证书" in str(exc):
            return {}
        raise


def put_domain_cert(config: dict, domain: str, cert_name: str, crt: str, key: str,
                    chain: str = "", enable: bool = True) -> str:
    """上传并启用域名证书，返回 certId。"""
    body = {
        "certificate": {
            "certName": cert_name,
            "certServerData": crt,
            "certPrivateData": key,
            "certLinkData": chain or "",
        },
        "httpsEnable": "ON" if enable else "OFF",
    }
    data = call(config, "PUT", f"/v2/{domain}/certificates", body=body, timeout=60)
    return str(data.get("certId") or "")


def test_connection(config: dict) -> str:
    """连通性测试：能列出域名就算通过（顺带报数量）。"""
    names = list_domains(config)
    return f"百度云连接成功，账号下共 {len(names)} 个 CDN 加速域名"
