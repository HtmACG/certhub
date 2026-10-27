"""
证书部署插件
============
统一签名：handler(ctx, config, log) -> None
ctx 为 CertContext，包含证书内容与域名信息。
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import posixpath
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from . import net
from .certutil import _chain_blocks


class DeployError(Exception):
    pass


@dataclass
class CertContext:
    domain: str
    crt: str
    key: str
    pfx: bytes | None = None
    pfx_password: str = ""
    expires_time: str = ""
    domains: list[str] = field(default_factory=list)

    def render(self, template: str) -> str:
        if not template:
            return template
        return (template
                .replace("{domain}", self.domain)
                .replace("{timestamp}", str(int(time.time())))
                .replace("{date}", dt.date.today().isoformat()))


def _as_domain_list(value) -> list[str]:
    """把「单个域名字符串 / 数组 / 逗号分隔串」统一成域名列表。

    CDN 域名支持多选后，入参可能是数组；这里兼容老数据的字符串形式。
    """
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


# ---------------------------------------------------------------- SSH / 主机
def _ssh_client(config: dict):
    import paramiko

    host = (config.get("host") or "").strip()
    if not host:
        raise DeployError("未配置主机地址")
    port = int(config.get("port") or 22)
    user = config.get("username") or "root"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        "hostname": host,
        "port": port,
        "username": user,
        "timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 20,
    }
    if (config.get("authType") or "password") == "key":
        import io

        pkey_text = config.get("privateKey") or ""
        passphrase = config.get("passphrase") or None
        pkey = None
        for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
            try:
                pkey = cls.from_private_key(io.StringIO(pkey_text), password=passphrase)
                break
            except Exception:
                continue
        if pkey is None:
            raise DeployError("私钥解析失败，请确认格式（OpenSSH / PEM）")
        kwargs["pkey"] = pkey
    else:
        kwargs["password"] = config.get("password") or ""
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False

    try:
        client.connect(**kwargs)
    except paramiko.AuthenticationException:
        raise DeployError(f"SSH 认证失败（{user}@{host}:{port}）："
                          f"账号密码或私钥不正确，也可能是该账号不允许 SSH 登录")
    except paramiko.SSHException as exc:
        raise DeployError(f"SSH 连接 {host}:{port} 失败：{exc}")
    except OSError as exc:
        # NoValidConnectionsError / socket.timeout / gaierror 都走这里
        raise DeployError(f"无法连接主机 {host}:{port}：目标不可达或端口未开放"
                          f"（{exc.__class__.__name__}）")
    return client


def _sftp_write(sftp, remote_path: str, content: bytes):
    remote_dir = posixpath.dirname(remote_path)
    if remote_dir:
        parts, cur = remote_dir.strip("/").split("/"), ""
        for part in parts:
            cur += "/" + part
            try:
                sftp.stat(cur)
            except IOError:
                sftp.mkdir(cur)
    with sftp.file(remote_path, "wb") as fh:
        fh.write(content)


def deploy_to_host(ctx: CertContext, config: dict, log: Callable) -> None:
    host = config.get("host") or ""
    log(f"连接主机 {host} ...")
    client = _ssh_client(config)
    try:
        sftp = client.open_sftp()
        files = [
            (config.get("certPath") or "", ctx.crt.encode()),
            (config.get("keyPath") or "", ctx.key.encode()),
        ]
        if config.get("pfxPath") and ctx.pfx:
            files.append((config["pfxPath"], ctx.pfx))
        for path, content in files:
            if not path:
                continue
            real = ctx.render(path)
            log(f"上传 {real}")
            _sftp_write(sftp, real, content)
        sftp.close()

        cmd = ctx.render(config.get("reloadCmd") or "")
        if cmd:
            log(f"执行命令：{cmd}")
            _stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
            out = stdout.read().decode(errors="ignore").strip()
            err = stderr.read().decode(errors="ignore").strip()
            code = stdout.channel.recv_exit_status()
            if out:
                log(out)
            if code != 0:
                raise DeployError(f"重载命令执行失败（exit {code}）：{err or out}")
        log("证书部署完成")
    finally:
        client.close()


def deploy_to_local(ctx: CertContext, config: dict, log: Callable) -> None:
    target = Path(ctx.render(config.get("dir") or "./data/deploy")).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    mapping = [
        (config.get("certName") or "{domain}.crt", ctx.crt.encode()),
        (config.get("keyName") or "{domain}.key", ctx.key.encode()),
    ]
    if config.get("pfxName") and ctx.pfx:
        mapping.append((config["pfxName"], ctx.pfx))
    for name, content in mapping:
        if not name:
            continue
        path = target / ctx.render(name)
        path.write_bytes(content)
        log(f"写入 {path}")
    log("证书复制完成")


# ---------------------------------------------------------------- 云厂商公共
def _cloud_error(resp) -> str:
    """把云厂商的错误响应压成一行人话。

    各家格式不一样（阿里云 Message+Code、腾讯云 Response.Error、
    七牛 error+error_code），直接甩原文用户只能看到一坨 JSON 和 RequestId。
    """
    try:
        data = resp.json()
    except Exception:
        return f"HTTP {resp.status_code}：{resp.text[:200]}"
    err = data.get("Error") or (data.get("Response") or {}).get("Error") or data
    if not isinstance(err, dict):
        return f"HTTP {resp.status_code}：{resp.text[:200]}"
    msg = err.get("Message") or err.get("message") or err.get("error") or ""
    code = err.get("Code") or err.get("error_code") or ""
    if msg and code and str(code) not in str(msg):
        return f"{msg}（{code}）"
    if msg or code:
        return str(msg or code)
    return f"HTTP {resp.status_code}：{resp.text[:200]}"


def _cloud_request(method: str, url: str, **kwargs):
    """公网云厂商的请求：连接类异常翻成中文。

    这里不关 trust_env —— 访问公网 API 时宿主机上的代理往往是需要的。
    """
    try:
        return net.request(method, url, timeout=30, **kwargs)
    except httpx.HTTPError as exc:
        raise DeployError(f"请求 {url} 失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}），请检查网络或代理设置") from exc


# ---------------------------------------------------------------- 阿里云 CDN
def _aliyun_rpc(config: dict, action: str, params: dict, endpoint: str, version: str) -> dict:
    def enc(s):
        return urllib.parse.quote(str(s), safe="~")

    common = {
        "Action": action, "Format": "JSON", "Version": version,
        "AccessKeyId": config.get("accessKeyId", ""),
        "SignatureMethod": "HMAC-SHA1", "SignatureVersion": "1.0",
        "SignatureNonce": "".join(hashlib.md5(os.urandom(16)).hexdigest()[:16]),
        "Timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    common.update({k: v for k, v in params.items() if v not in (None, "")})
    canonical = "&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(common.items()))
    string_to_sign = "GET&%2F&" + enc(canonical)
    key = (config.get("accessKeySecret", "") + "&").encode()
    common["Signature"] = base64.b64encode(
        hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    resp = _cloud_request("GET", endpoint, params=common)
    if resp.status_code >= 400:
        raise DeployError(f"阿里云 {action} 失败：{_cloud_error(resp)}")
    try:
        return resp.json()
    except ValueError:
        raise DeployError(f"阿里云 {action} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")


def deploy_to_aliyun_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    # CDN 域名支持多选：逐个域名下发同一张证书
    domains = _as_domain_list(config.get("domain")) or [ctx.domain]
    for domain in domains:
        domain = ctx.render(domain)
        log(f"上传证书到阿里云 CDN：{domain}")
        result = _aliyun_rpc(config, "SetDomainServerCertificate", {
            "DomainName": domain,
            "ServerCertificateStatus": "on",
            "CertType": "upload",
            "ServerCertificate": ctx.crt,
            "PrivateKey": ctx.key,
            "CertName": ctx.render(config.get("certName") or f"{domain}-{int(time.time())}"),
        }, "https://cdn.aliyuncs.com/", "2018-05-10")
        log(f"阿里云 CDN 返回：{json.dumps(result, ensure_ascii=False)[:200]}")


# ---------------------------------------------------------------- 腾讯云 CDN
def _tencent_request(config: dict, action: str, body: dict, host: str, service: str,
                     version: str) -> dict:
    payload = json.dumps(body, separators=(",", ":"))
    ts = int(time.time())
    date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
    ct = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{action.lower()}\n"
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join([
        "POST", "/", "", canonical_headers, signed_headers,
        hashlib.sha256(payload.encode()).hexdigest(),
    ])
    scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join([
        "TC3-HMAC-SHA256", str(ts), scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])
    secret = config.get("secretKey", "")
    k_date = hmac.new(("TC3" + secret).encode(), date.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_date, service.encode(), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"tc3_request", hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"TC3-HMAC-SHA256 Credential={config.get('secretId','')}/{scope}, "
                         f"SignedHeaders={signed_headers}, Signature={signature}",
        "Content-Type": ct, "Host": host,
        "X-TC-Action": action, "X-TC-Timestamp": str(ts), "X-TC-Version": version,
    }
    resp = _cloud_request("POST", f"https://{host}", content=payload, headers=headers)
    if resp.status_code >= 400:
        raise DeployError(f"腾讯云 {action} 失败：{_cloud_error(resp)}")
    try:
        data = resp.json().get("Response", {})
    except ValueError:
        raise DeployError(f"腾讯云 {action} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if data.get("Error"):
        raise DeployError(f"腾讯云 {action} 失败：{_cloud_error(resp)}")
    return data


def deploy_to_tencent_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """把证书部署到腾讯云 CDN 加速域名。

    注意：CDN 服务下没有 UpdateCertificate 这个 action（早先的实现写错了，
    每次调用都会返回 InvalidAction）。正确做法是走 UpdateDomainConfig，
    在 Https.CertInfo 里直接带上证书与私钥，接口会做证书链与私钥匹配校验
    （对应错误码 InvalidParameter.SslCertParseError / SslCertMatchError）。
    """
    # CDN 域名支持多选：逐个域名下发同一张证书
    domains = _as_domain_list(config.get("domain")) or [ctx.domain]
    for domain in domains:
        domain = ctx.render(domain)
        log(f"上传证书到腾讯云 CDN：{domain}")
        result = _tencent_request(config, "UpdateDomainConfig", {
            "Domain": domain,
            "Https": {
                "Switch": "on",
                "CertInfo": {"Certificate": ctx.crt, "PrivateKey": ctx.key},
            },
        }, "cdn.tencentcloudapi.com", "cdn", "2018-06-06")
        log(f"腾讯云 CDN 返回：{json.dumps(result, ensure_ascii=False)[:200]}")


# ---------------------------------------------------------------- 七牛云
def _qiniu_token(config: dict, data: bytes) -> str:
    ak, sk = config.get("accessKey", ""), config.get("secretKey", "")
    encoded = base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    sign = hmac.new(sk.encode(), encoded.encode(), hashlib.sha1).digest()
    return f"{ak}:{base64.urlsafe_b64encode(sign).rstrip(b'=').decode()}:{encoded}"


def deploy_to_qiniu(ctx: CertContext, config: dict, log: Callable) -> None:
    domain = ctx.render(config.get("domain") or ctx.domain)
    name = ctx.render(config.get("certName") or f"{domain}-{int(time.time())}")
    body = {"name": name, "common_name": ctx.domain, "pri": ctx.key, "ca": ctx.crt}
    token = _qiniu_token(config, json.dumps(body).encode())
    log(f"上传证书到七牛云：{name}")
    resp = _cloud_request("POST", "https://api.qiniu.com/sslcert", json=body,
                          headers={"Authorization": f"QBox {token}"})
    if resp.status_code >= 400:
        raise DeployError(f"七牛云证书上传失败：{_cloud_error(resp)}")
    try:
        cert_id = resp.json().get("certID")
    except ValueError:
        raise DeployError(f"七牛云返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    log(f"证书 ID：{cert_id}")
    resp = _cloud_request("PUT", f"https://api.qiniu.com/domain/{domain}/ssl",
                          json={"certid": cert_id},
                          headers={"Authorization":
                                   f"QBox {_qiniu_token(config, json.dumps({'certid': cert_id}).encode())}"})
    if resp.status_code >= 400:
        raise DeployError(f"七牛云域名绑定失败：{_cloud_error(resp)}")
    log("七牛云部署完成")


# ---------------------------------------------------------------- 宝塔
def _panel_request(method: str, url: str, *, timeout: float = 30,
                   verify: bool = False, **kwargs):
    """内网面板统一发请求。

    两个必须做的处理：
    1. trust_env=False —— 部署目标是 192.168.x.x 这类内网地址，
       宿主机上若有 HTTP_PROXY，httpx 默认会把内网请求也甩给代理，
       结果是「连不上」却看不出原因；
    2. 把连接类异常翻成中文文案，避免用户看到
       `ConnectError: [WinError 10061]` 这种无从下手的内容。
    """
    try:
        return net.request(method, url, timeout=timeout, verify=verify,
                             trust_env=False, **kwargs)
    except httpx.HTTPError as exc:
        raise DeployError(f"连接 {url} 失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}）") from exc


def deploy_to_baota(ctx: CertContext, config: dict, log: Callable) -> None:
    url = (config.get("url") or "").rstrip("/")
    api_key = config.get("apiKey") or ""
    ts = str(int(time.time()))
    token = hashlib.md5((ts + hashlib.md5(api_key.encode()).hexdigest()).encode()).hexdigest()
    site = ctx.render(config.get("siteName") or ctx.domain)
    log(f"部署到宝塔站点：{site}")
    resp = _panel_request("POST", f"{url}/site?action=SetSSL", timeout=60, data={
        "request_time": ts, "request_token": token,
        "siteName": site, "type": "1", "csr": ctx.crt, "key": ctx.key,
    })
    try:
        data = resp.json()
    except Exception:
        raise DeployError(f"宝塔返回异常（HTTP {resp.status_code}）：{resp.text[:300]}")
    if not data.get("status"):
        raise DeployError(f"宝塔部署失败：{data.get('msg')}")
    log("宝塔部署完成")


# ---------------------------------------------------------------- 1Panel
def deploy_to_1panel(ctx: CertContext, config: dict, log: Callable) -> None:
    url = (config.get("url") or "").rstrip("/")
    api_key = config.get("apiKey") or ""
    ts = str(int(time.time()))
    token = hashlib.md5((api_key + ts).encode()).hexdigest()
    headers = {"1Panel-Token": token, "1Panel-Timestamp": ts}
    website_id = config.get("websiteId")
    log(f"上传证书到 1Panel 网站 {website_id}")
    resp = _panel_request("POST", f"{url}/api/v2/websites/ssl/upload", timeout=60,
                          headers=headers, json={
        "cert": ctx.crt, "key": ctx.key, "sslName": ctx.domain, "type": "paste",
    })
    try:
        data = resp.json()
    except Exception:
        raise DeployError(f"1Panel 返回异常（HTTP {resp.status_code}）：{resp.text[:300]}")
    if resp.status_code >= 400 or data.get("code") not in (200, 0):
        raise DeployError(f"1Panel 上传证书失败：{data.get('message') or resp.text[:300]}")
    ssl_id = (data.get("data") or {}).get("id")
    resp = _panel_request("POST", f"{url}/api/v2/websites/{website_id}/https", timeout=60,
                          headers=headers, json={
        "websiteSSLId": ssl_id, "enable": True,
    })
    if resp.status_code >= 400:
        raise DeployError(f"1Panel 绑定证书失败：{resp.text[:300]}")
    log("1Panel 部署完成")


# ---------------------------------------------------------------- Webhook
def deploy_to_webhook(ctx: CertContext, config: dict, log: Callable) -> None:
    url = config.get("url") or ""
    if not url:
        raise DeployError("未配置接口地址")
    extra = config.get("extraBody") or "{}"
    try:
        body = json.loads(extra) if isinstance(extra, str) else dict(extra)
    except Exception:
        raise DeployError("附加参数不是合法的 JSON")
    body.update({
        "domain": ctx.domain,
        "domains": ctx.domains,
        "cert": ctx.crt,
        "key": ctx.key,
        "expiresTime": ctx.expires_time,
    })
    headers = {"Content-Type": "application/json"}
    if config.get("token"):
        headers["Authorization"] = f"Bearer {config['token']}"
    log(f"POST {url}")
    try:
        resp = net.post(url, json=body, headers=headers, timeout=60)
    except httpx.HTTPError as exc:
        raise DeployError(f"请求 {url} 失败：{exc.__class__.__name__}"
                          f"（{str(exc) or '无详细原因'}）")
    if resp.status_code >= 400:
        raise DeployError(f"接口返回 {resp.status_code}：{resp.text[:200]}")
    log(f"接口返回 {resp.status_code}")


# ---------------------------------------------------------------- 群晖 DSM
def _totp_code(secret: str) -> str:
    """用群晖的双重认证密钥现算一个验证码。

    手工填的验证码 30 秒就过期，自动续签场景根本没法用；
    存 Base32 密钥、每次现算才是能长期跑的做法。
    """
    text = (secret or "").replace(" ", "").strip()
    if not text:
        return ""
    try:
        import pyotp
    except ImportError as exc:  # pragma: no cover - requirements 里有 pyotp
        raise DeployError("服务端缺少 pyotp 依赖，无法生成验证码") from exc
    try:
        return pyotp.TOTP(text).now()
    except Exception as exc:  # noqa: BLE001
        raise DeployError(
            f"两步验证密钥不合法（应为 Base32，例如 JBSWY3DPEHPK3PXP）：{exc}") from exc


def _dsm_base(config: dict) -> str:
    base = (config.get("url") or "").rstrip("/")
    if not base:
        raise DeployError("未配置 DSM 地址")
    return base if base.startswith("http") else "https://" + base


def _persist_access_field(access_id, key: str, value: str) -> bool:
    """把值写回授权配置（群晖的「设备令牌」就靠它自动回填）。"""
    if not access_id or not value:
        return False
    try:
        from ..db import SessionLocal
        from ..models import Access
        from ..security import decrypt_json, encrypt_json

        db = SessionLocal()
        try:
            row = db.get(Access, int(access_id))
            if not row:
                return False
            cfg = decrypt_json(row.config) or {}
            if cfg.get(key) == value:
                return False
            cfg[key] = value
            row.config = encrypt_json(cfg)
            db.commit()
            return True
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - 写回失败不影响本次部署
        return False


#: DSM 登录 / 取设备 ID 的错误码 → 中文结论（两条链路共用）
_DSM_LOGIN_HINTS = {
    400: "账号或密码错误",
    401: "账号已停用，或被「自动封锁」限制",
    403: "需要二步验证验证码：先在「获取设备ID」里输一次 6 位码，或填「验证密钥」",
    404: "二步验证验证码缺失或已过期（APP 里的码 30 秒一换，重新取一个再填）",
    406: "二步验证验证码不正确（确认手机时间和 DSM 同步，再取一个码）",
    407: "被 DSM 的 IP 封锁拦下了，先去 DSM 解除封锁",
    409: "该账号没有登录权限（可能只允许特定 IP）",
    410: "设备 ID 已失效（DSM 只记 30 天左右的受信设备），重新点「获取设备ID」换一个",
}


def _dsm_login_error(data: dict, action: str) -> DeployError:
    code = (data.get("error") or {}).get("code")
    hint = _DSM_LOGIN_HINTS.get(code, "")
    text = f"{action}失败，错误码 {code}"
    if hint:
        text += f"：{hint}"
    return DeployError(text)


#: certd 里登录用的会话名（DSM 用它区分会话），对齐 certd 的实现
_DSM_SESSION = "Certd"


def _synology_login_urls(config: dict) -> list[str]:
    """登录地址候选，和 certd 一致：version=="6" 用 auth.cgi，其它用 entry.cgi。

    DSM 7 两个地址都认，所以按顺序试：第一个连不上 / 返回的不是 JSON 就换下一个。
    """
    base = _dsm_base(config)
    version = str(config.get("dsmVersion") or "auto").strip().lower()
    if version.startswith("6"):
        return [f"{base}/webapi/auth.cgi", f"{base}/webapi/entry.cgi"]
    return [f"{base}/webapi/entry.cgi", f"{base}/webapi/auth.cgi"]


def _dsm_get(urls: list[str], params: dict, verify: bool, timeout: int = 20) -> dict:
    """按候选地址顺序 GET，返回第一个能解析成 JSON 的响应（certd 只取一个地址，这里多给了兜底）。"""
    last_error = ""
    for url in urls:
        try:
            resp = net.request("GET", url, timeout=timeout, verify=verify,
                               trust_env=False, params=params)
        except Exception as exc:  # noqa: BLE001
            last_error = f"连不上 {url}：{exc.__class__.__name__}（{exc}）"
            continue
        try:
            data = resp.json()
        except ValueError:
            last_error = (f"{url} 返回的不是 JSON（HTTP {resp.status_code}）："
                          "确认地址指向 DSM 首页、端口是 HTTPS 端口（默认 5001）")
            continue
        # 必须是 DSM 的应答（带 success 字段）才算这个地址可用：
        # 换成别的地址时可能 404 但返回一个合法 JSON（比如 {}），不能就此收工
        if isinstance(data, dict) and "success" in data:
            return data
        last_error = f"{url} 没有返回 DSM 登录应答（HTTP {resp.status_code}）"
        continue
    raise DeployError(last_error or "DSM 登录接口无响应")


def _synology_device_secret(config: dict) -> str:
    """受信设备令牌（certd 的 deviceId / DSM 的 did）；兼容老授权里的 deviceToken。

    老版本把「设备名」写在 deviceId 里（默认值就是 CertHub），那不是令牌：
    拿它当 device_id 去登录必然被 DSM 拒掉，所以这种值要跳过。
    """
    device_name = str(config.get("deviceName") or "").strip() or "CertHub"
    for key in ("deviceId", "deviceToken"):
        value = str(config.get(key) or "").strip()
        if not value:
            continue
        if key == "deviceId" and value in ("CertHub", device_name):
            continue
        return value
    return ""


def _synology_device_name(config: dict) -> str:
    """DSM「信任设备」列表里显示的名字。"""
    return str(config.get("deviceName") or "").strip() or "CertHub"


def _synology_otp_candidates(config: dict) -> list[tuple[str, str]]:
    """能拿来当验证码的来源：临时码 / 验证密钥现算。

    刻意不看「已开启二步验证」开关 —— 那个开关只影响表单显示。
    账号真开了二步验证时 DSM 只认 otp_code，开关关着不发码只会拿到 403。
    """
    codes: list[tuple[str, str]] = []
    temp = re.sub(r"\D", "", str(config.get("otpCode") or ""))
    if len(temp) == 6:
        codes.append(("临时验证码", temp))
    secret = str(config.get("otpSecret") or "").strip()
    if secret:
        try:
            code = _totp_code(secret)
        except DeployError:
            code = ""
        if code:
            codes.append(("验证密钥", code))
    return codes


def synology_fetch_device_id(config: dict, otp_code: str) -> dict:
    """用一次「受信设备登录」换设备 ID —— 对应 certd 的「获取设备ID」。

    请求参数完全照 certd 的 doLoginWithOTPCode：
      api=SYNO.API.Auth, version=6, method=login, account, passwd,
      otp_code=<6 位码>, enable_device_token=yes, device_name=<设备名>
    成功时 DSM 在 data.did 里回设备 ID（certd 的 deviceId 就取这个值）。

    前置条件（DSM 侧）：控制面板 → 安全性 → 勾选
    「允许网页浏览器的用户通过信任设备来跳过双重验证」；
    信任设备列表里会多一条记录，**不要删**，否则设备 ID 立刻失效。
    """
    code = re.sub(r"\D", "", str(otp_code or ""))
    if len(code) != 6:
        raise DeployError("请填写双重认证 APP 上的 6 位数字验证码")

    base = _dsm_base(config)
    verify = not config.get("insecure", True)
    account = str(config.get("username") or "").strip()
    password = str(config.get("password") or "")
    if not account:
        raise DeployError("请先填写群晖账号")
    if not password:
        raise DeployError("请先填写群晖密码（编辑已有授权时留空不覆盖，但取设备ID要用到）")

    device_name = _synology_device_name(config)
    params = {
        "api": "SYNO.API.Auth", "version": "6", "method": "login",
        "account": account, "passwd": password,
        "otp_code": code,
        # certd 用的是 enable_device_token（不是 enable_device_id），少这个词 DSM 不回 did
        "enable_device_token": "yes",
        "device_name": device_name,
    }
    data = _dsm_get(_synology_login_urls(config), params, verify, timeout=25)

    if not data.get("success"):
        error = _dsm_login_error(data, "获取设备ID")
        failed_code = (data.get("error") or {}).get("code")
        if failed_code in (403, 404, 406):
            raise DeployError(
                f"{error}。① 验证码必须是刚生成的（30 秒内），手机时间要和 DSM 同步，"
                "差超过 30 秒会一直被拒；"
                "② 如果这个账号其实没开二步验证，就不用取设备ID，"
                "直接把授权里的「已开启二步验证」关掉即可；"
                "③ 确认 DSM → 控制面板 → 安全性 → 勾选了"
                "「允许网页浏览器的用户通过信任设备来跳过双重验证」") from None
        raise DeployError(
            f"{error}。DSM → 控制面板 → 安全性 → 勾选"
            "「允许网页浏览器的用户通过信任设备来跳过双重验证」后再试") from None

    payload = data.get("data") or {}
    did = str(payload.get("did") or payload.get("device_id") or "").strip()
    if not did:
        raise DeployError(
            "DSM 登录成功但没有返回设备 ID（did）："
            "① 确认这个账号已开启双重认证；"
            "② 确认 DSM → 控制面板 → 安全性 → 勾选了"
            "「允许网页浏览器的用户通过信任设备来跳过双重验证」")
    return {"deviceId": did, "deviceName": device_name,
            "sid": str(payload.get("sid") or ""),
            "synotoken": str(payload.get("synotoken") or "")}


def _synology_otp_mode(config: dict) -> str:
    """把「是否开启二步验证」+「验证码来源」归一到 key / code / none。

    新表单是 twoFactor 开关 + otpType（只剩 key / code）；
    老授权里没有 twoFactor，直接看 otpType（含 none），两种都要能跑。
    注意：这个模式只用于日志与提示，不再决定要不要发验证码（见 _synology_otp_candidates）。
    """
    raw = str(config.get("otpType") or "").strip()
    flag = config.get("twoFactor")
    if flag is None:
        return raw if raw in ("key", "code", "none") else "none"
    if not flag:
        return "none"
    return raw if raw in ("key", "code") else "key"


def _synology_login_failure(data: dict, tried: list[str], otp_required: bool,
                            has_otp: bool, device_rejected: bool) -> DeployError:
    """把登录失败翻成一句能照着做的中文结论。"""
    code = (data.get("error") or {}).get("code")
    hint = _DSM_LOGIN_HINTS.get(code, "")
    head = f"DSM 登录失败，错误码 {code}"
    if hint:
        head += f"（{hint}）"
    tried_text = "、".join(tried) if tried else "账号密码"

    if otp_required and not has_otp:
        tail = (
            "这个账号已开启二步验证，但当前授权里没有可用的验证方式："
            "① 在「授权管理 → 群晖 DSM」点「获取设备ID」，输一次双重认证 APP 上的 6 位码"
            "（推荐，之后长期免验证码）；"
            "② 或者勾上「已开启二步验证」并填「验证密钥」"
            "（DSM → 个人设置 → 双重认证 →「遗失手机或设备」里的 Base32 密钥）"
        )
        if device_rejected:
            tail += "。另外：已保存的设备 ID 可能已失效（DSM 只记 30 天左右），重新获取一次即可"
        return DeployError(f"{head}。{tail}（本次已尝试：{tried_text}）")

    if otp_required and has_otp:
        return DeployError(
            f"{head}。账号开了二步验证，但这次提交的验证码没被接受："
            "先确认手机时间与 DSM 同步（TOTP 差超过 30 秒就会一直被拒），"
            "再点「获取设备ID」重新输一次最新验证码"
            f"（本次已尝试：{tried_text}）")

    return DeployError(f"{head}（本次已尝试：{tried_text}）")


def _synology_login(config: dict, log: Callable | None = None) -> dict:
    """登录 DSM，返回 {sid, synotoken, device_token, base, verify, otp_mode}。

    「每条腿」的参数都照 certd 的 SynologyClient：
      * 有设备 ID → doLoginWithDeviceId：device_name + device_id +
        session=Certd + format=sid + enable_syno_token=yes（不带验证码）；
      * 没有设备 ID → doLoginWithOTPCode：otp_code + enable_device_token=yes + device_name
        （DSM 会顺手回一个 did，写回授权后长期免验证码）；
      * 都没有 → doLogin：纯账号密码 + session=Certd + format=sid + enable_syno_token=yes。
    前一条失败会自动降级到下一条，并把失败原因写进日志，403 时给出可操作的结论。
    """
    log = log or (lambda _m: None)
    verify = not config.get("insecure", True)
    urls = _synology_login_urls(config)
    base = _dsm_base(config)

    otp_mode = _synology_otp_mode(config)
    device_token = _synology_device_secret(config)
    device_name = _synology_device_name(config)
    otp_sources = _synology_otp_candidates(config)

    account = str(config.get("username") or "")
    password = str(config.get("password") or "")

    def login_with_device(device_id: str) -> dict:
        params = {
            "api": "SYNO.API.Auth", "version": "6", "method": "login",
            "account": account, "passwd": password,
            "device_name": device_name, "device_id": device_id,
            "session": _DSM_SESSION, "format": "sid", "enable_syno_token": "yes",
        }
        return _dsm_get(urls, params, verify)

    def login_with_otp(otp_code: str) -> dict:
        params = {
            "api": "SYNO.API.Auth", "version": "6", "method": "login",
            "account": account, "passwd": password,
            "otp_code": otp_code,
            "enable_device_token": "yes", "device_name": device_name,
        }
        return _dsm_get(urls, params, verify)

    def login_plain() -> dict:
        params = {
            "api": "SYNO.API.Auth", "version": "6", "method": "login",
            "account": account, "passwd": password,
            "session": _DSM_SESSION, "format": "sid", "enable_syno_token": "yes",
        }
        return _dsm_get(urls, params, verify)

    mode_text = "关闭"
    if otp_mode == "key":
        mode_text = "验证密钥自动生成"
    elif otp_mode == "code":
        mode_text = "临时验证码"
    log(f"登录 DSM：{base}（设备名 {device_name}，二步验证 {mode_text}"
        f"{'，有已保存的设备 ID' if device_token else ''}）")

    data: dict = {}
    tried: list[str] = []
    otp_required = False
    device_rejected = False

    if device_token:
        tried.append("设备ID")
        data = login_with_device(device_token)
        if not data.get("success"):
            failed_code = (data.get("error") or {}).get("code")
            if failed_code == 403:
                otp_required = True
            if failed_code in (400, 401, 403, 404, 406, 410):
                device_rejected = True
            log(f"设备 ID 登录失败（错误码 {failed_code}），改用验证码重试")

    for label, code_text in otp_sources:
        if data.get("success"):
            break
        tried.append(label)
        log(f"使用「{label}」登录 DSM")
        data = login_with_otp(code_text)
        if not data.get("success"):
            failed_code = (data.get("error") or {}).get("code")
            if failed_code == 403:
                otp_required = True
            log(f"「{label}」登录失败（错误码 {failed_code}）")

    if not data.get("success"):
        # 兜底：什么都不带，纯账号密码（多数没开二步验证的 DSM 走这条）
        tried.append("账号密码")
        data = login_plain()
        if not data.get("success"):
            failed_code = (data.get("error") or {}).get("code")
            if failed_code == 403:
                otp_required = True

    if not data.get("success"):
        raise _synology_login_failure(data, tried, otp_required,
                                      bool(otp_sources), device_rejected)

    payload = data.get("data") or {}
    sid = payload.get("sid")
    if not sid:
        raise DeployError("DSM 登录成功但没有返回 sid，可能是 DSM 版本不受支持")

    synotoken = str(payload.get("synotoken") or "")
    did = str(payload.get("did") or payload.get("device_id") or "").strip()
    if did and did != device_token:
        saved = _persist_access_field(config.get("accessId"), "deviceId", did)
        log(f"已获取设备 ID（{device_name}）"
            f"{'，已写回授权配置，下次免验证码' if saved else ''}")
    log("DSM 登录成功")
    return {"sid": sid, "synotoken": synotoken, "device_token": did or device_token,
            "base": base, "verify": verify, "otp_mode": otp_mode}


def _dsm_firmware(base: str, sid: str, verify: bool) -> str:
    """问一次 DSM 固件版本（SYNO.Core.System.info），拿不到就返回空串。"""
    try:
        resp = net.request("GET", f"{base}/webapi/entry.cgi", timeout=15, verify=verify,
                           trust_env=False,
                           params={"api": "SYNO.Core.System", "version": "1",
                                   "method": "info", "_sid": sid})
        data = (resp.json() or {}).get("data") or {}
    except Exception:  # noqa: BLE001 - 版本只是锦上添花，查不到不影响连通性结论
        return ""
    text = str(data.get("firmware_ver") or "").strip()
    if text:
        return text
    major, minor = data.get("majorversion"), data.get("minorversion")
    if major and minor:
        return f"{major}.{minor}"
    return ""


def _dsm_cert_api_version(base: str, verify: bool, sid: str = "") -> str:
    """用 SYNO.API.Info 判断证书导入接口属于 7.1+ 还是 7.0，返回 '7.1' / '7.0' / ''。

    带上 _sid：部分 DSM 版本对未登录的 query.cgi 直接返回空，那样就白问了。
    """
    params = {"api": "SYNO.API.Info", "version": "1", "method": "query",
              "query": "SYNO.Core.Certificate.CRT,SYNO.Core.Certificate,SYNO.Core.System"}
    if sid:
        params["_sid"] = sid
    try:
        info = net.request("GET", f"{base}/webapi/query.cgi", timeout=15, verify=verify,
                           trust_env=False, params=params)
        payload = info.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return ""
    if "SYNO.Core.Certificate.CRT" in payload:
        return "7.1"
    if "SYNO.Core.Certificate" in payload:
        return "7.0"
    return ""


def synology_probe(config: dict) -> str:
    """「授权管理 → 测试」：真登录一次 DSM，把版本 / 二步验证 / 设备令牌查清楚。

    识别到具体版本时顺手写回授权配置（dsmVersion），用户不用自己猜是 7.0 还是 7.1，
    之后部署也直接按这个版本选接口，省掉一次失败重试。
    """
    result = _synology_login(config)
    base, verify, sid = result["base"], result["verify"], result["sid"]

    parts = [f"地址 {base}"]

    firmware = _dsm_firmware(base, sid, verify)
    api_version = _dsm_cert_api_version(base, verify, sid)
    version_bits: list[str] = []
    if firmware:
        version_bits.append(f"DSM {firmware}")
    if api_version:
        # 导入接口在 DSM 6/7 都是 SYNO.Core.Certificate；.CRT 只用来列表，这里报的是列表接口
        version_bits.append("证书列表接口 " + ("7.1+" if api_version == "7.1" else "7.0"))
    if version_bits:
        parts.append(" / ".join(version_bits))

    current_version = str(config.get("dsmVersion") or "auto").strip()
    if api_version and current_version == "auto":
        if _persist_access_field(config.get("accessId"), "dsmVersion", api_version):
            parts.append(f"版本已回填为 {api_version}")
    elif not api_version and current_version == "auto":
        parts.append("未识别到证书导入接口（版本保持自动，必要时手动指定 7.0 / 7.1）")

    otp_text = {"key": "已开启（验证密钥自动生成）",
                "code": "已开启（临时验证码）",
                "none": "未开启"}.get(result["otp_mode"], result["otp_mode"])
    parts.append(f"二步验证 {otp_text}")
    parts.append(f"设备名 {_synology_device_name(config)}")
    if result["device_token"]:
        parts.append("设备ID已保存（受信设备，登录免验证码）")
    else:
        parts.append("还没有设备ID：点「获取设备ID」输一次 6 位验证码，之后长期免验证码")

    return "群晖 DSM 连接成功（" + "，".join(parts) + "）"


def _dsm_api(base: str, verify: bool, sid: str, synotoken: str,
             params: dict, files: dict | None = None, form_fields: dict | None = None,
             timeout: float = 60) -> dict:
    """调一次 DSM 的 entry.cgi（等价 certd 的 doRequest：带上 _sid 与 SynoToken）。

    files 非空时走 multipart：id / desc 这类普通字段必须放进**表单体**（form_fields），
    塞在 query 里 DSM 读不到——certd 也是 form.append("id", ...) 这么传的。
    """
    query = dict(params)
    if sid:
        query["_sid"] = sid
    if synotoken:
        query["SynoToken"] = synotoken
    kwargs = {"verify": verify, "params": query}
    if files:
        if form_fields:
            kwargs["data"] = form_fields
        kwargs["files"] = files
    resp = _panel_request("POST" if files else "GET", f"{base}/webapi/entry.cgi",
                          timeout=timeout, **kwargs)
    try:
        data = resp.json()
    except ValueError:
        raise DeployError(f"DSM 返回的不是 JSON（HTTP {resp.status_code}）：{resp.text[:160]}") from None
    return data if isinstance(data, dict) else {}


def _dsm_cert_list(base: str, verify: bool, sid: str, synotoken: str) -> list[dict]:
    """列出 DSM 证书库里的证书（DSM 7 用 .CRT 的 list，DSM 6 用 SYNO.Core.Certificate）。"""
    for api_name in ("SYNO.Core.Certificate.CRT", "SYNO.Core.Certificate"):
        try:
            data = _dsm_api(base, verify, sid, synotoken,
                            {"api": api_name, "version": "1", "method": "list"})
        except DeployError:
            continue
        if data.get("success"):
            return data.get("data", {}).get("certificates") or []
    return []


def _dsm_cert_names(cert: dict) -> set[str]:
    """一张证书上能用来匹配的名字：desc + subject/alt 里的域名（保留 *. 前缀）。"""
    names: set[str] = set()
    desc = str(cert.get("desc") or "").strip().lower()
    if desc:
        names.add(desc)
    subject = cert.get("subject") or {}
    if isinstance(subject, dict):
        for key in ("common_name", "alt_name"):
            value = subject.get(key)
            if isinstance(value, str):
                for item in value.split(","):
                    item = item.strip().lower()
                    if item:
                        names.add(item)
    return names


def _dsm_name_matches(cert_name: str, domain: str) -> bool:
    """证书上的名字是否覆盖某个域名（通配符只覆盖一级子域名，和浏览器校验一致）。"""
    cert_name = (cert_name or "").strip().lower().strip(".")
    domain = (domain or "").strip().lower().lstrip("*.").strip(".")
    if not cert_name or not domain:
        return False
    if cert_name == domain:
        return True
    if cert_name.startswith("*."):
        base = cert_name[2:]
        return domain.endswith("." + base) and domain.count(".") == base.count(".") + 1
    return False


def _dsm_pick_cert(certs: list[dict], desc: str, domains: list[str]) -> dict | None:
    """在 DSM 证书库里挑出要替换的那张：先按名称精确匹配，再按域名（含通配）匹配。"""
    wanted_desc = (desc or "").strip().lower()
    if wanted_desc:
        for cert in certs:
            if str(cert.get("desc") or "").strip().lower() == wanted_desc:
                return cert
    wanted_domains = [d for d in (domain.strip() for domain in domains) if d]
    if wanted_domains:
        for cert in certs:
            names = _dsm_cert_names(cert)
            for domain in wanted_domains:
                if any(_dsm_name_matches(name, domain) for name in names):
                    return cert
    return None


def _split_pem_chain(pem: str) -> tuple[str, str]:
    """把证书链拆成 (站点证书, 中间证书)，DSM 的 import 接口是分两个字段收的。"""
    blocks = _chain_blocks(pem)
    if not blocks:
        return pem, ""
    leaf = blocks[0].strip() + "\n"
    inter = "\n".join(b.strip() for b in blocks[1:]) + ("\n" if len(blocks) > 1 else "")
    return leaf, inter


def deploy_to_synology(ctx: CertContext, config: dict, log: Callable) -> None:
    """上传证书到群晖 DSM 证书库，可选设为默认证书。

    请求形态照 certd / acme.sh 的做法（DSM 6/7 通用）：
      * list：SYNO.Core.Certificate.CRT（7.x）或 SYNO.Core.Certificate（6.x），method=list
      * import：SYNO.Core.Certificate + method=import，multipart 传 key / cert / inter_cert，
        并带 id（要替换的那张证书）+ desc
      * 设默认：SYNO.Core.Certificate + method=set_default，带 id
    之前在 .CRT 上直接调 import，DSM 回 {"code":103}（那个 API 没有 import 方法）。
    """
    session = _synology_login(config, log)
    sid = session["sid"]
    synotoken = session.get("synotoken", "")
    base, verify = session["base"], session["verify"]

    desc = ctx.render(str(config.get("certDesc") or "")) or ctx.domain
    as_default = bool(config.get("asDefault", True))
    domains = list(ctx.domains or []) or [ctx.domain]

    certs = _dsm_cert_list(base, verify, sid, synotoken)
    target = _dsm_pick_cert(certs, desc, domains)
    if target:
        log(f"DSM 证书库里已有同名证书（id={target.get('id')}，名称「{target.get('desc')}」），本次覆盖它")
    else:
        log(f"DSM 证书库里没有「{desc}」对应的证书，尝试新建一张")

    leaf, inter = _split_pem_chain(ctx.crt)
    files = {
        "key": ("key.pem", ctx.key.encode(), "application/x-pem-file"),
        "cert": ("cert.pem", leaf.encode(), "application/x-pem-file"),
    }
    if inter:
        files["inter_cert"] = ("inter.pem", inter.encode(), "application/x-pem-file")

    form_fields = {"desc": desc}
    if target and target.get("id") is not None:
        form_fields["id"] = str(target.get("id"))

    data = _dsm_api(base, verify, sid, synotoken,
                    {"api": "SYNO.Core.Certificate", "version": "1", "method": "import"},
                    files=files, form_fields=form_fields, timeout=120)
    if not data.get("success"):
        error = json.dumps(data.get("error"), ensure_ascii=False)
        code = (data.get("error") or {}).get("code")
        hint = ""
        if code in (101, 102, 103):
            hint = ("；DSM 的证书导入接口在方法/参数不匹配时会回 101~103。"
                    "先在 DSM「控制面板 → 安全性 → 证书」里建一张同名证书"
                    f"（或者把「证书名称」改成库里已存在的名字，例如 {desc}），再重试")
        elif code in (105, 106, 107):
            hint = "；会话失效了，重新运行一次流水线即可"
        raise DeployError(f"DSM 导入证书失败：{error}{hint}")

    cert_id = None
    result = data.get("data") or {}
    if isinstance(result, dict):
        cert_id = result.get("id") or result.get("cert_id")
    if cert_id is None and target:
        cert_id = target.get("id")
    log(f"证书已导入 DSM（名称「{desc}」{('，id=' + str(cert_id)) if cert_id else ''}）")

    if not as_default or cert_id is None:
        return
    default_data = _dsm_api(base, verify, sid, synotoken,
                            {"api": "SYNO.Core.Certificate", "version": "1",
                             "method": "set_default", "id": str(cert_id)})
    if default_data.get("success"):
        log("已把这张证书设为 DSM 默认证书")
    else:
        # 设默认失败不影响证书已经导入，只提醒一句
        log("设为默认证书失败（证书已导入，可到 DSM 控制台手动设为默认）："
            + json.dumps(default_data.get("error"), ensure_ascii=False))


def deploy_to_qnap(ctx: CertContext, config: dict, log: Callable) -> None:
    """上传证书到威联通 QTS 系统证书库。

    QTS 的证书接口各固件版本差异较大，这里走 sslUtils.cgi 的 ssl_import 子功能，
    失败时把服务端原文一并抛出，便于按固件版本调整。
    """
    base = (config.get("url") or "").rstrip("/")
    if not base:
        raise DeployError("未配置 QTS 地址")
    verify = not config.get("insecure", True)

    log(f"登录 QTS：{base}")
    login_pwd = base64.b64encode((config.get("password") or "").encode()).decode()
    resp = _panel_request("POST", f"{base}/cgi-bin/authLogin.cgi", timeout=30,
                          verify=verify, data={
        "user": config.get("username", ""), "pwd": login_pwd, "serviceKey": "1",
    })
    text = resp.text

    sid = ""
    if "<authPassed><![CDATA[1]]></authPassed>" in text:
        import re

        m = re.search(r"<authSid><!\[CDATA\[(.*?)\]\]></authSid>", text)
        sid = m.group(1) if m else ""
    if not sid:
        raise DeployError("QTS 登录失败：账号密码错误，或该固件不支持 sslUtils 接口")

    log("QTS 登录成功，开始上传证书")
    files = {
        "cert": ("cert.pem", ctx.crt.encode(), "application/x-pem-file"),
        "key": ("key.pem", ctx.key.encode(), "application/x-pem-file"),
    }
    resp = _panel_request("POST", f"{base}/cgi-bin/sslUtils.cgi", timeout=120,
                          verify=verify, params={"subfunc": "ssl_import", "sid": sid},
                          files=files)
    if resp.status_code >= 400 or "error" in resp.text.lower()[:200]:
        raise DeployError(f"QTS 导入证书失败（HTTP {resp.status_code}）：{resp.text[:300]}")
    log("威联通 QTS 证书部署完成")


# ---------------------------------------------------------------- Proxmox VE
def deploy_to_proxmox(ctx: CertContext, config: dict, log: Callable) -> None:
    """上传证书到 PVE 节点的 custom 证书目录，PVE 会自动重载 pveproxy。"""
    base = (config.get("url") or "").rstrip("/")
    if not base:
        raise DeployError("未配置 PVE 地址")
    node = config.get("node") or "pve"
    token_id = config.get("tokenId") or ""
    token_secret = config.get("tokenSecret") or ""
    if not token_id or not token_secret:
        raise DeployError("未配置 PVE API Token")
    headers = {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}
    verify = not config.get("insecure", True)

    log(f"上传证书到 PVE 节点 {node}")
    resp = _panel_request(
        "POST", f"{base}/api2/json/nodes/{node}/certificates/custom",
        timeout=120, verify=verify, headers=headers,
        data={"certificates": ctx.crt, "key": ctx.key, "force": "1"},
    )
    if resp.status_code >= 400:
        raise DeployError(f"PVE 上传证书失败（HTTP {resp.status_code}）：{resp.text[:300]}")

    if config.get("restart", True):
        # PVE 上传 custom 证书后会自动重载 pveproxy，这里再显式调一次重启接口，
        # 部分老版本没有该接口，失败不影响结果
        try:
            r = _panel_request("POST", f"{base}/api2/json/nodes/{node}/certificates/custom/restart",
                               timeout=60, verify=verify, headers=headers)
            log(f"重载 pveproxy：HTTP {r.status_code}")
        except DeployError as exc:
            log(f"重载 pveproxy 跳过：{exc}")
    log("Proxmox VE 证书部署完成")


# ---------------------------------------------------------------- 火山引擎证书中心
def deploy_to_volcengine(ctx: CertContext, config: dict, log: Callable) -> None:
    from . import volcengine

    name = ctx.render(config.get("certName") or "{domain}-{timestamp}")
    result = volcengine.import_certificate(config, ctx.domain, ctx.crt, ctx.key, log, alias=name)
    log(f"火山引擎证书托管完成：{result.get('instanceId') or '（未返回实例 ID）'}")


DEPLOY_HANDLERS = {
    "DeployToHost": deploy_to_host,
    "DeployToLocal": deploy_to_local,
    "DeployToAliyunCdn": deploy_to_aliyun_cdn,
    "DeployToTencentCdn": deploy_to_tencent_cdn,
    "DeployToQiniu": deploy_to_qiniu,
    "DeployToBaota": deploy_to_baota,
    "DeployTo1Panel": deploy_to_1panel,
    "DeployToSynology": deploy_to_synology,
    "DeployToQnap": deploy_to_qnap,
    "DeployToProxmox": deploy_to_proxmox,
    "DeployToVolcengine": deploy_to_volcengine,
    "DeployToWebhook": deploy_to_webhook,
}

# 扩展插件（对象存储 / SSH 服务预设 / 面板 / 更多云 CDN）在 deploy_ext 里，
# 由它自己往 DEPLOY_HANDLERS 注册。依赖方向是单向的（ext → deploy），
# 这里不能再反向 import，否则从 ext 侧导入时会撞上「半初始化模块」。
