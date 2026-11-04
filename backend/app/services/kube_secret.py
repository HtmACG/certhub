"""通用：用 kubeconfig 把证书写进 Kubernetes 的 TLS Secret。

阿里云 ACK / 腾讯云 TKE / 百度云 CCE 都是托管 K8s，控制台都能导出 kubeconfig，
差别只在品牌，所以把「解析 kubeconfig + 鉴权 + upsert Secret + 触发 Ingress 重载」抽到这里，
各厂商插件只负责元数据。
"""
from __future__ import annotations

import base64
import os
import ssl
import tempfile
import time
from typing import Callable

from .deploy import CertContext, DeployError, _cloud_error, _cloud_request


def _decode(value: str | None) -> bytes:
    return base64.b64decode(value or "")


def parse_kubeconfig(text: str) -> dict:
    if not (text or "").strip():
        raise DeployError("授权里没有填 kubeconfig")
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
                          "请重新下载「静态 kubeconfig」再填进来")
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


def _request(kube: dict, cert_param, method: str, url: str, *, body: dict | None = None,
             headers: dict | None = None):
    all_headers = {"Authorization": f"Bearer {kube['token']}"} if kube.get("token") else {}
    all_headers.update(headers or {})
    kwargs = {"headers": all_headers, "verify": kube["verify"]}
    if body is not None:
        kwargs["json"] = body
    if cert_param:
        kwargs["cert"] = cert_param
    return _cloud_request(method, kube["server"] + url, **kwargs)


def deploy_tls_secret(ctx: CertContext, config: dict, log: Callable) -> None:
    """config 需要：kubeconfig / namespace / secretName / ingressNames（可选）"""
    parsed = parse_kubeconfig(str(config.get("kubeconfig") or ""))
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
            with os.fdopen(cert_fd, "wb") as fh:
                fh.write(_decode(cert_data))
            with os.fdopen(key_fd, "wb") as fh:
                fh.write(_decode(key_data))
            cert_param = (cert_path, key_path)

        kube = {"server": parsed["server"], "verify": verify, "token": token}
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
        resp = _request(kube, cert_param, "POST", url, body=body)
        if resp.status_code in (401, 403):
            raise DeployError(f"集群鉴权失败（HTTP {resp.status_code}）：kubeconfig 已过期，"
                              "或没有该命名空间的操作权限")
        if resp.status_code == 409:
            log(f"Secret {namespace}/{name} 已存在，改为更新")
            cur = _request(kube, cert_param, "GET", f"{url}/{name}")
            if cur.status_code >= 400:
                raise DeployError(f"读取 Secret 失败：{_cloud_error(cur)}")
            body["metadata"]["resourceVersion"] = (cur.json() or {}).get(
                "metadata", {}).get("resourceVersion")
            resp = _request(kube, cert_param, "PUT", f"{url}/{name}", body=body)
        if resp.status_code >= 400:
            raise DeployError(f"写入 Secret 失败：{_cloud_error(resp)}")
        log(f"TLS Secret 已更新：{namespace}/{name}")

        ingresses = config.get("ingressNames") or []
        if isinstance(ingresses, str):
            ingresses = [item.strip() for item in ingresses.split(",") if item.strip()]
        stamp = str(int(time.time()))
        for ingress in ingresses:
            ingress = ctx.render(str(ingress))
            patch = {"metadata": {"annotations": {"certd.io/reload-at": stamp}}}
            resp2 = _request(kube, cert_param, "PATCH",
                             f"/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses/{ingress}",
                             body=patch,
                             headers={"Content-Type": "application/merge-patch+json"})
            if resp2.status_code >= 400:
                raise DeployError(f"触发 Ingress {ingress} 重载失败：{_cloud_error(resp2)}")
            log(f"已触发 Ingress {ingress} 重载")
    finally:
        for path in cert_files:
            try:
                os.remove(path)
            except OSError:
                pass
