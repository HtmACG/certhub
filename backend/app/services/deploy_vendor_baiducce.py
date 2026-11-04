"""百度智能云 CCE（Kubernetes）证书部署。

CCE 的证书下发本质是更新集群里的 `kubernetes.io/tls` Secret，
所以这里用控制台导出的 kubeconfig 直连 API Server：
- 支持 token，以及 client-certificate-data / client-key-data 两种鉴权；
- Secret 不存在就创建，存在就按 resourceVersion 整体替换；
- 可选给 Ingress 打时间戳注解，触发 Nginx Ingress Controller 重新加载证书。

kubeconfig 里如果用的是 exec / auth-provider 这类动态凭据，这里不支持，会直接给出中文提示。
"""
from __future__ import annotations

import base64
import ssl
import tempfile
import time
from typing import Callable

from .deploy import CertContext, DeployError, _cloud_error, _cloud_request


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToBaiduCce",
        "name": "百度云-部署到CCE",
        "group": "deploy",
        "icon": "cloud",
        "category": "集群",
        "desc": "把证书写进百度智能云 CCE 集群的 TLS Secret，可顺带给 Ingress 打重载注解",
        "logo": "",
        "color": "#2932e1",
        "inputs": [
            f("accessId", "CCE 授权", "access", accessCategory="cloud",
              accessTypes=["baiducce"], required=True),
            f("namespace", "命名空间", default="default"),
            f("secretName", "Secret 名称", default="{domain}-tls"),
            f("ingressNames", "Ingress 名称", "tags", default=[],
              helper="可选：证书更新后给这些 Ingress 打时间戳注解，让 Ingress Controller 立即重载"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {
    "baiducce": {
        "name": "百度云 CCE",
        "category": "cloud",
        "desc": "CCE 集群的 kubeconfig（证书写入 K8s Secret）",
        "inputs": [
            f("kubeconfig", "kubeconfig", "textarea", required=True,
              helper="CCE 控制台 → 集群 → 连接信息 → 复制 kubeconfig（含 server / CA / 客户端证书）"),
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


def _decode(value: str | None) -> bytes:
    return base64.b64decode(value or "")


def _parse_kubeconfig(text: str) -> dict:
    if not text.strip():
        raise DeployError("CCE 授权里没有填 kubeconfig")
    try:
        import yaml
    except Exception as exc:  # pragma: no cover
        raise DeployError(f"解析 kubeconfig 需要 PyYAML：{exc}") from exc
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        raise DeployError(f"kubeconfig 不是合法 YAML：{exc}") from exc
    if not isinstance(data, dict):
        raise DeployError("kubeconfig 内容格式不对")

    contexts = {item.get("name"): item.get("context") or {} for item in data.get("contexts") or []}
    clusters = {item.get("name"): item.get("cluster") or {} for item in data.get("clusters") or []}
    users = {item.get("name"): item.get("user") or {} for item in data.get("users") or []}

    current = data.get("current-context") or ""
    context = contexts.get(current) or {}
    if not context:
        raise DeployError(f"kubeconfig 里找不到当前上下文「{current}」")

    cluster = clusters.get(context.get("cluster")) or {}
    user = users.get(context.get("user")) or {}
    server = str(cluster.get("server") or "").rstrip("/")
    if not server:
        raise DeployError("kubeconfig 里没有 API Server 地址（cluster.server）")
    if user.get("exec") or user.get("auth-provider"):
        raise DeployError("kubeconfig 用的是 exec / auth-provider 动态凭据，暂不支持；"
                          "请在 CCE 控制台重新下载「静态 kubeconfig」再填进来")
    return {"server": server, "cluster": cluster, "user": user,
            "namespace": context.get("namespace") or ""}


def _build_verify(cluster: dict):
    if cluster.get("insecure-skip-tls-verify"):
        return False
    ca_data = cluster.get("certificate-authority-data")
    ca_file = cluster.get("certificate-authority")
    try:
        if ca_data:
            return ssl.create_default_context(cadata=base64.b64decode(ca_data).decode())
        if ca_file:
            with open(ca_file, "rb") as fh:
                return ssl.create_default_context(cadata=fh.read().decode())
    except Exception as exc:
        raise DeployError(f"集群 CA 解析失败：{exc}") from exc
    return True


def _k8s_request(config: dict, method: str, url: str, *, body: dict | None = None,
                 headers: dict | None = None, verify=None, cert=None):
    kube = config["_kube"]
    all_headers = {"Authorization": f"Bearer {kube['token']}"} if kube.get("token") else {}
    all_headers.update(headers or {})
    kwargs = {"headers": all_headers, "verify": verify if verify is not None else kube["verify"]}
    if body is not None:
        kwargs["json"] = body
    if cert:
        kwargs["cert"] = cert
    return _cloud_request(method, kube["server"] + url, **kwargs)


@_register("DeployToBaiduCce")
def deploy_to_baiducce(ctx: CertContext, config: dict, log: Callable) -> None:
    parsed = _parse_kubeconfig(str(config.get("kubeconfig") or ""))
    cluster, user = parsed["cluster"], parsed["user"]
    verify = _build_verify(cluster)
    token = user.get("token") or ""

    cert_files: list[str] = []
    cert_param = None
    try:
        if not token:
            cert_data = user.get("client-certificate-data")
            key_data = user.get("client-key-data")
            if not cert_data or not key_data:
                raise DeployError("kubeconfig 里既没有 token，也没有客户端证书，无法鉴权")
            cert_fd, cert_path = tempfile.mkstemp(suffix=".crt")
            key_fd, key_path = tempfile.mkstemp(suffix=".key")
            cert_files = [cert_path, key_path]
            with __import__("os").fdopen(cert_fd, "wb") as fh:
                fh.write(_decode(cert_data))
            with __import__("os").fdopen(key_fd, "wb") as fh:
                fh.write(_decode(key_data))
            cert_param = (cert_path, key_path)

        config["_kube"] = {"server": parsed["server"], "verify": verify,
                           "token": token, "cert": cert_param}
        namespace = ctx.render(config.get("namespace") or parsed["namespace"] or "default")
        name = ctx.render(config.get("secretName") or f"{ctx.domain.replace('*', 'wildcard')}-tls")

        body = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": namespace},
            "type": "kubernetes.io/tls",
            "data": {
                "tls.crt": base64.b64encode(ctx.crt.encode()).decode(),
                "tls.key": base64.b64encode(ctx.key.encode()).decode(),
            },
        }
        url = f"/api/v1/namespaces/{namespace}/secrets"
        resp = _k8s_request(config, "POST", url, body=body, cert=cert_param)
        if resp.status_code == 401 or resp.status_code == 403:
            raise DeployError(f"CCE 鉴权失败（HTTP {resp.status_code}）："
                              "kubeconfig 已过期，或没有该命名空间的操作权限")
        if resp.status_code == 409:
            log(f"Secret {namespace}/{name} 已存在，改为更新")
            cur = _k8s_request(config, "GET", f"{url}/{name}", cert=cert_param)
            if cur.status_code >= 400:
                raise DeployError(f"读取 Secret 失败：{_cloud_error(cur)}")
            body["metadata"]["resourceVersion"] = (cur.json() or {}).get(
                "metadata", {}).get("resourceVersion")
            resp = _k8s_request(config, "PUT", f"{url}/{name}", body=body, cert=cert_param)
        if resp.status_code >= 400:
            raise DeployError(f"写入 Secret 失败：{_cloud_error(resp)}")
        log(f"CCE Secret 已更新：{namespace}/{name}")

        ingresses = config.get("ingressNames") or []
        if isinstance(ingresses, str):
            ingresses = [item.strip() for item in ingresses.split(",") if item.strip()]
        if ingresses:
            stamp = str(int(time.time()))
            for ingress in ingresses:
                ingress = ctx.render(str(ingress))
                patch = {"metadata": {"annotations": {"certd.io/reload-at": stamp}}}
                resp2 = _k8s_request(
                    config, "PATCH",
                    f"/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses/{ingress}",
                    body=patch, cert=cert_param,
                    headers={"Content-Type": "application/merge-patch+json"})
                if resp2.status_code >= 400:
                    raise DeployError(f"触发 Ingress {ingress} 重载失败：{_cloud_error(resp2)}")
                log(f"已触发 Ingress {ingress} 重载")
        log("百度云 CCE 证书部署完成")
    finally:
        import os

        for path in cert_files:
            try:
                os.remove(path)
            except OSError:
                pass


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
