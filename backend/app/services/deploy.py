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
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from . import net


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
    domain = ctx.render(config.get("domain") or ctx.domain)
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
    domain = ctx.render(config.get("domain") or ctx.domain)
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


def _synology_otp_mode(config: dict) -> str:
    """把「是否开启二步验证」+「验证码来源」归一到 key / code / none。

    新表单是 twoFactor 开关 + otpType（只剩 key / code）；
    老授权里没有 twoFactor，直接看 otpType（含 none），两种都要能跑。
    """
    raw = str(config.get("otpType") or "").strip()
    flag = config.get("twoFactor")
    if flag is None:
        return raw if raw in ("key", "code", "none") else "none"
    if not flag:
        return "none"
    return raw if raw in ("key", "code") else "key"


def _synology_login(config: dict, log: Callable | None = None) -> dict:
    """登录 DSM，返回 {sid, device_token, base, verify, otp_mode}。

    二步验证有两条路：
      1. 一直用验证密钥（TOTP）现算——稳定，但要能拿到 Base32 密钥；
      2. 登录一次拿到「设备令牌」（did），之后用 device_id 免验证码——
         更省事，所以登录成功后会把 did 写回授权配置。
    两条都支持，谁有就用谁。
    """
    log = log or (lambda _m: None)
    base = _dsm_base(config)
    verify = not config.get("insecure", True)

    otp_mode = _synology_otp_mode(config)
    device_id = str(config.get("deviceId") or "").strip()
    device_token = str(config.get("deviceToken") or "").strip()

    otp_code = ""
    if otp_mode == "code":
        otp_code = str(config.get("otpCode") or "").strip()
        if not otp_code:
            raise DeployError(
                "「已开启二步验证」且验证码来源是「临时验证码」，但 6 位验证码是空的。"
                "临时验证码 30 秒就过期，长期自动续签请把来源改成「验证密钥」")
    elif otp_mode == "key":
        secret = str(config.get("otpSecret") or "").strip()
        if not secret and not device_token:
            raise DeployError(
                "「已开启二步验证」但验证密钥是空的：DSM → 个人设置 → 双重认证 → "
                "「遗失手机或设备」里能拿到 Base32 密钥（例：JBSWY3DPEHPK3PXP）。"
                "如果这台设备已经存过令牌，清空「设备令牌」重试即可重新生成")
        otp_code = _totp_code(secret)
        if otp_code:
            log("已用「验证密钥」自动生成验证码")

    params = {
        "api": "SYNO.API.Auth", "version": "6", "method": "login",
        "account": config.get("username", ""), "passwd": config.get("password", ""),
        "session": "Certificate", "format": "sid",
    }
    if device_id:
        params["device_name"] = device_id
        params["enable_device_token"] = "yes"
    if device_token:
        params["device_id"] = device_token
    if otp_code:
        params["otp_code"] = otp_code

    log(f"登录 DSM：{base}（设备 {device_id or '-'}，二步验证 "
        f"{'关闭' if otp_mode == 'none' else ('验证密钥' if otp_mode == 'key' else '临时验证码')}"
        f"{'，使用已保存的设备令牌' if device_token else ''}）")
    try:
        resp = net.request("GET", f"{base}/webapi/auth.cgi", timeout=20,
                           verify=verify, trust_env=False, params=params)
    except Exception as exc:  # noqa: BLE001
        raise DeployError(f"连不上 {base}：{exc.__class__.__name__}（{exc}）") from exc
    try:
        data = resp.json()
    except ValueError:
        raise DeployError(
            f"DSM 登录接口返回的不是 JSON（HTTP {resp.status_code}）："
            f"确认地址指向 DSM 首页、端口是 HTTPS 端口（默认 5001）") from None

    if not data.get("success"):
        code = (data.get("error") or {}).get("code")
        hints = {
            400: "账号或密码错误",
            401: "账号已停用，或被「自动封锁」限制",
            403: "需要二步验证验证码：打开「已开启二步验证」并填「验证密钥」",
            404: "二步验证验证码缺失或已过期：填「验证密钥」（长期）或临时 6 位验证码",
            407: "被 DSM 的 IP 封锁拦下了，先去 DSM 解除封锁",
            409: "该账号没有登录权限（可能只允许特定 IP）",
        }
        hint = hints.get(code, "")
        raise DeployError(f"DSM 登录失败，错误码 {code}" + (f"：{hint}" if hint else ""))

    payload = data.get("data") or {}
    sid = payload.get("sid")
    if not sid:
        raise DeployError("DSM 登录成功但没有返回 sid，可能是 DSM 版本不受支持")
    did = str(payload.get("did") or "").strip()
    if did and did != device_token:
        saved = _persist_access_field(config.get("accessId"), "deviceToken", did)
        log(f"已获取设备令牌（{device_id or 'CertHub'}）"
            f"{'，已写回授权配置，下次免验证码' if saved else ''}")
    log("DSM 登录成功")
    return {"sid": sid, "device_token": did or device_token, "base": base,
            "verify": verify, "otp_mode": otp_mode}


def _dsm_cert_apis(config: dict) -> list[str]:
    """按「群晖版本」决定试哪个证书导入接口。"""
    version = str(config.get("dsmVersion") or "auto").strip()
    if version == "7.1":
        return ["SYNO.Core.Certificate.CRT"]
    if version == "7.0":
        return ["SYNO.Core.Certificate"]
    # 自动：7.1+ 优先，失败退回 7.0 的旧接口
    return ["SYNO.Core.Certificate.CRT", "SYNO.Core.Certificate"]


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
        version_bits.append("证书接口 " + ("7.1+" if api_version == "7.1" else "7.0"))
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
    parts.append(f"设备 ID {str(config.get('deviceId') or '').strip() or 'CertHub'}")
    if result["device_token"]:
        parts.append("设备令牌已保存（下次免验证码）")

    return "群晖 DSM 连接成功（" + "，".join(parts) + "）"


def deploy_to_synology(ctx: CertContext, config: dict, log: Callable) -> None:
    """上传证书到群晖 DSM 证书库，可选设为默认证书。

    DSM 7.0 用 SYNO.Core.Certificate 导入，7.1+ 换成 SYNO.Core.Certificate.CRT；
    按「群晖版本」选接口，自动模式下两个都试，命中哪个记哪个。
    """
    session = _synology_login(config, log)
    sid = session["sid"]
    base, verify = session["base"], session["verify"]

    desc = ctx.render(str(config.get("certDesc") or "")) or ctx.domain
    as_default = bool(config.get("asDefault", True))
    files = {
        "key": ("key.pem", ctx.key.encode(), "application/x-pem-file"),
        "cert": ("cert.pem", ctx.crt.encode(), "application/x-pem-file"),
    }

    errors: list[str] = []
    for api_name in _dsm_cert_apis(config):
        form = {"api": api_name, "version": "1", "method": "import",
                "desc": desc, "_sid": sid}
        if as_default:
            form["as_default"] = "true"
        resp = _panel_request("POST", f"{base}/webapi/entry.cgi", timeout=120,
                              verify=verify, params=form, files=files)
        try:
            data = resp.json()
        except ValueError:
            errors.append(f"{api_name} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:120]}")
            continue
        if data.get("success"):
            log(f"证书已导入 DSM（接口 {api_name}，名称「{desc}」"
                f"{'，已设为默认证书' if as_default else ''}）")
            return
        errors.append(f"{api_name}：{json.dumps(data.get('error'), ensure_ascii=False)}")

    raise DeployError(
        "DSM 导入证书失败：" + "；".join(errors)[:400]
        + "。若版本不确定，把「群晖版本」从自动改成具体版本再试")


# ---------------------------------------------------------------- 威联通 QTS
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
