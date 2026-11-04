"""雨云（Rainyun）证书更新。

API：https://api.v2.rainyun.com，鉴权头 `X-Api-Key`。
证书中心里的每条记录有 ID，替换时 `PUT /product/sslcenter/{id}` + `{cert, key}`，
站点上引用这张证书的域名会跟着更新（所以任务里选的是「证书 ID」，不是域名）。
"""
from __future__ import annotations

import json
from typing import Callable

from .deploy import CertContext, DeployError, _cloud_request


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToRainyunCdn",
        "name": "雨云-更新证书",
        "group": "deploy",
        "icon": "cloud",
        "category": "云 CDN",
        "desc": "按证书 ID 覆盖雨云证书中心里的证书内容",
        "logo": "",
        "color": "#7c3aed",
        "inputs": [
            f("accessId", "雨云授权", "access", accessCategory="cloud",
              accessTypes=["rainyun"], required=True),
            f("certIds", "证书 ID", "tags", required=True,
              helper="雨云控制台 → SSL 证书里的记录 ID；"
                     "需要先在控制台上传一次证书并关联站点"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "rainyun": {
        "name": "雨云 Rainyun",
        "category": "cloud",
        "desc": "雨云证书中心（API Key）",
        "inputs": [
            f("apiKey", "API Key", "password", required=True,
              helper="https://app.rainyun.com/account/settings/api-key"),
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


def _rainyun_request(config: dict, method: str, path: str, data: dict | None = None) -> dict:
    api_key = str(config.get("apiKey") or "").strip()
    if not api_key:
        raise DeployError("雨云授权缺少 API Key")
    resp = _cloud_request(method.upper(), "https://api.v2.rainyun.com" + path,
                          headers={"X-Api-Key": api_key}, json=data)
    try:
        payload = resp.json()
    except ValueError:
        raise DeployError(f"雨云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code >= 400 or payload.get("code") != 200:
        raise DeployError(f"雨云接口失败：{payload.get('message') or payload}")
    return payload.get("data") or {}


def _as_ids(value) -> list[int]:
    if value is None or value == "":
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    result = []
    for item in items:
        raw = str(item).strip()
        if not raw:
            continue
        try:
            result.append(int(raw))
        except ValueError:
            raise DeployError(f"证书 ID 必须是数字：{raw}")
    return result


@_register("DeployToRainyunCdn")
def deploy_to_rainyun_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    cert_ids = _as_ids(config.get("certIds"))
    if not cert_ids:
        raise DeployError("请选择要更新的雨云证书 ID")

    for cert_id in cert_ids:
        _rainyun_request(config, "PUT", f"/product/sslcenter/{cert_id}",
                         {"cert": ctx.crt, "key": ctx.key})
        log(f"雨云证书 {cert_id} 已更新")
    log("雨云证书更新完成")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
