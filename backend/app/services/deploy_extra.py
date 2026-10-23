"""
补充部署插件（第二批）
=========================================================
上游 certd 的「选择任务类型」里还有几类本系统没有的任务，这里补齐：

- 上传证书到 FTP（FTP / 显式 TLS）
- 执行远程主机命令（SSH，不需要传证书的运维场景）
- 等待（流水线里排顺序 / 等 CDN 生效用）
- 部署到 K8s Ingress（写 TLS Secret 并把 Ingress 的 spec.tls 指过去）
- 上传证书到 AWS ACM（ALB / API Gateway 之类自取）
- 数据备份（把本次证书归档到本机备份目录，留一份可回滚）

统一签名 handler(ctx, config, log)，注册进 deploy.DEPLOY_HANDLERS。
"""
from __future__ import annotations

import io
import json
import posixpath
import ssl
import time
import zipfile
from pathlib import Path
from typing import Callable

from .deploy import CertContext, DeployError, _ssh_client

HANDLERS: dict[str, Callable] = {}


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


def _cert_files(ctx: CertContext, config: dict) -> list[tuple[str, str]]:
    """按配置凑出要上传的文件：[(文件名, 内容)]。

    证书 / 私钥默认都传，PFX 只有填了文件名才传（需要密码，不是谁都想要）。
    """
    files = [
        (ctx.render(config.get("certName") or "{domain}.crt"), ctx.crt),
        (ctx.render(config.get("keyName") or "{domain}.key"), ctx.key),
    ]
    pfx_name = (config.get("pfxName") or "").strip()
    if pfx_name and ctx.pfx:
        files.append((ctx.render(pfx_name), ctx.pfx.decode("latin-1")))
    return files


# ================================================================ FTP
@_register("DeployToFtp")
def deploy_to_ftp(ctx: CertContext, config: dict, log: Callable) -> None:
    """上传证书到 FTP / FTPS 服务器（很多虚拟主机只给 FTP，只能走这条路）。"""
    import ftplib

    host = (config.get("host") or "").strip()
    if not host:
        raise DeployError("未配置 FTP 服务器地址")
    port = int(config.get("port") or 21)
    user = config.get("username") or "anonymous"
    password = config.get("password") or ""
    use_tls = (config.get("tls") or "none").lower() == "explicit"

    log(f"连接 FTP {host}:{port}（{'FTPS 显式加密' if use_tls else '明文 FTP'}）")
    conn: ftplib.FTP = ftplib.FTP_TLS() if use_tls else ftplib.FTP()
    try:
        conn.encoding = "utf-8"
        conn.connect(host, port, timeout=30)
        conn.login(user, password)
        if use_tls:
            # 登录走 AUTH TLS 之后，数据通道也要保护，否则部分服务器直接拒绝传输
            conn.prot_p()  # type: ignore[attr-defined]
        conn.set_pasv(bool(config.get("passive", True)))

        # 逐级进入目录，不存在就建（FTP 没有 mkdir -p）
        for part in [p for p in ctx.render(config.get("dir") or "certs").split("/") if p]:
            try:
                conn.cwd(part)
            except ftplib.error_perm:
                conn.mkd(part)
                conn.cwd(part)

        for name, content in _cert_files(ctx, config):
            payload = content.encode("utf-8") if isinstance(content, str) else content
            conn.storbinary(f"STOR {posixpath.basename(name)}", io.BytesIO(payload))
            log(f"已上传 {posixpath.basename(name)}")
    except ftplib.all_errors as exc:  # type: ignore[attr-defined]
        raise DeployError(f"FTP 操作失败：{exc}") from exc
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    log("FTP 证书上传完成")


# ================================================================ 远程命令
@_register("DeployRunCommand")
def run_remote_command(ctx: CertContext, config: dict, log: Callable) -> None:
    """在远程主机上执行命令（证书已由别的任务放好，这里只负责重载服务等动作）。"""
    command = ctx.render((config.get("command") or "").strip())
    if not command:
        raise DeployError("未填写要执行的命令")
    timeout = int(config.get("timeout") or 120)

    log(f"在 {config.get('host') or '主机'} 执行命令")
    client = _ssh_client(config)
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
    finally:
        client.close()

    for line in out.splitlines():
        log(line)
    if err.strip():
        log(f"[stderr] {err.strip()[:500]}")
    if code != 0:
        raise DeployError(f"命令返回非 0（退出码 {code}）："
                          f"{(err.strip() or command)[:200]}")
    log("远程命令执行完成")


# ================================================================ 等待
@_register("DeployWait")
def deploy_wait(ctx: CertContext, config: dict, log: Callable) -> None:
    """等待若干秒：证书推完 CDN 需要时间，后面的任务可以插这个排节奏。"""
    seconds = int(config.get("seconds") or 30)
    seconds = max(0, min(seconds, 3600))
    log(f"等待 {seconds} 秒后继续")
    time.sleep(seconds)


# ================================================================ K8s Ingress
def _k8s_conn(config: dict) -> tuple[str, bool | ssl.SSLContext, dict]:
    """K8s API 连接信息：地址 / TLS 校验方式 / 鉴权头（与 Secret 插件同一套规则）。"""
    base = (config.get("apiServer") or config.get("apiUrl") or "").rstrip("/")
    if not base:
        raise DeployError("未配置 Kubernetes API 地址")
    token = config.get("token") or ""
    if not token:
        raise DeployError("未配置 Kubernetes Token")

    ca_cert = str(config.get("caCert") or "").strip()
    if config.get("insecure", True):
        verify: bool | ssl.SSLContext = False
    elif ca_cert:
        try:
            verify = ssl.create_default_context(cadata=ca_cert)
        except ssl.SSLError as exc:
            raise DeployError(f"集群 CA 证书解析失败：{exc}") from exc
    else:
        verify = True
    return base, verify, {"Authorization": f"Bearer {token}"}


@_register("DeployToK8sIngress")
def deploy_to_k8s_ingress(ctx: CertContext, config: dict, log: Callable) -> None:
    """部署到 K8s Ingress：写 TLS Secret，再把 Ingress 的 spec.tls 指向它。"""
    from . import deploy_ext

    namespace = ctx.render(config.get("namespace") or "default")
    secret = ctx.render(config.get("secretName") or f"{ctx.domain.replace('*', 'wildcard')}-tls")
    ingress = ctx.render(config.get("ingressName") or "")
    if not ingress:
        raise DeployError("未填写 Ingress 名称")

    # 1) 写 Secret：直接复用「部署到 K8s Secret」的实现，两条路径行为保持一致
    deploy_ext.deploy_to_k8s_secret(
        ctx,
        {**config, "namespace": namespace, "secretName": secret, "ingressNames": []},
        log,
    )

    # 2) 把 Ingress 的 TLS 指向这个 Secret（merge patch 里 patchStrategy 是 replace）
    base, verify, headers = _k8s_conn(config)
    hosts = config.get("hosts") or []
    if isinstance(hosts, str):
        hosts = [item.strip() for item in hosts.split(",") if item.strip()]
    tls_entry: dict = {"secretName": secret}
    if hosts:
        tls_entry["hosts"] = list(hosts)

    url = f"{base}/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses/{ingress}"
    resp = deploy_ext._panel_request(
        "PATCH", url, timeout=30, verify=verify,
        headers={**headers, "Content-Type": "application/merge-patch+json"},
        json={"spec": {"tls": [tls_entry]}},
    )
    if resp.status_code >= 400:
        raise DeployError(f"更新 Ingress {ingress} 的 TLS 失败：{deploy_ext._cloud_error(resp)}")
    log(f"Ingress {namespace}/{ingress} 已指向 Secret {secret}")


# ================================================================ AWS ACM
@_register("DeployToAwsAcm")
def deploy_to_aws_acm(ctx: CertContext, config: dict, log: Callable) -> None:
    """把证书导入 AWS ACM（ALB / API Gateway / CloudFront 都从 ACM 取证书）。

    CloudFront 只认 us-east-1 的证书，所以区域可填；顺手给证书打几个标签，
    免得 ACM 列表里一堆无主证书分不清是哪条流水线传的。
    """
    from .deploy_ext import _aws_sigv4, _cloud_error, _cloud_request

    ak = config.get("accessKeyId") or ""
    sk = config.get("secretAccessKey") or config.get("secretKey") or ""
    if not ak or not sk:
        raise DeployError("AWS 授权缺少 AccessKey / SecretAccessKey")
    region = (config.get("region") or "us-east-1").strip()
    name = ctx.render(config.get("certName") or "{domain}")

    body = json.dumps({
        "Certificate": ctx.crt,
        "PrivateKey": ctx.key,
        "CertificateChain": config.get("certChain") or "",
        "Tags": [
            {"Key": "Name", "Value": name},
            {"Key": "ManagedBy", "Value": "CertHub"},
        ],
    }).encode()
    host = f"acm.{region}.amazonaws.com"
    headers = _aws_sigv4("POST", host, "/", body, ak=ak, sk=sk, region=region,
                         service="acm", content_type="application/x-amz-json-1.1")
    headers["X-Amz-Target"] = "CertificateManager.ImportCertificate"

    log(f"导入证书到 ACM（{region}）")
    resp = _cloud_request("POST", f"https://{host}/", content=body, headers=headers)
    if resp.status_code >= 300:
        raise DeployError(f"ACM 导入证书失败：{_cloud_error(resp)}")
    arn = (resp.json() or {}).get("CertificateArn") or "（未返回 ARN）"
    log(f"ACM 证书 ARN：{arn}")


# ================================================================ 百度智能云 CDN
@_register("DeployToBaiduCdn")
def deploy_to_baidu_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """百度智能云 CDN：百度云没有全局证书库，证书是「按域名」挂的，
    所以这里对填的每个加速域名各上传一次证书并开启 HTTPS。"""
    from . import baiducloud

    domains = config.get("domain") or []
    if isinstance(domains, str):
        domains = [item.strip() for item in domains.split(",") if item.strip()]
    domains = [ctx.render(str(item)) for item in (domains or [])] or [ctx.domain]

    enable = bool(config.get("httpsEnable", True))
    for domain in domains:
        name = ctx.render(config.get("certName") or "") or f"{domain}-{int(time.time())}"
        log(f"上传证书到百度云 CDN：{domain}")
        cert_id = baiducloud.put_domain_cert(
            config, domain, name, ctx.crt, ctx.key,
            chain=(config.get("certChain") or "").strip(), enable=enable,
        )
        log(f"{domain} 证书已生效（certId={cert_id or '未返回'}，"
            f"HTTPS={'开启' if enable else '关闭'}）")


# ================================================================ 数据备份
@_register("DeployBackupCerts")
def deploy_backup_certs(ctx: CertContext, config: dict, log: Callable) -> None:
    """把本次证书打包归档到本机备份目录（换证前留一份，出问题能回滚）。"""
    from ..config import PROJECT_DIR

    target = (config.get("dir") or "./data/backup").strip()
    path = Path(target)
    if not path.is_absolute():
        path = PROJECT_DIR / target.lstrip("./")
    path.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = ctx.render(config.get("fileName") or "{domain}-{timestamp}.zip")
    if not name.endswith(".zip"):
        name += ".zip"
    archive = path / name

    meta = {
        "domain": ctx.domain,
        "domains": ctx.domains,
        "expiresTime": ctx.expires_time,
        "backupAt": stamp,
    }
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{ctx.domain}.crt", ctx.crt)
        zf.writestr(f"{ctx.domain}.key", ctx.key)
        if ctx.pfx:
            zf.writestr(f"{ctx.domain}.pfx", ctx.pfx)
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    log(f"证书已备份到 {archive}")

    # 只保留最近 keepCount 份，磁盘不会被历史备份撑爆
    keep = int(config.get("keepCount") or 30)
    if keep > 0:
        olds = sorted(path.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in olds[keep:]:
            try:
                old.unlink()
                log(f"清理旧备份 {old.name}")
            except OSError as exc:
                log(f"清理旧备份失败（跳过）：{exc}")


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
