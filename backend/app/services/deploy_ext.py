"""certd 部署插件复刻（扩展部分）
=================================
部署插件多达上百个，逐个实现没有意义——真正要看的是它们背后的
「交付方式」，同类插件的差异只是默认路径、接口地址和几个参数。

所以这里按交付方式归类，一类共用一套代码：

1. **对象存储**：阿里云 OSS / 腾讯云 COS / 华为云 OBS / 火山引擎 TOS /
   AWS S3 / 自建 MinIO / Cloudflare R2 / 七牛 Kodo
   —— 都是「把一个文件 PUT 到桶里」，差别只在签名算法与 endpoint。

2. **SSH 主机**：Nginx / Apache / HAProxy / Tomcat / IIS
   —— 都是「传文件 + 执行重载命令」，差别只在默认路径与命令。

3. **面板 / 集群**：Nginx Proxy Manager / K8s Secret / OpenWrt
   —— 调各自的 HTTP 接口或 SSH。

4. **云 CDN**：阿里云 DCDN / 直播 / 点播 / SLB、火山引擎 CDN / 直播、
   AWS CloudFront、Fastly。

5. **其它**：证书发邮件、在主机上执行脚本。

所有 handler 统一签名 ``handler(ctx, config, log)``，注册进 deploy.DEPLOY_HANDLERS。
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import smtplib
import ssl
import time
import urllib.parse
from dataclasses import replace
from email import encoders
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Callable

import httpx

from . import net

from . import certutil, volcengine
from .deploy import (
    CertContext,
    DeployError,
    _aliyun_rpc,
    _as_domain_list,
    _cloud_error,
    _cloud_request,
    _panel_request,
    _sftp_write,
    _ssh_client,
    deploy_to_host,
)

HANDLERS: dict[str, Callable] = {}


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


# ================================================================ 对象存储
def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _aws_sigv4(method: str, host: str, path: str, payload: bytes, *,
               ak: str, sk: str, region: str, service: str = "s3",
               content_type: str | None = "application/octet-stream",
               session_token: str = "", now: dt.datetime | None = None) -> dict:
    """AWS SigV4 签名，返回可直接用于请求的 header。

    OBS / TOS / R2 / MinIO / AWS S3 都吃这套；OSS 与 COS 有自己的算法，见下。
    content_type 传 None 表示不签这个头（GET 这类没有 body 的请求要这么用，
    否则签名里声明了 content-type 而实际没发，服务端验签会失败）。
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = amz_date[:8]
    payload_hash = _sha256_hex(payload)

    headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type is not None:
        headers["content-type"] = content_type
    if session_token:
        headers["x-amz-security-token"] = session_token

    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{str(headers[k]).strip()}\n" for k in sorted(headers))
    canonical_uri = urllib.parse.quote(path, safe="/-_.~")
    canonical_request = "\n".join([
        method.upper(), canonical_uri, "", canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope, _sha256_hex(canonical_request.encode()),
    ])
    key = ("AWS4" + sk).encode()
    for part in (date, region, service, "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return headers


def _oss_headers(method: str, bucket: str, key: str, payload: bytes,
                 content_type: str, ak: str, sk: str, date: str = "") -> dict:
    """阿里云 OSS V1 签名。

    注意 OSS 的 CanonicalizedResource 是 ``/bucket/key``，
    和 S3 的路径风格不同，所以不能直接套 SigV4。
    """
    date = date or dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    content_md5 = base64.b64encode(hashlib.md5(payload).digest()).decode()
    string_to_sign = "\n".join([
        method.upper(), content_md5, content_type, date, f"/{bucket}/{key}",
    ])
    signature = base64.b64encode(
        hmac.new(sk.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    return {
        "Date": date,
        "Content-MD5": content_md5,
        "Content-Type": content_type,
        "Authorization": f"OSS {ak}:{signature}",
    }


def _cos_headers(method: str, host: str, key: str, payload: bytes,
                 content_type: str, ak: str, sk: str, now: int | None = None,
                 expire: int = 3600, backdate: int = 60) -> dict:
    """腾讯云 COS 签名（q-sign-algorithm=sha1，即文档里的「签名算法 v5」）。

    两个容易写错的地方（都踩过）：
    1. ``SignKey = HMAC-SHA1(SecretKey, KeyTime)`` 的结果是**十六进制字符串**，
       下一步要用这个字符串当 key，而不是用原始 digest 字节；
    2. 待签的 header 串用 ``&`` 连接、且 key/value 都要 URL 编码，
       不是 ``key=value\\n`` 这种格式。

    key_time 往前留 60 秒，避免本机时钟略快时被判「签名尚未生效」。
    """
    now = int(now if now is not None else time.time())
    key_time = f"{now - backdate};{now + expire}"

    signed = {
        "content-length": str(len(payload)),
        "content-type": content_type,
        "host": host,
    }
    encode = lambda v: urllib.parse.quote(str(v), safe="-_.~")
    header_string = "&".join(f"{encode(k).lower()}={encode(v)}"
                             for k, v in sorted(signed.items()))

    pathname = "/" + key
    http_string = f"{method.lower()}\n{pathname}\n\n{header_string}\n"
    string_to_sign = (f"sha1\n{key_time}\n"
                      f"{hashlib.sha1(http_string.encode()).hexdigest()}\n")
    sign_key = hmac.new(sk.encode(), key_time.encode(), hashlib.sha1).hexdigest()
    signature = hmac.new(sign_key.encode(), string_to_sign.encode(),
                         hashlib.sha1).hexdigest()
    return {
        "Content-Type": content_type,
        "Authorization": (
            f"q-sign-algorithm=sha1&q-ak={ak}&q-sign-time={key_time}"
            f"&q-key-time={key_time}&q-header-list={';'.join(sorted(signed))}"
            f"&q-url-param-list=&q-signature={signature}"
        ),
    }


# 每种存储的 endpoint 模板与默认 region
STORAGE_TARGETS = {
    "oss": {
        "name": "阿里云 OSS",
        "endpoint": "https://{bucket}.{region}.aliyuncs.com/{key}",
        "region": "oss-cn-hangzhou",
        "signer": "oss",
    },
    "cos": {
        "name": "腾讯云 COS",
        "endpoint": "https://{bucket}.cos.{region}.myqcloud.com/{key}",
        "region": "ap-guangzhou",
        "signer": "cos",
    },
    "obs": {
        "name": "华为云 OBS",
        "endpoint": "https://{bucket}.obs.{region}.myhuaweicloud.com/{key}",
        "region": "cn-north-4",
        "signer": "sigv4",
    },
    "tos": {
        "name": "火山引擎 TOS",
        "endpoint": "https://{bucket}.tos-{region}.volces.com/{key}",
        "region": "cn-beijing",
        "signer": "sigv4",
    },
    "aws": {
        "name": "AWS S3",
        "endpoint": "https://{bucket}.s3.{region}.amazonaws.com/{key}",
        "region": "us-east-1",
        "signer": "sigv4",
    },
    "r2": {
        "name": "Cloudflare R2",
        "endpoint": "https://{bucket}.{accountId}.r2.cloudflarestorage.com/{key}",
        "region": "auto",
        "signer": "sigv4",
    },
    "kodo": {
        "name": "七牛 Kodo",
        "endpoint": "https://{bucket}.s3-{region}.qiniucs.com/{key}",
        "region": "cn-east-1",
        "signer": "sigv4",
    },
    "s3": {
        "name": "S3 兼容存储",
        "endpoint": "{endpoint}/{bucket}/{key}",
        "region": "us-east-1",
        "signer": "sigv4",
    },
}


def _object_files(ctx: CertContext, config: dict) -> list[tuple[str, bytes, str]]:
    """要上传的文件清单：证书、私钥，可选 PFX。"""
    files = [
        (ctx.render(config.get("certName") or "{domain}.crt"), ctx.crt.encode(),
         "application/x-pem-file"),
        (ctx.render(config.get("keyName") or "{domain}.key"), ctx.key.encode(),
         "application/x-pem-file"),
    ]
    if config.get("pfxName"):
        pfx = ctx.pfx
        if not pfx:
            pfx = certutil.cert_pem_to_pfx(ctx.crt, ctx.key,
                                           config.get("pfxPassword") or "")
        files.append((ctx.render(config["pfxName"]), pfx, "application/x-pkcs12"))
    return files


def _is_private_host(host: str) -> bool:
    """内网地址判断：这类目标必须绕开系统代理。"""
    import ipaddress

    if not host:
        return False
    if host == "localhost" or host.endswith((".local", ".lan", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _put_object(url: str, headers: dict, body: bytes, label: str) -> None:
    """上传一个对象。

    目标是内网地址时（自建 MinIO / Ceph）必须绕开系统代理，
    否则宿主机配了 HTTP_PROXY 会把 127.0.0.1 也甩给代理，报一个看不出原因的 502。
    """
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        resp = net.request("PUT", url, content=body, headers=headers,
                             timeout=120, trust_env=not _is_private_host(host))
    except httpx.HTTPError as exc:
        raise DeployError(f"{label} 上传失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}）") from exc
    if resp.status_code >= 300:
        raise DeployError(f"{label} 上传失败：{_cloud_error(resp)}")


def _deploy_object_storage(ctx: CertContext, config: dict, log: Callable, kind: str) -> None:
    spec = STORAGE_TARGETS[kind]
    bucket = config.get("bucket") or ""
    if not bucket:
        raise DeployError("未配置存储桶（Bucket）")
    region = config.get("region") or spec["region"]
    ak = (config.get("accessKeyId") or config.get("accessKey") or
          config.get("secretId") or "")
    sk = (config.get("accessKeySecret") or config.get("secretKey") or
          config.get("secretAccessKey") or "")
    if not ak or not sk:
        raise DeployError(f"{spec['name']} 授权缺少 AK/SK")

    prefix = (config.get("dir") or "").strip("/")
    session_token = config.get("sessionToken") or ""
    files = _object_files(ctx, config)

    for name, body, ctype in files:
        key = f"{prefix}/{name}" if prefix else name
        if kind == "s3":
            endpoint = (config.get("endpoint") or "").rstrip("/")
            if not endpoint:
                raise DeployError("自建 S3 需要填写 Endpoint，例如 http://minio.local:9000")
            url = spec["endpoint"].format(endpoint=endpoint, bucket=bucket, key=key)
            host = urllib.parse.urlparse(endpoint).netloc
            path = f"/{bucket}/{key}"
        else:
            url = spec["endpoint"].format(bucket=bucket, region=region, key=key,
                                          accountId=config.get("accountId") or "")
            host = urllib.parse.urlparse(url).netloc
            path = "/" + key

        log(f"上传 {spec['name']}：{bucket}/{key}")
        if spec["signer"] == "oss":
            headers = _oss_headers("PUT", bucket, key, body, ctype, ak, sk)
        elif spec["signer"] == "cos":
            headers = _cos_headers("PUT", host, key, body, ctype, ak, sk)
        else:
            sign_region = region
            # OSS 的 region 形如 oss-cn-hangzhou，签名里要写 cn-hangzhou
            headers = _aws_sigv4("PUT", host, path, body, ak=ak, sk=sk,
                                 region=sign_region, service="s3",
                                 content_type=ctype, session_token=session_token)
        _put_object(url, headers, body, spec["name"])
    log(f"{spec['name']} 部署完成，共 {len(files)} 个文件")


@_register("DeployToAliyunOss")
def deploy_to_aliyun_oss(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "oss")


@_register("DeployToTencentCos")
def deploy_to_tencent_cos(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "cos")


@_register("DeployToHuaweiObs")
def deploy_to_huawei_obs(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "obs")


@_register("DeployToVolcengineTos")
def deploy_to_volcengine_tos(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "tos")


@_register("DeployToAwsS3")
def deploy_to_aws_s3(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "aws")


@_register("DeployToS3")
def deploy_to_s3(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "s3")


@_register("DeployToCloudflareR2")
def deploy_to_r2(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "r2")


@_register("DeployToQiniuKodo")
def deploy_to_qiniu_kodo(ctx, config, log):
    _deploy_object_storage(ctx, config, log, "kodo")


# ================================================================ SSH 主机
SSH_PRESETS = {
    "DeployToNginx": {
        "certPath": "/etc/nginx/ssl/{domain}.crt",
        "keyPath": "/etc/nginx/ssl/{domain}.key",
        "reloadCmd": "nginx -t && nginx -s reload",
    },
    "DeployToApache": {
        "certPath": "/etc/httpd/ssl/{domain}.crt",
        "keyPath": "/etc/httpd/ssl/{domain}.key",
        "reloadCmd": "httpd -t && systemctl reload httpd",
    },
    "DeployToHaproxy": {
        # HAProxy 要的是 crt 与 key 拼在一起的单个 PEM
        "certPath": "/etc/haproxy/ssl/{domain}.pem",
        "keyPath": "",
        "combine": True,
        "reloadCmd": "haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy",
    },
    "DeployToTomcat": {
        # Tomcat 用 PKCS#12，server.xml 里配置 keystoreFile / keystorePass
        "certPath": "",
        "keyPath": "",
        "pfxPath": "/opt/tomcat/conf/{domain}.pfx",
        "reloadCmd": "systemctl restart tomcat",
    },
}


def _deploy_ssh_preset(ctx: CertContext, config: dict, log: Callable, key: str) -> None:
    preset = SSH_PRESETS[key]
    merged = {**preset, **{k: v for k, v in config.items() if v not in (None, "")}}
    if preset.get("combine"):
        # 单文件 PEM：证书 + 私钥，HAProxy / Nginx 的 ssl_certificate 都能直接用
        merged["certPath"] = preset["certPath"]
        ctx = replace(ctx, crt=ctx.crt.rstrip("\n") + "\n" + ctx.key)
    if preset.get("pfxPath"):
        password = config.get("pfxPassword") or ""
        ctx = replace(ctx, pfx=certutil.cert_pem_to_pfx(ctx.crt, ctx.key, password),
                      pfx_password=password)
        merged["pfxPassword"] = password
    deploy_to_host(ctx, merged, log)


@_register("DeployToNginx")
def deploy_to_nginx(ctx, config, log):
    _deploy_ssh_preset(ctx, config, log, "DeployToNginx")


@_register("DeployToApache")
def deploy_to_apache(ctx, config, log):
    _deploy_ssh_preset(ctx, config, log, "DeployToApache")


@_register("DeployToHaproxy")
def deploy_to_haproxy(ctx, config, log):
    _deploy_ssh_preset(ctx, config, log, "DeployToHaproxy")


@_register("DeployToTomcat")
def deploy_to_tomcat(ctx, config, log):
    _deploy_ssh_preset(ctx, config, log, "DeployToTomcat")


def _ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


@_register("DeployToIis")
def deploy_to_iis(ctx: CertContext, config: dict, log: Callable) -> None:
    """Windows IIS：上传 PFX，导入到 LocalMachine\\My，再用 netsh 绑定。

    IIS 没有「证书文件」的概念，证书必须导入证书存储并按指纹绑定，
    所以不能复用普通主机的上传逻辑。
    """
    site = config.get("siteName") or ctx.domain
    port = str(config.get("port") or 443)
    password = config.get("pfxPassword") or ""
    remote_dir = (config.get("dir") or "C:/certd").rstrip("/")
    pfx_name = ctx.render(config.get("pfxName") or "{domain}.pfx")
    pfx = certutil.cert_pem_to_pfx(ctx.crt, ctx.key, password)

    log(f"连接主机 {config.get('host')} ...")
    client = _ssh_client(config)
    try:
        sftp = client.open_sftp()
        pfx_path = f"{remote_dir}/{pfx_name}"
        log(f"上传 {pfx_path}")
        _sftp_write(sftp, pfx_path, pfx)

        script = "\n".join([
            "$ErrorActionPreference = 'Stop'",
            f"$pwd = ConvertTo-SecureString -String {_ps_quote(password)} "
            "-Force -AsPlainText",
            f"$cert = Import-PfxCertificate -FilePath {_ps_quote(pfx_path)} "
            "-CertStoreLocation Cert:\\LocalMachine\\My -Password $pwd",
            "$thumb = $cert.Thumbprint",
            f"netsh http update sslcert hostnameport={site}:{port} "
            "certhash=$thumb appid={{4dc3e181-e14b-4a21-b022-59fc669b0914}} "
            "certstorename=MY",
            "Write-Output ('THUMBPRINT=' + $thumb)",
        ])
        script_path = f"{remote_dir}/certd-deploy.ps1"
        log(f"写入部署脚本 {script_path}")
        _sftp_write(sftp, script_path, script.encode("utf-8-sig"))
        sftp.close()

        cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
        log(f"执行：{cmd}")
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=180)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        if out:
            log(out)
        if code != 0:
            raise DeployError(f"IIS 部署失败（exit {code}）：{err or out}")
        log("IIS 证书部署完成")
    finally:
        client.close()


# ================================================================ 面板 / 集群
@_register("DeployToNpm")
def deploy_to_npm(ctx: CertContext, config: dict, log: Callable) -> None:
    """Nginx Proxy Manager：登录 → 上传证书 → 绑定到代理主机。"""
    base = (config.get("url") or "").rstrip("/")
    if not base:
        raise DeployError("未配置 NPM 地址")
    verify = not config.get("insecure", True)

    log(f"登录 NPM：{base}")
    resp = _panel_request("POST", f"{base}/api/tokens", timeout=30, verify=verify,
                          json={"identity": config.get("email") or "",
                                "secret": config.get("password") or ""})
    if resp.status_code >= 400:
        raise DeployError(f"NPM 登录失败：{_cloud_error(resp)}")
    token = (resp.json() or {}).get("token")
    if not token:
        raise DeployError("NPM 登录失败：未返回 token")
    headers = {"Authorization": f"Bearer {token}"}

    nice_name = ctx.render(config.get("certName") or f"{ctx.domain}-certd-{int(time.time())}")
    log(f"上传证书：{nice_name}")
    files = {
        "certificate": ("cert.pem", ctx.crt.encode(), "application/x-pem-file"),
        "key": ("key.pem", ctx.key.encode(), "application/x-pem-file"),
    }
    resp = _panel_request("POST", f"{base}/api/nginx/certificates", timeout=60,
                          verify=verify, headers=headers,
                          data={"nice_name": nice_name, "provider": "other"}, files=files)
    if resp.status_code >= 400:
        raise DeployError(f"NPM 上传证书失败：{_cloud_error(resp)}")
    cert_id = (resp.json() or {}).get("id")
    log(f"证书 ID：{cert_id}")

    host_ids = _as_domain_list(config.get("proxyHostId"))
    host_ids = list(dict.fromkeys(str(item).strip() for item in host_ids if str(item).strip()))
    if not host_ids:
        log("未选择代理主机，仅上传证书")
        return

    errors: list[str] = []
    for host_id in host_ids:
        resp = _panel_request("GET", f"{base}/api/nginx/proxy-hosts/{host_id}", timeout=30,
                              verify=verify, headers=headers)
        if resp.status_code >= 400:
            errors.append(f"代理主机 {host_id}: 读取失败 {_cloud_error(resp)}")
            continue
        host = resp.json() or {}
        host["certificate_id"] = cert_id
        host["ssl_forced"] = True
        resp = _panel_request("PUT", f"{base}/api/nginx/proxy-hosts/{host_id}", timeout=60,
                              verify=verify, headers=headers, json=host)
        if resp.status_code >= 400:
            errors.append(f"代理主机 {host_id}: 绑定失败 {_cloud_error(resp)}")
            continue
        log(f"已绑定到代理主机 {host_id}")
    if errors:
        raise DeployError("部分 NPM 代理主机部署失败：" + "；".join(errors))
    log("NPM 部署完成")


@_register("DeployToK8sSecret")
def deploy_to_k8s_secret(ctx: CertContext, config: dict, log: Callable) -> None:
    """把证书写成 kubernetes.io/tls 类型的 Secret（Ingress 可直接引用）。

    写完之后可以顺带给 Ingress 打一个时间戳注解：Nginx Ingress Controller 只在
    Ingress 对象变化时重新加载上游证书，只改 Secret 有时要等十几分钟才生效。
    """
    base = (config.get("apiServer") or config.get("apiUrl") or "").rstrip("/")
    if not base:
        raise DeployError("未配置 Kubernetes API 地址")
    token = config.get("token") or ""
    if not token:
        raise DeployError("未配置 Kubernetes Token")
    namespace = ctx.render(config.get("namespace") or "default")
    name = ctx.render(config.get("secretName") or f"{ctx.domain.replace('*', 'wildcard')}-tls")
    # caCert 用于自建集群的自签 CA；insecure 优先级更高（跳过校验）
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
    headers = {"Authorization": f"Bearer {token}"}

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
    url = f"{base}/api/v1/namespaces/{namespace}/secrets"
    resp = _panel_request("POST", url, timeout=30, verify=verify, headers=headers, json=body)
    if resp.status_code == 409:
        # 已存在，取 resourceVersion 后整体替换
        log(f"Secret {namespace}/{name} 已存在，改为更新")
        cur = _panel_request("GET", f"{url}/{name}", timeout=30, verify=verify, headers=headers)
        if cur.status_code >= 400:
            raise DeployError(f"读取 Secret 失败：{_cloud_error(cur)}")
        body["metadata"]["resourceVersion"] = (cur.json() or {}).get("metadata", {}).get(
            "resourceVersion")
        resp = _panel_request("PUT", f"{url}/{name}", timeout=30, verify=verify,
                              headers=headers, json=body)
    if resp.status_code >= 400:
        raise DeployError(f"写入 Secret 失败：{_cloud_error(resp)}")
    log(f"K8s Secret 已更新：{namespace}/{name}")

    ingresses = config.get("ingressNames") or []
    if isinstance(ingresses, str):
        ingresses = [item.strip() for item in ingresses.split(",") if item.strip()]
    if not ingresses:
        return
    annotation = config.get("restartAnnotation") or "certd.io/reload-at"
    stamp = str(int(time.time()))
    for ingress in ingresses:
        ingress = ctx.render(str(ingress))
        patch = {"metadata": {"annotations": {annotation: stamp}}}
        resp2 = _panel_request(
            "PATCH",
            f"{base}/apis/networking.k8s.io/v1/namespaces/{namespace}/ingresses/{ingress}",
            timeout=30, verify=verify, headers={**headers,
                                               "Content-Type": "application/merge-patch+json"},
            json=patch)
        if resp2.status_code >= 400:
            raise DeployError(f"触发 Ingress {ingress} 重载失败：{_cloud_error(resp2)}")
        log(f"已触发 Ingress {ingress} 重载")


@_register("DeployToOpenwrt")
def deploy_to_openwrt(ctx: CertContext, config: dict, log: Callable) -> None:
    """OpenWrt（含 iStoreOS）：写证书文件并重启 uhttpd / nginx。"""
    service = config.get("service") or "uhttpd"
    cert_path = ctx.render(config.get("certPath") or f"/etc/ssl/certd/{ctx.domain}.crt")
    key_path = ctx.render(config.get("keyPath") or f"/etc/ssl/certd/{ctx.domain}.key")

    log(f"连接路由器 {config.get('host')} ...")
    client = _ssh_client(config)
    try:
        sftp = client.open_sftp()
        log(f"上传 {cert_path}")
        _sftp_write(sftp, cert_path, ctx.crt.encode())
        log(f"上传 {key_path}")
        _sftp_write(sftp, key_path, ctx.key.encode())
        sftp.close()

        if service == "uhttpd":
            cmd = "; ".join([
                f"uci set uhttpd.main.cert={cert_path}",
                f"uci set uhttpd.main.key={key_path}",
                "uci commit uhttpd",
                "/etc/init.d/uhttpd restart",
            ])
        else:
            cmd = (config.get("reloadCmd") or
                   f"/etc/init.d/{service} restart")
        log(f"执行：{cmd}")
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        if out:
            log(out)
        if code != 0:
            raise DeployError(f"重启 {service} 失败（exit {code}）：{err or out}")
        log("OpenWrt 证书部署完成")
    finally:
        client.close()


# ================================================================ 云 CDN
@_register("DeployToAliyunDcdn")
def deploy_to_aliyun_dcdn(ctx, config, log):
    domain = ctx.render(config.get("domain") or ctx.domain)
    log(f"上传证书到阿里云 DCDN：{domain}")
    result = _aliyun_rpc(config, "SetDcdnDomainSSLCertificate", {
        "DomainName": domain,
        "SSLProtocol": "on",
        "CertType": "upload",
        "SSLPub": ctx.crt,
        "SSLPri": ctx.key,
        "CertName": ctx.render(config.get("certName") or f"certd-{domain}-{int(time.time())}"),
    }, "https://dcdn.aliyuncs.com/", "2018-01-15")
    log(f"阿里云 DCDN 返回：{json.dumps(result, ensure_ascii=False)[:200]}")


@_register("DeployToAliyunLive")
def deploy_to_aliyun_live(ctx, config, log):
    domain = ctx.render(config.get("domain") or ctx.domain)
    log(f"上传证书到阿里云直播：{domain}")
    result = _aliyun_rpc(config, "SetLiveDomainCertificate", {
        "DomainName": domain,
        "CertType": "upload",
        "SSLPub": ctx.crt,
        "SSLPri": ctx.key,
        "CertName": ctx.render(config.get("certName") or f"certd-{domain}-{int(time.time())}"),
    }, "https://live.aliyuncs.com/", "2016-11-01")
    log(f"阿里云直播返回：{json.dumps(result, ensure_ascii=False)[:200]}")


@_register("DeployToAliyunVod")
def deploy_to_aliyun_vod(ctx, config, log):
    domain = ctx.render(config.get("domain") or ctx.domain)
    log(f"上传证书到阿里云点播：{domain}")
    result = _aliyun_rpc(config, "SetVodDomainCertificate", {
        "DomainName": domain,
        "CertType": "upload",
        "SSLPub": ctx.crt,
        "SSLPri": ctx.key,
        "CertName": ctx.render(config.get("certName") or f"certd-{domain}-{int(time.time())}"),
    }, "https://vod.aliyuncs.com/", "2017-03-21")
    log(f"阿里云点播返回：{json.dumps(result, ensure_ascii=False)[:200]}")


@_register("DeployToAliyunSlb")
def deploy_to_aliyun_slb(ctx, config, log):
    """上传到阿里云 SLB 证书库。

    注意：SLB 的证书绑定在监听上，需要先在证书库里有这张证书。
    这里只做「上传」，绑定动作由用户在控制台或后续任务完成。
    """
    name = ctx.render(config.get("certName") or f"certd-{ctx.domain}-{int(time.time())}")
    log(f"上传证书到阿里云 SLB 证书库：{name}")
    result = _aliyun_rpc(config, "UploadServerCertificate", {
        "ServerCertificateName": name,
        "ServerCertificate": ctx.crt,
        "PrivateKey": ctx.key,
    }, "https://slb.aliyuncs.com/", "2014-05-15")
    cert_id = (result.get("ServerCertificateId") or "")
    log(f"阿里云 SLB 证书 ID：{cert_id}")


def _volc_call(config: dict, action: str, body: dict, host: str, service: str,
               version: str) -> dict:
    cfg = {**config, "host": host, "service": service}
    try:
        url, headers, payload = volcengine.sign(cfg, "POST", action, body, version=version)
        resp = _cloud_request("POST", url, headers=headers, content=payload, timeout=60)
    except volcengine.VolcError as exc:
        raise DeployError(str(exc)) from exc
    try:
        data = resp.json()
    except ValueError:
        raise DeployError(f"火山引擎 {action} 返回非 JSON（HTTP {resp.status_code}）")
    meta = data.get("ResponseMetadata") or {}
    err = meta.get("Error") or {}
    if err:
        raise DeployError(f"火山引擎 {action} 失败：{err.get('Message')}（{err.get('Code')}）")
    return data.get("Result") or {}


@_register("DeployToVolcengineCdn")
def deploy_to_volcengine_cdn(ctx, config, log):
    domain = ctx.render(config.get("domain") or ctx.domain)
    log(f"上传证书到火山引擎 CDN：{domain}")
    result = _volc_call(config, "AddCdnCertificate", {
        "Certificate": {
            "Certificate": ctx.crt,
            "PrivateKey": ctx.key,
            "Desc": ctx.render(config.get("certName") or f"certd-{domain}"),
        },
    }, "cdn.volcengineapi.com", "CDN", "2021-03-01")
    cert_id = result.get("CertId") or ""
    log(f"证书 ID：{cert_id}")
    if not cert_id:
        raise DeployError(f"火山引擎未返回 CertId：{json.dumps(result, ensure_ascii=False)[:200]}")
    _volc_call(config, "UpdateCdnConfig", {
        "Domain": domain,
        "CertId": cert_id,
        "CertName": ctx.render(config.get("certName") or f"certd-{domain}"),
    }, "cdn.volcengineapi.com", "CDN", "2021-03-01")
    log("火山引擎 CDN 证书绑定完成")


@_register("DeployToVolcengineLive")
def deploy_to_volcengine_live(ctx, config, log):
    """火山引擎直播：直播产品没有单独的「添加证书」接口（AddCert 不存在），
    证书随 UpdateCert 一起提交。"""
    domain = ctx.render(config.get("domain") or ctx.domain)
    log(f"上传证书到火山引擎直播：{domain}")
    result = _volc_call(config, "UpdateCert", {
        "Domain": domain,
        "CertName": ctx.render(config.get("certName") or f"certd-{domain}"),
        "Certificate": ctx.crt,
        "PrivateKey": ctx.key,
    }, "live.volcengineapi.com", "live", "2023-01-01")
    log(f"火山引擎直播返回：{json.dumps(result, ensure_ascii=False)[:200]}")


@_register("DeployToAwsCloudfront")
def deploy_to_aws_cloudfront(ctx, config, log):
    """AWS CloudFront：先导入 ACM 证书，再把分发指向它。

    CloudFront 只接受 us-east-1 的 ACM 证书，且必须回写完整的
    DistributionConfig（先 GET 拿到配置与 ETag，改完再 PUT）。
    这里用 XML 字符串处理，避免引入额外依赖。
    """
    import xml.etree.ElementTree as ET

    distribution_id = config.get("distributionId") or ""
    if not distribution_id:
        raise DeployError("未配置 CloudFront 分发 ID")
    ak = config.get("accessKeyId") or ""
    sk = config.get("secretAccessKey") or config.get("secretKey") or ""
    if not ak or not sk:
        raise DeployError("AWS 授权缺少 AccessKey / SecretAccessKey")

    region = "us-east-1"
    log("导入证书到 ACM（us-east-1）...")
    acm_body = json.dumps({
        "Certificate": ctx.crt, "PrivateKey": ctx.key, "CertificateChain": "",
    }).encode()
    host = f"acm.{region}.amazonaws.com"
    headers = _aws_sigv4("POST", host, "/", acm_body, ak=ak, sk=sk, region=region,
                         service="acm", content_type="application/x-amz-json-1.1")
    headers["X-Amz-Target"] = "CertificateManager.ImportCertificate"
    resp = _cloud_request("POST", f"https://{host}/", content=acm_body, headers=headers)
    if resp.status_code >= 300:
        raise DeployError(f"ACM 导入证书失败：{_cloud_error(resp)}")
    cert_arn = (resp.json() or {}).get("CertificateArn")
    log(f"ACM 证书 ARN：{cert_arn}")

    cf_host = "cloudfront.amazonaws.com"
    base = f"https://{cf_host}/2020-05-31/distribution/{distribution_id}/config"
    log("读取 CloudFront 分发配置 ...")
    # GET 没有 body，不签 content-type —— 签名里声明了却没发这个头，服务端验签会失败
    h = _aws_sigv4("GET", cf_host, f"/2020-05-31/distribution/{distribution_id}/config",
                   b"", ak=ak, sk=sk, region="us-east-1", service="cloudfront",
                   content_type=None)
    resp = _cloud_request("GET", base, headers=h)
    if resp.status_code >= 300:
        raise DeployError(f"读取 CloudFront 配置失败：{_cloud_error(resp)}")
    etag = resp.headers.get("ETag", "")

    root = ET.fromstring(resp.text)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag[1:].split("}")[0]
    prefix = f"{{{ns}}}" if ns else ""
    vc = root.find(f"{prefix}DistributionConfig/{prefix}ViewerCertificate")
    if vc is None:
        raise DeployError("CloudFront 配置里没有 ViewerCertificate 节点")
    for child in list(vc):
        vc.remove(child)
    for tag, text in (("CloudFrontDefaultCertificate", "false"),
                      ("ACMCertificateArn", cert_arn),
                      ("SSLSupportMethod", config.get("sslMethod") or "sni-only"),
                      ("MinimumProtocolVersion", "TLSv1.2_2021")):
        node = ET.SubElement(vc, f"{prefix}{tag}")
        node.text = text

    body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    log("回写 CloudFront 配置 ...")
    h = _aws_sigv4("PUT", cf_host, f"/2020-05-31/distribution/{distribution_id}/config",
                   body, ak=ak, sk=sk, region="us-east-1", service="cloudfront",
                   content_type="application/xml")
    if etag:
        h["If-Match"] = etag
    resp = _cloud_request("PUT", base, content=body, headers=h)
    if resp.status_code >= 300:
        raise DeployError(f"更新 CloudFront 配置失败：{_cloud_error(resp)}")
    log("CloudFront 证书部署完成")


@_register("DeployToFastly")
def deploy_to_fastly(ctx, config, log):
    """Fastly：把证书上传到某个 service version（默认 active 版本的下一个）。"""
    token = config.get("apiToken") or ""
    service_id = config.get("serviceId") or ""
    if not token or not service_id:
        raise DeployError("Fastly 需要 API Token 与 Service ID")
    version = config.get("version") or ""
    headers = {"Fastly-Key": token, "Accept": "application/json"}

    if not version:
        log("查询 Fastly 服务版本 ...")
        resp = _cloud_request("GET", f"https://api.fastly.com/service/{service_id}/details",
                              headers=headers)
        if resp.status_code >= 300:
            raise DeployError(f"查询 Fastly 服务失败：{_cloud_error(resp)}")
        active = (resp.json() or {}).get("active_version")
        if not active:
            raise DeployError("该服务还没有 active 版本，请先在控制台发布一次")
        # 证书只能加到「草稿版本」，先克隆 active 版本
        resp = _cloud_request("PUT", f"https://api.fastly.com/service/{service_id}/version/"
                                     f"{active}/clone", headers=headers)
        if resp.status_code >= 300:
            raise DeployError(f"克隆 Fastly 版本失败：{_cloud_error(resp)}")
        version = str((resp.json() or {}).get("number") or "")
        log(f"已克隆出版本 {version}")

    body = json.dumps({"cert_blob": ctx.crt, "name": ctx.domain,
                       "intermediates_blob": ""}).encode()
    headers["Content-Type"] = "application/json"
    resp = _cloud_request("POST",
                          f"https://api.fastly.com/service/{service_id}/version/{version}/certificate",
                          content=body, headers=headers)
    if resp.status_code >= 300:
        raise DeployError(f"Fastly 上传证书失败：{_cloud_error(resp)}")
    log("Fastly 证书已上传")
    if config.get("activate", True):
        resp = _cloud_request("PUT",
                              f"https://api.fastly.com/service/{service_id}/version/{version}/activate",
                              headers=headers)
        if resp.status_code >= 300:
            raise DeployError(f"激活 Fastly 版本失败：{_cloud_error(resp)}")
        log(f"Fastly 版本 {version} 已激活")


# ================================================================ 其它
@_register("DeployToMail")
def deploy_to_mail(ctx: CertContext, config: dict, log: Callable) -> None:
    """把证书作为附件发到指定邮箱（备份 / 交付给人工安装的场景）。"""
    host = config.get("smtpHost")
    if not host:
        raise DeployError("未配置 SMTP 服务器")
    to = config.get("to") or []
    if isinstance(to, str):
        to = [x.strip() for x in to.replace(";", ",").split(",") if x.strip()]
    if not to:
        raise DeployError("未配置收件人")
    username = config.get("username") or ""
    sender = config.get("from") or username
    port = int(config.get("smtpPort") or 465)

    msg = MIMEMultipart()
    msg["Subject"] = Header(f"证书 {ctx.domain}（{ctx.expires_time or ''} 到期）", "utf-8")
    msg["From"] = formataddr((str(Header("CertHub", "utf-8")), sender))
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(f"<p>域名：{ctx.domain}</p><p>到期时间：{ctx.expires_time}</p>",
                        "html", "utf-8"))
    for name, content, ctype in _object_files(ctx, config):
        part = MIMEApplication(content, _subtype="x-pem" if "pem" in ctype else "pkcs12")
        part.add_header("Content-Disposition", "attachment", filename=name)
        msg.attach(part)

    log(f"发送邮件到 {', '.join(to)}")
    if config.get("ssl", True):
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        try:
            server.starttls()
        except Exception:
            pass
    try:
        if username:
            server.login(username, config.get("password") or "")
        server.sendmail(sender, to, msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise DeployError("SMTP 认证失败：多数邮箱这里要填「授权码」而不是登录密码") from exc
    finally:
        server.quit()
    log("证书邮件已发送")


@_register("DeployToScript")
def deploy_to_script(ctx: CertContext, config: dict, log: Callable) -> None:
    """在远程主机上执行自定义脚本，可通过环境变量拿到证书内容。"""
    command = config.get("command") or ""
    if not command:
        raise DeployError("未配置要执行的命令")
    log(f"连接主机 {config.get('host')} ...")
    client = _ssh_client(config)
    try:
        env = {
            "CERTD_DOMAIN": ctx.domain,
            "CERTD_CERT": base64.b64encode(ctx.crt.encode()).decode(),
            "CERTD_KEY": base64.b64encode(ctx.key.encode()).decode(),
        }
        exports = " ".join(f"{k}='{v}'" for k, v in env.items())
        cmd = f"export {exports}; {ctx.render(command)}"
        log(f"执行：{ctx.render(command)}")
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
        out = stdout.read().decode(errors="ignore").strip()
        err = stderr.read().decode(errors="ignore").strip()
        code = stdout.channel.recv_exit_status()
        if out:
            log(out[-2000:])
        if code != 0:
            raise DeployError(f"脚本执行失败（exit {code}）：{err[-500:] or out[-500:]}")
        log("脚本执行完成")
    finally:
        client.close()


# 把扩展 handler 注册进主注册表。
# 依赖方向保持单向（deploy_ext → deploy），所以这段放在文件末尾、
# 由 deploy_ext 主动写入，而不是让 deploy 反过来 import 本模块。
from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
