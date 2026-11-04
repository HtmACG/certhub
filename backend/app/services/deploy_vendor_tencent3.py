"""腾讯云 SSL 证书中心：只上传证书，不绑定任何产品。

有些场景（CDN / CLB / 直播 / 网关共用一张证书，或人工到控制台绑定）只需要把证书
托管到腾讯云 SSL，不用改监听器。这里复用 `tencent_ssl.call_api` 的通用签名。
"""
from __future__ import annotations

import time
from typing import Callable

from .deploy import CertContext, DeployError
from .tencent_ssl import TencentSslError, call_api


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToTencentCert",
        "name": "腾讯云-上传证书到SSL",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "只把证书上传到腾讯云 SSL 证书中心（不动 CDN / CLB 等产品）",
        "logo": "",
        "color": "#006eff",
        "inputs": [
            f("accessId", "腾讯云授权", "access", accessCategory="cloud",
              accessTypes=["tencentcloud"], required=True),
            f("certAlias", "证书别名", default="{domain}-{timestamp}"),
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


@_register("DeployToTencentCert")
def deploy_to_tencent_cert(ctx: CertContext, config: dict, log: Callable) -> None:
    alias = ctx.render(config.get("certAlias") or f"{ctx.domain}-{int(time.time())}")
    try:
        data = call_api(config, "ssl.tencentcloudapi.com", "ssl", "2019-12-05",
                        "UploadCertificate", {
                            "CertificatePublicKey": ctx.crt,
                            "CertificatePrivateKey": ctx.key,
                            "Alias": alias,
                        })
    except TencentSslError as exc:
        raise DeployError(str(exc)) from exc
    cert_id = data.get("CertificateId") or ""
    if not cert_id:
        raise DeployError("腾讯云上传成功但没有返回 CertificateId")
    log(f"证书已上传到腾讯云 SSL：{alias}（ID={cert_id}）")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
