"""百度智能云证书管理（CERT）：上传 / 替换证书。

接口（按 bce-sdk-go 的 CERT 文档）：
- Endpoint：`certificate.baidubce.com`，BCE 签名（复用 `baiducloud._sign`，只是换 host）
- 新建：`POST /v1/certificate`，body 里证书/私钥/证书链都是 **Base64**
- 替换：`PUT /v1/certificate/{certId}`（证书 ID 不变，适合续期）
"""
from __future__ import annotations

import base64
import re
from typing import Callable

from . import baiducloud
from .baiducloud import BaiduError
from .deploy import CertContext, DeployError


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToBaiduCert",
        "name": "百度云-上传到证书托管",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "把证书上传到百度智能云证书管理（CERT），供 CDN / BLB 引用",
        "logo": "",
        "color": "#2932e1",
        "inputs": [
            f("accessId", "百度云授权", "access", accessCategory="cloud",
              accessTypes=["baiducloud"], required=True),
            f("certName", "证书名称", default="{domain}-{timestamp}",
              helper="字母开头，只允许字母、数字、- / .，最长 65 个字符"),
            f("certId", "已有证书 ID", default="",
              helper="填了就是「替换证书内容」（续期场景，ID 不变）；留空则新建一张"),
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


def _split_chain(crt: str) -> tuple[str, str]:
    blocks = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                        crt or "", re.S)
    if not blocks:
        return crt or "", ""
    return blocks[0], "\n".join(blocks[1:])


def _b64(text: str) -> str:
    return base64.b64encode((text or "").encode()).decode()


@_register("DeployToBaiduCert")
def deploy_to_baidu_cert(ctx: CertContext, config: dict, log: Callable) -> None:
    name = ctx.render(config.get("certName") or "{domain}-{timestamp}")[:65]
    if not name:
        raise DeployError("请填写证书名称")
    leaf, chain = _split_chain(ctx.crt)
    body = {
        "certName": name,
        "certServerData": _b64(leaf),
        "certPrivateData": _b64(ctx.key),
        "certLinkData": _b64(chain) if chain else "",
    }

    cert_id = str(config.get("certId") or "").strip()
    try:
        if cert_id:
            data = baiducloud.call(config, "PUT", f"/v1/certificate/{cert_id}",
                                   body=body, host="certificate.baidubce.com")
            log(f"证书已替换：{name}（ID={cert_id}）")
            return
        data = baiducloud.call(config, "POST", "/v1/certificate",
                               body=body, host="certificate.baidubce.com")
    except BaiduError as exc:
        raise DeployError(str(exc)) from exc

    new_id = str(data.get("certId") or data.get("CertId") or "")
    log(f"证书已上传到百度云证书管理：{name}（ID={new_id or '未返回'}）")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
