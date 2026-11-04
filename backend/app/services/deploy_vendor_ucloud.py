"""优刻得 UCloud 证书部署：对象存储 US3 / WAF / USSL。

UCloud 的开放 API 是「参数 + SHA1 签名」那一套：
    除 Signature 外的参数按参数名 ASCII 升序，拼成 key+value 串，
    末尾接 API 私钥，做 SHA1 十六进制摘要，放进 Signature 参数。
接口地 https://api.ucloud.cn（可用 baseUrl 覆盖，便于代理/联调）。

三个插件：
- UCloud-部署到对象存储(US3)：UpdateUFileSSLCert，按存储桶的加速域名换证书
- UCloud-部署到WAF：先 AddWafDomainCertificateInfo，再逐个域名 UpdateWafDomainHostInfo
- UCloud-上传到USSL：UploadNormalCertificate，只上传到证书中心
"""
from __future__ import annotations

import base64
import hashlib
from typing import Callable

from .deploy import CertContext, DeployError, _cloud_error, _cloud_request


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToUcloudUs3",
        "name": "UCloud-部署到对象存储(US3)",
        "group": "deploy",
        "icon": "cloud",
        "category": "对象存储",
        "desc": "更新 UCloud 对象存储 US3 存储桶域名的 HTTPS 证书",
        "logo": "",
        "color": "#1f6fe5",
        "inputs": [
            f("accessId", "UCloud 授权", "access", accessCategory="cloud",
              accessTypes=["ucloud"], required=True),
            f("region", "地域", required=True, default="cn-bj2",
              placeholder="cn-bj2", helper="US3 存储桶所在地域，例如 cn-bj2、cn-sh2"),
            f("bucket", "存储桶", required=True, helper="存储桶名称，例如 my-bucket"),
            f("domainList", "域名列表", "tags", required=True,
              helper="存储桶上已绑定的域名，可在控制台自定义域名里查看"),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToUcloudWaf",
        "name": "UCloud-部署到WAF",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "把证书传到 UCloud WAF 并更新到防护域名",
        "logo": "",
        "color": "#1f6fe5",
        "inputs": [
            f("accessId", "UCloud 授权", "access", accessCategory="cloud",
              accessTypes=["ucloud"], required=True),
            f("domainList", "WAF 域名", "tags", required=True,
              helper="UCloud WAF 控制台里的防护域名，例如 www.example.com"),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToUcloudUssl",
        "name": "UCloud-上传到USSL",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "只把证书上传到 UCloud USSL 证书中心（不动任何域名）",
        "logo": "",
        "color": "#1f6fe5",
        "inputs": [
            f("accessId", "UCloud 授权", "access", accessCategory="cloud",
              accessTypes=["ucloud"], required=True),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "ucloud": {
        "name": "优刻得 UCloud",
        "category": "cloud",
        "desc": "UCloud 对象存储 / WAF / USSL 证书部署",
        "inputs": [
            f("publicKey", "公钥", required=True,
              helper="UCloud 控制台 → API 管理（console.ucloud.cn/uaccount/api_manage）"),
            f("privateKey", "私钥", "password", required=True),
            f("projectId", "项目 ID", required=False,
              helper="控制台 → 项目管理 → 项目 ID；默认项目可留空"),
            f("baseUrl", "API 地址", default="https://api.ucloud.cn",
              helper="走代理或联调时改这里"),
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


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def ucloud_call(config: dict, action: str, params: dict | None = None,
                region: str | None = None) -> dict:
    public_key = str(config.get("publicKey") or "").strip()
    private_key = str(config.get("privateKey") or "").strip()
    if not public_key or not private_key:
        raise DeployError("UCloud 授权缺少公钥 / 私钥")

    payload: dict[str, str] = {"Action": action, "PublicKey": public_key}
    project_id = str(config.get("projectId") or "").strip()
    if project_id:
        payload["ProjectId"] = project_id
    if region:
        payload["Region"] = region
    for key, value in (params or {}).items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple)):
            value = ",".join(str(item) for item in value)
        payload[key] = str(value)

    raw = "".join(f"{key}{payload[key]}" for key in sorted(payload))
    payload["Signature"] = hashlib.sha1((raw + private_key).encode("utf-8")).hexdigest()

    base = str(config.get("baseUrl") or "https://api.ucloud.cn").rstrip("/")
    resp = _cloud_request("POST", base + "/", data=payload)
    if resp.status_code >= 400:
        raise DeployError(f"UCloud {action} 失败：{_cloud_error(resp)}")
    try:
        data = resp.json()
    except ValueError:
        raise DeployError(f"UCloud {action} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if int(data.get("RetCode", 0)) != 0:
        raise DeployError(f"UCloud {action} 失败：{data.get('Message') or data}")
    return data


def _cert_name(ctx: CertContext, config: dict) -> str:
    return ctx.render(config.get("certName") or "{domain}-{timestamp}")


@_register("DeployToUcloudUssl")
def deploy_to_ucloud_ussl(ctx: CertContext, config: dict, log: Callable) -> None:
    crt_b64 = base64.b64encode(ctx.crt.encode()).decode()
    key_b64 = base64.b64encode(ctx.key.encode()).decode()
    name = _cert_name(ctx, config)
    data = ucloud_call(config, "UploadNormalCertificate", {
        "CertificateName": name,
        "SslPublicKey": crt_b64,
        "SslPrivateKey": key_b64,
        "SslMD5": _md5(crt_b64 + key_b64),
    })
    cert_id = data.get("CertificateID") or data.get("CertificateId") or ""
    log(f"USSL 证书上传成功：{name}（ID={cert_id or '未返回'}）")


@_register("DeployToUcloudWaf")
def deploy_to_ucloud_waf(ctx: CertContext, config: dict, log: Callable) -> None:
    domains = _as_list(config.get("domainList"))
    if not domains:
        raise DeployError("请填写要更新的 UCloud WAF 域名")
    crt_b64 = base64.b64encode(ctx.crt.encode()).decode()
    key_b64 = base64.b64encode(ctx.key.encode()).decode()
    name = _cert_name(ctx, config)

    added = ucloud_call(config, "AddWafDomainCertificateInfo", {
        "Domain": ",".join([ctx.domain, *ctx.domains]).strip(","),
        "CertificateName": name,
        "SslPublicKey": crt_b64,
        "SslPrivateKey": key_b64,
        "SslMD5": _md5(crt_b64),
        "SslKeyless": "off",
    })
    cert_id = added.get("Id") or added.get("CertificateID") or ""
    if not cert_id:
        raise DeployError(f"WAF 证书添加成功但没有返回 Id：{str(added)[:200]}")
    log(f"WAF 证书已添加，ID={cert_id}")

    for domain in domains:
        info = ucloud_call(config, "DescribeWafDomainHostInfo",
                           {"Limit": 10, "Offset": 0, "FullDomain": domain})
        rows = info.get("DomainHostList") or []
        if not rows:
            raise DeployError(f"UCloud WAF 里找不到域名 {domain}（请先在控制台添加站点）")
        old = rows[0]
        src_ips = [item.get("SrcIP") for item in (old.get("SrcIPInfo") or [])
                   if item.get("SrcIP")]
        ucloud_call(config, "UpdateWafDomainHostInfo", {
            "WorkRegions": old.get("WorkRegions") or "",
            "FullDomain": domain,
            "CertificateID": cert_id,
            "SrcIP": src_ips,
        })
        log(f"WAF 域名 {domain} 证书已更新")


@_register("DeployToUcloudUs3")
def deploy_to_ucloud_us3(ctx: CertContext, config: dict, log: Callable) -> None:
    bucket = str(config.get("bucket") or "").strip()
    region = str(config.get("region") or "").strip()
    domains = _as_list(config.get("domainList"))
    if not bucket:
        raise DeployError("请填写 US3 存储桶名称")
    if not domains:
        raise DeployError("请填写存储桶上已绑定的域名")

    for domain in domains:
        ucloud_call(config, "UpdateUFileSSLCert", {
            "BucketName": bucket,
            "Domain": domain,
            "CertificateName": _cert_name(ctx, config),
            "Certificate": ctx.crt,
            "CertificateKey": ctx.key,
        }, region=region)
        log(f"US3 存储桶 {bucket} 的域名 {domain} 证书已更新")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
