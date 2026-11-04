"""UCloud CDN / ULB 证书部署（复用 `deploy_vendor_ucloud.ucloud_call` 的签名）。"""
from __future__ import annotations

import base64
import hashlib
import time
from typing import Callable

from .deploy import CertContext, DeployError
from .deploy_vendor_ucloud import _as_list, _cert_name, ucloud_call


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToUcloudCdn",
        "name": "UCloud-部署到CDN",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "上传证书到 UCloud USSL 并更新 CDN 域名的 HTTPS 配置",
        "logo": "",
        "color": "#1f6fe5",
        "inputs": [
            f("accessId", "UCloud 授权", "access", accessCategory="cloud",
              accessTypes=["ucloud"], required=True),
            f("domainList", "CDN 域名", "tags", required=True,
              helper="UCloud CDN 控制台里的加速域名"),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToUcloudUlb",
        "name": "UCloud-部署到负载均衡",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "替换 UCloud ULB / ALB / CLB 的 HTTPS 证书（按证书名称匹配并重新绑定）",
        "logo": "",
        "color": "#1f6fe5",
        "inputs": [
            f("accessId", "UCloud 授权", "access", accessCategory="cloud",
              accessTypes=["ucloud"], required=True),
            f("region", "地域", required=True, default="cn-bj2"),
            f("certNameList", "ULB 证书名称", "tags", required=True,
              helper="ULB 控制台里 HTTPS 监听器用的证书名称；"
                     "不存在时只上传同名证书，需要你到控制台手动绑定一次"),
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


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _upload_ussl(ctx: CertContext, config: dict) -> tuple[str, str]:
    """上传到 USSL，返回 (certId, certName)。"""
    crt_b64 = base64.b64encode(ctx.crt.encode()).decode()
    key_b64 = base64.b64encode(ctx.key.encode()).decode()
    name = _cert_name(ctx, config)
    data = ucloud_call(config, "UploadNormalCertificate", {
        "CertificateName": name,
        "SslPublicKey": crt_b64,
        "SslPrivateKey": key_b64,
        "SslMD5": _md5(crt_b64 + key_b64),
    })
    cert_id = str(data.get("CertificateID") or data.get("CertificateId") or "")
    if not cert_id:
        raise DeployError(f"USSL 上传成功但没有返回证书 ID：{str(data)[:200]}")
    return cert_id, name


@_register("DeployToUcloudCdn")
def deploy_to_ucloud_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    domains = _as_list(config.get("domainList"))
    if not domains:
        raise DeployError("请填写 UCloud CDN 域名")
    cert_id, cert_name = _upload_ussl(ctx, config)
    log(f"USSL 证书上传成功：{cert_name}（ID={cert_id}）")

    for domain in domains:
        info = ucloud_call(config, "GetUcdnDomainConfig", {"Domain": [domain]})
        rows = info.get("DomainList") or []
        conf = next((row for row in rows if row.get("Domain") == domain), None)
        if not conf:
            raise DeployError(f"UCloud CDN 里找不到域名 {domain}")
        body = {
            "DomainId": conf.get("DomainId"),
            "CertName": cert_name,
            "CertId": cert_id,
            "CertType": "ussl",
            "EnableHttp2": conf.get("EnableHttp2") or "0",
            "RedirectHttp2Https": conf.get("RedirectHttp2Https") or "0",
            "TlsVersion": conf.get("TlsVersion") or "tlsv1.0,tlsv1.1,tlsv1.2,tlsv1.3",
        }
        if conf.get("HttpsStatusCn") == "enable":
            body["HttpsStatusCn"] = "enable"
        if conf.get("HttpsStatusAbroad") == "enable":
            body["HttpsStatusAbroad"] = "enable"
        if not body.get("HttpsStatusCn") and not body.get("HttpsStatusAbroad"):
            body["HttpsStatusCn"] = "enable"
        ucloud_call(config, "UpdateUcdnDomainHttpsConfigV2", body)
        log(f"UCloud CDN 域名 {domain} 的 HTTPS 证书已更新")


def _list_ssl(config: dict, region: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        data = ucloud_call(config, "DescribeSSLV2",
                           {"Offset": offset, "Limit": 100}, region=region)
        batch = data.get("DataSet") or []
        rows.extend(batch)
        total = int(data.get("TotalCount") or 0)
        offset += len(batch)
        if not batch or offset >= total:
            break
    return rows


def _upload_ulb(config: dict, region: str, name: str, ctx: CertContext) -> str:
    content = f"{ctx.crt}\n{ctx.key}"
    data = ucloud_call(config, "CreateSSL", {
        "SSLName": name,
        "SSLContent": content,
    }, region=region)
    ssl_id = str(data.get("SSLId") or "")
    if not ssl_id:
        raise DeployError(f"创建 ULB 证书失败：{str(data)[:200]}")
    return ssl_id


@_register("DeployToUcloudUlb")
def deploy_to_ucloud_ulb(ctx: CertContext, config: dict, log: Callable) -> None:
    region = str(config.get("region") or "cn-bj2")
    wanted = _as_list(config.get("certNameList"))
    if not wanted:
        raise DeployError("请填写 ULB 证书名称")

    certs = _list_ssl(config, region)
    by_name = {str(item.get("SSLName")): item for item in certs if item.get("SSLName")}
    now = time.time()

    for name in wanted:
        old = by_name.get(name)
        if not old:
            _upload_ulb(config, region, name, ctx)
            log(f"没有找到 ULB 证书 {name}，已按该名称上传；"
                "请到 ULB 控制台把它绑到 HTTPS 监听器（后续会自动替换）")
            continue

        new_id = _upload_ulb(config, region, f"{name}_{old.get('SSLId')}_{int(now)}", ctx)
        if old.get("Relations"):
            ucloud_call(config, "UpdateSSLBinding", {
                "OldSSLId": old.get("SSLId"), "NewSSLId": new_id,
            }, region=region)
            log(f"ULB 证书绑定已从 {old.get('SSLId')} 切到 {new_id}")
        ucloud_call(config, "UpdateSSLAttribute", {
            "SSLId": new_id, "SSLName": name,
        }, region=region)
        try:
            ucloud_call(config, "DeleteSSL", {"SSLId": old.get("SSLId")}, region=region)
            log(f"旧证书 {old.get('SSLId')} 已删除")
        except DeployError as exc:
            log(f"旧证书删除失败（忽略）：{exc}")
        log(f"ULB 证书 {name} 已替换为 {new_id}")

    # 顺手清掉已过期且没绑定的证书
    for item in certs:
        not_after = item.get("NotAfter")
        if not_after and isinstance(not_after, (int, float)) and not_after < now:
            try:
                ucloud_call(config, "DeleteSSL", {"SSLId": item.get("SSLId")}, region=region)
                log(f"已清理过期证书 {item.get('SSLName')}（{item.get('SSLId')}）")
            except DeployError as exc:
                log(f"清理过期证书失败（忽略）：{exc}")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
