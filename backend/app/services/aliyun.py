"""阿里云 RPC 风格 API 的公共签名/请求封装。

阿里云大多数老服务（云解析、数字证书管理服务、CDN…）都是同一套 RPC 签名：
- 参数按 key 排序 → canonicalized query string → HMAC-SHA1
- SignatureNonce 每次必须不同，否则会命中「Specified signature nonce was used already」
- 错误响应是 HTTP 4xx + {"Code","Message","RequestId","Recommend"}
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import urllib.parse

import httpx

from . import net


class AliyunError(RuntimeError):
    pass


def _enc(value) -> str:
    return urllib.parse.quote(str(value), safe="~")


def signed_params(config: dict, params: dict) -> dict:
    """补公共参数并算出 Signature。"""
    ak = config.get("accessKeyId") or ""
    sk = config.get("accessKeySecret") or ""
    if not ak or not sk:
        raise AliyunError("阿里云授权缺少 AccessKeyId / AccessKeySecret")

    common = {
        "Format": "JSON",
        "AccessKeyId": ak,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": os.urandom(16).hex(),
        "Timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    common.update({k: v for k, v in params.items() if v not in (None, "")})
    canonical = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(common.items()))
    string_to_sign = "GET&%2F&" + _enc(canonical)
    digest = hmac.new((sk + "&").encode(), string_to_sign.encode(), hashlib.sha1).digest()
    common["Signature"] = base64.b64encode(digest).decode()
    return common


def error_text(resp: httpx.Response) -> str:
    """把阿里云错误压成一行人话（Message + Code）。"""
    try:
        data = resp.json() or {}
    except Exception:  # noqa: BLE001
        return f"HTTP {resp.status_code} {resp.text[:200]}"
    msg = data.get("Message") or ""
    code = data.get("Code") or ""
    if msg and code and code not in msg:
        return f"{msg}（{code}）"
    return str(msg or code or f"HTTP {resp.status_code}")


def call(config: dict, endpoint: str, action: str, version: str,
         params: dict | None = None, timeout: int = 30) -> dict:
    """调用一次阿里云 RPC 接口，返回 JSON（已去掉 RequestId 之外的包装）。"""
    query = signed_params(config, {"Action": action, "Version": version, **(params or {})})
    try:
        resp = net.get(endpoint, params=query, timeout=timeout)
    except httpx.HTTPError as exc:
        raise AliyunError(f"请求阿里云失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}）") from exc
    if resp.status_code >= 400:
        raise AliyunError(f"阿里云 {action} 失败：{error_text(resp)}")
    try:
        return resp.json() or {}
    except ValueError:
        raise AliyunError(f"阿里云 {action} 返回非 JSON：{resp.text[:200]}")


def test_identity(config: dict) -> str:
    """用 STS GetCallerIdentity 只校验身份（不依赖任何业务权限）。"""
    data = call(config, "https://sts.aliyuncs.com/", "GetCallerIdentity", "2015-04-01")
    who = data.get("Arn") or data.get("AccountId") or "未知账号"
    return f"AccessKey 有效（{who}）"
