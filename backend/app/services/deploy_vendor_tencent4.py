"""腾讯云 TKE（容器服务 Kubernetes）证书部署。

和阿里云 ACK / 百度云 CCE 一样：用 kubeconfig 写 `kubernetes.io/tls` Secret，
可选给 Ingress 打时间戳注解触发重载。实现复用 `kube_secret.deploy_tls_secret`。
"""
from __future__ import annotations

from typing import Callable

from .deploy import CertContext, DeployError
from .kube_secret import deploy_tls_secret


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToTencentTke",
        "name": "腾讯云-部署到TKE",
        "group": "deploy",
        "icon": "cloud",
        "category": "集群",
        "desc": "把证书写进腾讯云 TKE 集群的 TLS Secret，可顺带触发 Ingress 重载",
        "logo": "",
        "color": "#006eff",
        "inputs": [
            f("accessId", "TKE 授权", "access", accessCategory="cloud",
              accessTypes=["tke"], required=True),
            f("namespace", "命名空间", default="default"),
            f("secretName", "Secret 名称", default="{domain}-tls"),
            f("ingressNames", "Ingress 名称", "tags", default=[],
              helper="可选：证书更新后给这些 Ingress 打时间戳注解，让 Ingress Controller 立即重载"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "tke": {
        "name": "腾讯云 TKE",
        "category": "cloud",
        "desc": "TKE 集群的 kubeconfig（证书写入 K8s Secret）",
        "inputs": [
            f("kubeconfig", "kubeconfig", "textarea", required=True,
              helper="TKE 控制台 → 集群 → 基本信息 → 集群凭证 → 复制 kubeconfig"),
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


@_register("DeployToTencentTke")
def deploy_to_tencent_tke(ctx: CertContext, config: dict, log: Callable) -> None:
    if not config.get("kubeconfig"):
        raise DeployError("请先在「授权管理」里配置 TKE 的 kubeconfig")
    deploy_tls_secret(ctx, config, log)


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
