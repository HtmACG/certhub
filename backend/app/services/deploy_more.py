"""面板 / WAF / 其它云服务的证书部署。

这里放三块：
- 长亭雷池 WAF（SafeLine）：API Token 鉴权，更新控制台与防护站点的证书
- 又拍云 CDN / USS：控制台账号登录换 Cookie，上传证书后绑定加速域名
- 腾讯云 CLB 负载均衡：先传证书到 SSL 证书中心，再绑定到监听器

所有 handler 统一签名 handler(ctx, config, log)，注册进 deploy.DEPLOY_HANDLERS。
"""
from __future__ import annotations

import ssl as ssl_module
import time
from typing import Callable

import httpx

from .deploy import CertContext, DeployError, _cloud_error, _cloud_request
from .tencent_ssl import TencentSslError, call_api

HANDLERS: dict[str, Callable] = {}


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


# ================================================================ 长亭雷池 WAF
def safeline_verify(config: dict):
    """雷池常见用自签证书，默认跳过校验；填了 CA 就按 CA 校。"""
    if config.get("insecure", True):
        return False
    ca = str(config.get("caCert") or "").strip()
    if ca:
        try:
            return ssl_module.create_default_context(cadata=ca)
        except ssl_module.SSLError as exc:
            raise DeployError(f"雷池 CA 证书解析失败：{exc}") from exc
    return True


def safeline_request(config: dict, method: str, path: str, body: dict | None = None) -> dict:
    base = (config.get("baseUrl") or config.get("url") or "").rstrip("/")
    token = config.get("apiToken") or ""
    if not base:
        raise DeployError("雷池授权缺少访问地址（形如 https://host:9443）")
    if not token:
        raise DeployError("雷池授权缺少 ApiToken（控制台 → 系统设置 → 开放接口）")

    resp = _cloud_request(method.upper(), base + path,
                          json=body if method.upper() != "GET" else None,
                          headers={"X-SLCE-API-TOKEN": token,
                                   "Content-Type": "application/json"},
                          verify=safeline_verify(config))
    try:
        data = resp.json() or {}
    except ValueError:
        raise DeployError(f"雷池返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if data.get("err"):
        raise DeployError(f"雷池接口失败：{data.get('msg') or data}")
    return data.get("data") or {}


def safeline_certs(config: dict) -> list[dict]:
    data = safeline_request(config, "GET", "/api/open/cert")
    return data.get("nodes") or []


@_register("DeployToSafeline")
def deploy_to_safeline(ctx: CertContext, config: dict, log: Callable) -> None:
    """更新雷池的证书。

    雷池的证书是用「ID」引用的：id=0 表示新增一张，之后要回到插件配置里
    改成这张新证书的 ID，后续才会自动更新同一张证书（控制台/站点上引用的也是它）。
    """
    ids = _as_list(config.get("certIds")) or ["0"]
    for raw in ids:
        try:
            cert_id = int(str(raw).strip())
        except ValueError:
            raise DeployError(f"雷池证书 ID 必须是数字：{raw}")
        body: dict = {"manual": {"crt": ctx.crt, "key": ctx.key}, "type": 2}
        action = "新增"
        if cert_id > 0:
            body["id"] = cert_id
            action = "更新"
        data = safeline_request(config, "POST", "/api/open/cert", body)
        new_id = data if isinstance(data, (int, str)) else (data or {}).get("id", "")
        log(f"雷池证书 {cert_id} {action}成功{('，新 ID=' + str(new_id)) if new_id else ''}")


# ================================================================ 又拍云
def _upyun_base(config: dict) -> str:
    """又拍云控制台地址；baseUrl 可覆盖（自建反代 / 测试用）。"""
    return (config.get("baseUrl") or "https://console.upyun.com").rstrip("/")


def upyun_login(config: dict) -> str:
    """用控制台账号换 Cookie（后续接口都靠它维持会话）。"""
    username = config.get("username") or ""
    password = config.get("password") or ""
    if not username or not password:
        raise DeployError("又拍云授权缺少账号或密码")

    resp = _cloud_request("POST", _upyun_base(config) + "/accounts/signin/",
                          data={"username": username, "password": password})
    try:
        body = resp.json()
    except ValueError:
        raise DeployError(f"又拍云登录返回非 JSON（HTTP {resp.status_code}）")
    if (body or {}).get("errors"):
        raise DeployError(f"又拍云登录失败：{body.get('msg') or body.get('errors')}")
    payload = (body or {}).get("data") or {}
    if payload.get("error_code"):
        raise DeployError(f"又拍云登录失败：{payload.get('message')}")

    cookies = resp.headers.get("set-cookie") or ""
    if not cookies:
        raise DeployError("又拍云登录成功但没有返回 Cookie")
    # 只取 name=value 部分，避免把 Path/HttpOnly 一起塞回请求头
    pairs = [part.split(";", 1)[0].strip() for part in cookies.split(",") if "=" in part]
    return "; ".join(pair for pair in pairs if pair)


def upyun_request(config: dict, method: str, url: str, cookie: str,
                  body: dict | None = None, params: dict | None = None) -> dict:
    resp = _cloud_request(method.upper(), url, json=body if method.upper() != "GET" else None,
                          params=params, headers={"Cookie": cookie})
    try:
        data = resp.json() or {}
    except ValueError:
        raise DeployError(f"又拍云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    payload = data.get("data") or {}
    if data.get("errors") or payload.get("error_code"):
        message = str(data.get("msg") or payload.get("message") or data)
        # 重复绑定同一张证书不算失败
        if "domain has been bound" in message.lower():
            return payload
        raise DeployError(f"又拍云接口失败：{message[:200]}")
    return payload


def upyun_domains(config: dict) -> list[dict]:
    cookie = upyun_login(config)
    payload = upyun_request(
        config, "GET", _upyun_base(config) + "/api/account/domains/", cookie,
        params={"limit": 1000, "business_type": "file", "security_cdn": "false",
                "websocket": "false", "key": "", "domain": ""})
    return payload.get("domains") or []


@_register("DeployToUpyun")
def deploy_to_upyun(ctx: CertContext, config: dict, log: Callable) -> None:
    """又拍云 CDN / USS：上传证书 → 绑定加速域名 → 可选强制 HTTPS。"""
    domains = _as_list(config.get("domains")) or [ctx.domain]
    force_https = str(config.get("forceHttps") or "keep").lower()

    cookie = upyun_login(config)
    log("又拍云登录成功")

    payload = upyun_request(config, "POST", _upyun_base(config) + "/api/https/certificate/",
                            cookie, body={"certificate": ctx.crt, "private_key": ctx.key})
    cert_id = (payload.get("result") or {}).get("certificate_id")
    if not cert_id:
        raise DeployError(f"又拍云上传证书失败：{str(payload)[:200]}")
    log(f"又拍云证书上传成功，ID={cert_id}")

    for domain in domains:
        upyun_request(config, "POST", _upyun_base(config) + "/api/https/migrate/domain",
                      cookie, body={"crt_id": cert_id, "domain_name": domain})
        log(f"又拍云域名 {domain} 已绑定证书 {cert_id}")

        manage: dict = {"certificate_id": cert_id, "domain": domain}
        if force_https in ("true", "false"):
            manage["force_https"] = force_https == "true"
        upyun_request(config, "POST", _upyun_base(config) + "/api/https/certificate/manager",
                      cookie, body=manage)
        if "force_https" in manage:
            log(f"又拍云域名 {domain} 已设置强制 HTTPS={manage['force_https']}")


# ================================================================ 腾讯云 CLB
def tencent_upload_cert(config: dict, alias: str, crt: str, key: str) -> str:
    """把证书传到腾讯云 SSL 证书中心，返回 CertificateId（CLB 只能引用已托管的证书）。"""
    try:
        data = call_api(config, "ssl.tencentcloudapi.com", "ssl", "2019-12-05",
                        "UploadCertificate", {
                            "CertificatePublicKey": crt,
                            "CertificatePrivateKey": key,
                            "Alias": alias,
                        })
    except TencentSslError as exc:
        raise DeployError(str(exc)) from exc
    cert_id = data.get("CertificateId") or ""
    if not cert_id:
        raise DeployError("腾讯云上传证书成功但没有返回 CertificateId")
    return cert_id


@_register("DeployToTencentClb")
def deploy_to_tencent_clb(ctx: CertContext, config: dict, log: Callable) -> None:
    """腾讯云 CLB：上传证书到 SSL 证书中心，再绑定到指定监听器。"""
    lb_id = config.get("loadBalancerId") or ""
    listener_id = config.get("listenerId") or ""
    if not lb_id or not listener_id:
        raise DeployError("腾讯云 CLB 部署需要填写负载均衡实例 ID 与监听器 ID")

    alias = ctx.render(config.get("certAlias") or "certd-{domain}-{timestamp}")
    cert_id = config.get("certId") or tencent_upload_cert(config, alias, ctx.crt, ctx.key)
    log(f"腾讯云证书 ID={cert_id}")

    body = {"CertificateId": str(cert_id), "LoadBalancerId": lb_id, "ListenerId": listener_id}
    domain = ctx.render(config.get("domain") or "")
    if domain:
        body["Domain"] = domain
    try:
        call_api(config, "clb.tencentcloudapi.com", "clb", "2018-03-17",
                 "ModifyCertificate", body)
    except TencentSslError as exc:
        raise DeployError(str(exc)) from exc
    log(f"腾讯云 CLB 监听器 {listener_id} 证书绑定成功")


# ================================================================ 腾讯云 EdgeOne
TEO_HOST = "teo.tencentcloudapi.com"
TEO_SERVICE = "teo"
TEO_VERSION = "2022-09-01"

#: 腾讯云 EdgeOne 常见错误码 → 一句中文结论（原始错误仍附在括号里，便于排障）
_TEO_ERROR_HINTS = {
    "AuthFailure.SecretIdNotFound":
        "腾讯云鉴权失败：SecretId 不存在，请检查授权里的 SecretId / SecretKey",
    "AuthFailure.SignatureFailure":
        "腾讯云鉴权失败：SecretKey 不正确，请检查授权里的 SecretId / SecretKey",
    "UnauthorizedOperation.CamUnauthorized":
        "腾讯云子账号没有 EdgeOne 权限，请到 CAM 给这个子账号授权 QcloudTEOFullAccess",
    "UnauthorizedOperation.NoPermission":
        "腾讯云子账号没有 EdgeOne 权限，请到 CAM 给这个子账号授权 QcloudTEOFullAccess",
    "ResourceUnavailable.ZoneNotFound": "EdgeOne 站点不存在或不属于这个账号",
    "ResourceUnavailable.HostNotFound": "EdgeOne 里找不到这个加速域名（请先在控制台添加）",
    "FailedOperation.CertificateNotFound": "SSL 证书中心里找不到这个证书 ID",
    "FailedOperation.CertificateHasExpired": "证书已过期，EdgeOne 拒绝下发",
    "InvalidParameter.CertNotMatchDomain": "证书与域名不匹配（证书 SAN 里没有这个域名）",
}


def _teo_call(config: dict, action: str, body: dict | None = None) -> dict:
    """调用 EdgeOne（teo）接口；错误翻成中文结论，别把英文 code 原样甩给用户。"""
    try:
        return call_api(config, TEO_HOST, TEO_SERVICE, TEO_VERSION, action, body)
    except TencentSslError as exc:
        text = str(exc)
        for code, hint in _TEO_ERROR_HINTS.items():
            if code in text:
                raise DeployError(f"{hint}（{text}）") from exc
        raise DeployError(text) from exc


def _teo_list(config: dict, action: str, body: dict, key: str, page_size: int) -> list[dict]:
    """EdgeOne 列表接口统一分页：Some 接口默认只返回 20 条，这里必须翻完。"""
    rows: list[dict] = []
    offset = 0
    while True:
        payload = dict(body or {})
        payload["Offset"] = offset
        payload["Limit"] = page_size
        data = _teo_call(config, action, payload)
        batch = data.get(key) or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return rows


def tencent_edgeone_domain_rows(config: dict) -> list[dict]:
    """列出账号下所有 EdgeOne 站点的加速域名。

    返回 ``[{"domain": ..., "zoneId": ..., "zoneName": ...}]``。
    站点少的时候一次拉完最省事；站点/域名都按 100/200 分页，不会只拿到第一页。
    """
    zones = _teo_list(config, "DescribeZones", {}, "Zones", 100)
    rows: list[dict] = []
    for zone in zones:
        zone_id = str(zone.get("ZoneId") or zone.get("Id") or "").strip()
        if not zone_id:
            continue
        zone_name = str(zone.get("ZoneName") or zone.get("Name") or zone_id).strip()
        for item in _teo_list(config, "DescribeAccelerationDomains",
                              {"ZoneId": zone_id}, "AccelerationDomains", 200):
            domain = str(item.get("DomainName") or "").strip()
            if domain:
                rows.append({"domain": domain, "zoneId": zone_id, "zoneName": zone_name})
    return rows


@_register("DeployToTencentEdgeOne")
def deploy_to_tencent_edgeone(ctx: CertContext, config: dict, log: Callable) -> None:
    """腾讯云 EdgeOne：先把证书传到 SSL 证书中心，再按站点分组调 ModifyHostsCertificate。

    EdgeOne 的接口只认 SSL 证书 ID（ServerCertInfo.CertId），不能像 CDN 那样
    直接内联证书内容；一个 ZoneId 下可以一次改多个 Hosts，所以按站点分组下发。
    站点由加速域名反查（DescribeZones + DescribeAccelerationDomains），
    用户只需要选域名，不必再去抄 ZoneId。
    """
    domains = _as_list(config.get("domain")) or [ctx.domain]
    domains = [ctx.render(domain) for domain in domains]
    if not domains:
        raise DeployError("腾讯云 EdgeOne 部署需要填写加速域名")

    cert_id = str(config.get("certId") or "").strip()
    if cert_id:
        log(f"复用腾讯云 SSL 证书 ID={cert_id}")
    else:
        alias = ctx.render(config.get("certName") or "certd-{domain}-{timestamp}")
        cert_id = tencent_upload_cert(config, alias, ctx.crt, ctx.key)
        log(f"证书已上传到腾讯云 SSL 证书中心，CertId={cert_id}")

    rows = tencent_edgeone_domain_rows(config)
    zone_of = {row["domain"]: row for row in rows}
    missing = [domain for domain in domains if domain not in zone_of]
    if missing:
        raise DeployError("EdgeOne 里找不到加速域名：" + "、".join(missing)
                          + "（请先在 EdgeOne 控制台添加站点和加速域名）")

    grouped: dict[tuple[str, str], list[str]] = {}
    for domain in domains:
        row = zone_of[domain]
        grouped.setdefault((row["zoneId"], row["zoneName"]), []).append(domain)

    for (zone_id, zone_name), hosts in grouped.items():
        result = _teo_call(config, "ModifyHostsCertificate", {
            "ZoneId": zone_id,
            "Hosts": hosts,
            "Mode": "sslcert",
            "ServerCertInfo": [{"CertId": cert_id}],
        })
        log(f"EdgeOne 站点「{zone_name}」域名 {', '.join(hosts)} 证书部署成功"
            f"（RequestId={result.get('RequestId') or '-'}）")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
