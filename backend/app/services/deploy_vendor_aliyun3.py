"""阿里云 ACK（容器服务 Kubernetes）证书部署。

ACK 的证书下发就是更新集群里的 `kubernetes.io/tls` Secret：
用控制台导出的 kubeconfig 直连 API Server，写 Secret 后可给 Ingress 打重载注解。
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
        "type": "DeployToAliyunAck",
        "name": "阿里云-部署到ACK",
        "group": "deploy",
        "icon": "cloud",
        "category": "集群",
        "desc": "把证书写进阿里云 ACK 集群的 TLS Secret，可顺带触发 Ingress 重载",
        "logo": "",
        "color": "#ff6a00",
        "inputs": [
            f("accessId", "ACK 授权", "access", accessCategory="cloud",
              accessTypes=["ack"], required=True),
            f("namespace", "命名空间", default="default"),
            f("secretName", "Secret 名称", default="{domain}-tls"),
            f("ingressNames", "Ingress 名称", "tags", default=[],
              helper="可选：证书更新后给这些 Ingress 打时间戳注解，让 Ingress Controller 立即重载"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "ack": {
        "name": "阿里云 ACK",
        "category": "cloud",
        "desc": "ACK 集群的 kubeconfig（证书写入 K8s Secret）",
        "inputs": [
            f("kubeconfig", "kubeconfig", "textarea", required=True,
              helper="ACK 控制台 → 集群信息 → 连接信息 → 复制 kubeconfig"),
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


@_register("DeployToAliyunAck")
def deploy_to_aliyun_ack(ctx: CertContext, config: dict, log: Callable) -> None:
    if not config.get("kubeconfig"):
        raise DeployError("请先在「授权管理」里配置 ACK 的 kubeconfig")
    deploy_tls_secret(ctx, config, log)


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
