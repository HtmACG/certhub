"""国内 CDN / 云厂商证书部署（certd 插件复刻）。

这里补齐国内常用的几家 CDN 服务商：

- 天翼云（CTyun，open.ctcdn.cn，x-alogic 签名）
- 括彩云 CDN（kuocaicdn.com，账号密码换 Cookie/Session）
- 易盾 DCDN（user.yiduncdn.com，api-key / api-secret 头）
- 白山云（cdn.api.baishan.com，token 走 query）
- 多吉云（api.dogecloud.com，TOKEN ak:HMAC-SHA1 签名）
- 我爱云（console.edeg.ttzi.cn，账号密码换 Token）
- 京东云（ssl / cdn.jdcloud-api.com，JDCLOUD2-HMAC-SHA256，结构同 AWS SigV4）

接口路径与参数以 certd 对应插件为准（那些是在真实账号上跑通过的）。
所有 handler 统一签名 handler(ctx, config, log)，注册进 deploy.DEPLOY_HANDLERS。
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import string
import time
import urllib.parse
import re
import uuid
from typing import Callable

import httpx

from .deploy import CertContext, DeployError, _cloud_request

HANDLERS: dict[str, Callable] = {}

_B64_CHARS = set(string.ascii_letters + string.digits + "+/=")


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


# ================================================================ 公共小工具
def _node_b64decode(text: str) -> bytes:
    """复刻 Node 的 Buffer.from(s, "base64")：忽略字母表之外的字符。

    天翼云签名把上一轮签名结果当密钥用，而那个结果是用 base64url 表示的，
    Node 解码时会直接丢掉 '-' 和 '_'；要和服务端算出同样的值就得照它的行为来。
    """
    cleaned = "".join(ch for ch in text if ch in _B64_CHARS)
    cleaned += "=" * ((-len(cleaned)) % 4)
    return base64.b64decode(cleaned)


def _b64url(data: bytes) -> str:
    return base64.b64encode(data).decode().replace("+", "-").replace("/", "_").rstrip("=")


def _json_or_text(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise DeployError(f"接口返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if not isinstance(data, dict):
        raise DeployError(f"接口返回格式异常：{resp.text[:200]}")
    return data


def _base_url(config: dict, default: str) -> str:
    """接口地址：默认用官方域名，可通过授权里的 baseUrl 覆盖（自建反代 / 测试用）。"""
    return (config.get("baseUrl") or default).rstrip("/")


def _as_list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


# ================================================================ 天翼云
def _ctyun_headers(config: dict, uri: str, now_ms: int | None = None) -> dict:
    """天翼云 open.ctcdn.cn 的 x-alogic 签名。

    content       = AK \n 毫秒时间戳 \n uri（含 query）
    authorizedKey = HMAC-SHA256(SK 的 base64 解码值, "AK:天数")
    signature     = HMAC-SHA256(authorizedKey, content)
    两次 HMAC 结果都用 base64url 表示。
    """
    ak = config.get("accessKeyId") or ""
    sk = config.get("securityKey") or ""
    if not ak or not sk:
        raise DeployError("天翼云授权缺少 accessKeyId / securityKey")

    now_ms = now_ms or int(time.time() * 1000)
    first = hmac.new(_node_b64decode(sk), f"{ak}:{now_ms // 86400000}".encode(),
                     hashlib.sha256).digest()
    auth_key = _node_b64decode(_b64url(first))
    signature = _b64url(hmac.new(auth_key, f"{ak}\n{now_ms}\n{uri}".encode(),
                                 hashlib.sha256).digest())
    return {
        "x-alogic-now": str(now_ms),
        "x-alogic-app": ak,
        "x-alogic-signature": signature,
        "x-alogic-ac": "app",
        "Content-Type": "application/json",
    }


def ctyun_request(config: dict, method: str, uri: str, data: dict | None = None) -> dict:
    """调一次天翼云 API。GET 的查询串要算进签名，所以先拼 uri 再签名。"""
    if method.upper() == "GET" and data:
        uri = uri + "?" + urllib.parse.urlencode(data)
    headers = _ctyun_headers(config, uri)
    resp = _cloud_request(method.upper(), _base_url(config, "https://open.ctcdn.cn") + uri,
                          headers=headers,
                          json=data if method.upper() != "GET" else None)
    body = _json_or_text(resp)
    if body.get("code") != 100000:
        raise DeployError(f"天翼云 {uri} 失败：[{body.get('code')}] {body.get('message')}")
    return body


def ctyun_domains(config: dict, product_code: str = "008") -> list[dict]:
    body = ctyun_request(config, "GET", "/v2/domain/query",
                         {"product_code": product_code, "page_size": 100})
    return body.get("result") or []


@_register("DeployToCtyunCdn")
def deploy_to_ctyun_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """天翼云 CDN / 全站加速：先建证书，再批量改域名的 https 配置。"""
    product_code = config.get("productCode") or "008"
    domains = _as_list(config.get("domains")) or [ctx.domain]
    cert_name = ctx.render(config.get("certName") or "certd-{domain}-{timestamp}")

    log(f"天翼云：创建证书 {cert_name}")
    created = ctyun_request(config, "POST", "/v1/cert/create", {
        "name": cert_name, "key": ctx.key, "certs": ctx.crt,
    })
    log(f"证书创建成功，ID={created.get('id')}")

    result = ctyun_request(config, "POST", "/v1/domain/batch_update_configuration_information", {
        "domain": domains, "product_code": product_code,
        "cert_name": cert_name, "https_status": "on",
    })
    failed = []
    for detail in result.get("domain_details") or []:
        code = detail.get("code")
        if code == 100000:
            continue
        message = f"{detail.get('domain')}：[{code}] {detail.get('message')}"
        # 工单在途不是错误：控制台上已经有一次配置没跑完
        if "工单" in str(detail.get("message")) or "操作中" in str(detail.get("message")):
            log(f"跳过（域名正在操作中）：{message}")
            continue
        failed.append(message)
    if failed:
        raise DeployError("天翼云部署失败：" + "；".join(failed))
    log(f"天翼云部署完成：{', '.join(domains)}")


# ================================================================ 括彩云
def kuocai_login(config: dict) -> dict:
    """账号密码登录，返回 {sessionId, token}（后续请求放在 Cookie 里）。"""
    username = config.get("username") or ""
    password = config.get("password") or ""
    if not username or not password:
        raise DeployError("括彩云授权缺少账号或密码")

    resp = _cloud_request("POST", _base_url(config, "https://kuocaicdn.com") + "/login/loginUser",
                          data={"userAccount": username, "userPwd": password, "remember": "true"},
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    body = _json_or_text(resp)
    if not body.get("success"):
        raise DeployError(f"括彩云登录失败：{body.get('message')}")

    session_id = ""
    for cookie in resp.cookies.jar:
        if cookie.name.upper() == "JSESSIONID":
            session_id = cookie.value
    if not session_id:
        raw = resp.headers.get("set-cookie") or ""
        for part in raw.split(";"):
            if part.strip().upper().startswith("JSESSIONID="):
                session_id = part.split("=", 1)[1]
    return {"sessionId": session_id, "token": body.get("data") or ""}


def kuocai_request(config: dict, path: str, data: dict,
                   login: dict | None = None) -> dict:
    login = login or kuocai_login(config)
    cookie = f"JSESSIONID={login['sessionId']};kuocai_cdn_token={login['token']}"
    resp = _cloud_request("POST", _base_url(config, "https://kuocaicdn.com") + path,
                          json=data, headers={"Cookie": cookie})
    body = _json_or_text(resp)
    if not body.get("success"):
        raise DeployError(f"括彩云 {path} 失败：{body.get('message')}")
    return body


def kuocai_domains(config: dict) -> list[dict]:
    body = kuocai_request(config, "/CdnDomain/queryForDatatables",
                          {"draw": 1, "start": 0, "length": 1000,
                           "search": {"value": "", "regex": False}})
    return ((body.get("data") or {}).get("data")) or []


@_register("DeployToKuocaiCdn")
def deploy_to_kuocai_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """括彩云 CDN：按域名绑定证书（内部会换成域名 ID）。"""
    wanted = _as_list(config.get("domains")) or [ctx.domain]
    login = kuocai_login(config)
    log("括彩云登录成功")

    by_name = {}
    for item in kuocai_domains(config):
        by_name[str(item.get("domainName") or "").lower()] = item.get("id")

    cert_name = ctx.render(config.get("certName") or "certd-{domain}-{timestamp}")
    for domain in wanted:
        domain_id = domain if domain.isdigit() else by_name.get(domain.lower())
        if not domain_id:
            raise DeployError(f"括彩云里找不到加速域名：{domain}（请先在控制台添加）")
        kuocai_request(config, "/CdnDomainHttps/httpsConfiguration", {
            "doMainId": domain_id,
            "https": {
                "https_status": "on",
                "certificate_name": cert_name,
                "certificate_source": "0",
                "certificate_value": ctx.crt,
                "private_key": ctx.key,
            },
        }, login)
        log(f"括彩云域名 {domain} 证书更新成功")


# ================================================================ 易盾
def yidun_request(config: dict, method: str, path: str, data: dict | None = None) -> dict:
    api_key = config.get("apiKey") or ""
    api_secret = config.get("apiSecret") or ""
    if not api_key or not api_secret:
        raise DeployError("易盾授权缺少 apiKey / apiSecret")

    resp = _cloud_request(method.upper(), _base_url(config, "http://user.yiduncdn.com") + path,
                          json=data if method.upper() != "GET" else None,
                          params=data if method.upper() == "GET" else None,
                          headers={"api-key": api_key, "api-secret": api_secret})
    body = _json_or_text(resp)
    if body.get("code") != 0:
        raise DeployError(f"易盾 {path} 失败：{body.get('msg')}")
    return body


def yidun_sites(config: dict, domain: str = "") -> list[dict]:
    body = yidun_request(config, "GET", "/v1/sites", {"domain": domain} if domain else None)
    return body.get("data") or []


@_register("DeployToYidunCdn")
def deploy_to_yidun_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """易盾 DCDN：可以按证书 ID 直接更新，也可以按域名找到站点再更新。"""
    cert_id = config.get("certId")
    if cert_id:
        yidun_request(config, "PUT", f"/v1/certs/{cert_id}",
                      {"cert": ctx.crt, "key": ctx.key})
        log(f"易盾证书 {cert_id} 更新成功")
        return

    domains = _as_list(config.get("domains")) or [ctx.domain]
    for domain in domains:
        sites = yidun_sites(config, domain)
        site = next((row for row in sites if row.get("domain") == domain), None)
        if site is None:
            raise DeployError(f"易盾里找不到站点：{domain}")

        existed = (site.get("https_listen") or {}).get("cert")
        if existed:
            yidun_request(config, "PUT", f"/v1/certs/{existed}",
                          {"cert": ctx.crt, "key": ctx.key})
            log(f"易盾域名 {domain} 的证书 {existed} 更新成功")
            continue

        name = f"{domain}_{int(time.time() * 1000)}"
        yidun_request(config, "POST", "/v1/certs", {
            "name": name, "type": "custom", "cert": ctx.crt, "key": ctx.key,
        })
        created = yidun_request(config, "GET", "/v1/certs", {"name": name})
        rows = created.get("data") or []
        if not rows:
            raise DeployError(f"易盾证书创建后查不到：{name}")
        new_id = rows[0].get("id")
        yidun_request(config, "PUT", "/v1/sites",
                      {"id": site.get("id"), "https_listen": {"cert": new_id}})
        log(f"易盾域名 {domain} 已绑定新证书 {new_id}")


# ================================================================ 白山云
@_register("DeployToBaishanCdn")
def deploy_to_baishan_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """白山云：按证书 ID 更新证书内容。"""
    token = config.get("token") or ""
    if not token:
        raise DeployError("白山云授权缺少 token")
    cert_id = config.get("certId")
    if not cert_id:
        raise DeployError("白山云部署需要填写证书 ID（控制台证书列表里可以看到）")

    url = _base_url(config, "https://cdn.api.baishan.com") + "/v2/domain/certificate"
    try:
        resp = _cloud_request("POST", url, params={"token": token}, json={
            "cert_id": int(cert_id),
            "name": ctx.render(config.get("certName") or ctx.domain),
            "certificate": ctx.crt,
            "key": ctx.key,
        })
    except DeployError as exc:
        message = str(exc)
        if "already exists" in message.lower():
            # 证书内容没变时白山云直接报「已存在」，这不算失败
            log("白山云提示证书已存在，内容无需更新")
            return
        raise
    body = _json_or_text(resp)
    if body.get("code") != 0:
        message = body.get("message") or body.get("msg") or json.dumps(body, ensure_ascii=False)
        if "already exists" in str(message).lower():
            log("白山云提示证书已存在，内容无需更新")
            return
        raise DeployError(f"白山云更新证书失败：{message}")
    log(f"白山云证书 {cert_id} 更新成功")


# ================================================================ 多吉云
def doge_request(config: dict, path: str, data: dict | None = None,
                 ignore_err: bool = False) -> dict:
    """多吉云开放 API：body 用 form 编码，签名是 HMAC-SHA1(path + "\n" + body)。"""
    access_key = config.get("accessKey") or ""
    secret_key = config.get("secretKey") or ""
    if not access_key or not secret_key:
        raise DeployError("多吉云授权缺少 accessKey / secretKey")

    body = urllib.parse.urlencode(data or {}, doseq=True)
    sign = hmac.new(secret_key.encode(), f"{path}\n{body}".encode(), hashlib.sha1).hexdigest()
    resp = _cloud_request("POST", _base_url(config, "https://api.dogecloud.com") + path,
                          content=body,
                          headers={"Authorization": f"TOKEN {access_key}:{sign}",
                                   "Content-Type": "application/x-www-form-urlencoded"})
    data_json = _json_or_text(resp)
    if data_json.get("code") != 200:
        if ignore_err:
            return {"warn": data_json.get("msg") or "接口返回异常"}
        raise DeployError(f"多吉云 {path} 失败：{data_json.get('msg') or data_json.get('code')}")
    return data_json.get("data") or {}


def doge_domains(config: dict) -> list[dict]:
    return doge_request(config, "/cdn/domain/list.json", {}).get("domains") or []


def _doge_clean_expired(config: dict, log: Callable, now: float) -> None:
    """顺手清掉「已过期且没绑定域名」的旧证书，避免证书列表越积越多。"""
    certs = doge_request(config, "/cdn/cert/list.json", {}).get("certs") or []
    for item in certs:
        try:
            expired = int(item.get("expire") or 0) < int(now)
        except (TypeError, ValueError):
            expired = False
        if not expired or item.get("domainCount"):
            continue
        try:
            doge_request(config, "/cdn/cert/delete.json", {"id": item.get("id")})
            log(f"已清理过期证书 {item.get('id')}")
        except DeployError as exc:
            log(f"清理过期证书失败（可忽略）：{exc}")


@_register("DeployToDogeCdn")
def deploy_to_doge_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """多吉云 CDN：上传证书 → 逐个域名绑定 → 清理过期证书。"""
    domains = _as_list(config.get("domains")) or [ctx.domain]
    note = ctx.render(config.get("certName") or "certd-{domain}-{timestamp}")

    uploaded = doge_request(config, "/cdn/cert/upload.json", {
        "note": note, "cert": ctx.crt, "private": ctx.key,
    })
    cert_id = uploaded.get("id")
    if not cert_id:
        raise DeployError("多吉云上传证书成功但没有返回证书 ID")
    log(f"多吉云证书上传成功，ID={cert_id}")

    ignore_err = bool(config.get("ignoreDeployNullCode"))
    for domain in domains:
        result = doge_request(config, "/cdn/cert/bind.json",
                             {"id": cert_id, "domain": domain}, ignore_err=ignore_err)
        if result.get("warn"):
            log(f"绑定域名 {domain} 返回异常但已忽略：{result['warn']}")
            continue
        log(f"多吉云域名 {domain} 绑定证书 {cert_id} 成功")

    _doge_clean_expired(config, log, time.time())


# ================================================================ 我爱云
def woai_request(config: dict, path: str, data: dict, token: str = "") -> dict:
    base = _base_url(config, config.get("baseApi") or "https://console.edeg.ttzi.cn")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Token"] = token
    resp = _cloud_request("POST", base + path, json=data, headers=headers)
    body = _json_or_text(resp)
    if body.get("code") != 200:
        raise DeployError(f"我爱云 {path} 失败：{body.get('message') or body.get('code')}")
    return body


def woai_login(config: dict) -> str:
    username = config.get("username") or ""
    password = config.get("password") or ""
    if not username or not password:
        raise DeployError("我爱云授权缺少账号或密码")
    body = woai_request(config, "/account/login",
                        {"username": username, "password": password})
    token = (body.get("data") or {}).get("token") or ""
    if not token:
        raise DeployError("我爱云登录未返回 Token")
    return token


@_register("DeployToWoaiCdn")
def deploy_to_woai_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """我爱云 CDN：证书 ID 在控制台证书列表里，直接用新内容覆盖。"""
    cert_id = config.get("certId")
    if not cert_id:
        raise DeployError("我爱云部署需要填写证书 ID（控制台证书列表里可以看到）")

    token = woai_login(config)
    log("我爱云登录成功")
    woai_request(config, "/certificate/edit",
                 {"id": cert_id, "cert": ctx.crt, "key": ctx.key}, token=token)
    log(f"我爱云证书 {cert_id} 更新成功")


# ================================================================ 京东云
JD_SSL_HOST = "ssl.jdcloud-api.com"
JD_CDN_HOST = "cdn.jdcloud-api.com"
JD_REGION = "cn-north-1"


def _jd_escape_segment(value: str) -> str:
    """路径段编码：保留 -_.~ （与 AWS 的 uriEscapePath 一致）。"""
    return urllib.parse.quote(str(value), safe="-_.~")


def _jd_canonical_query(query: dict | None) -> str:
    if not query:
        return ""
    items = []
    for key in sorted(query):
        value = query[key]
        if value is None:
            continue
        items.append(f"{_jd_escape_segment(key)}={_jd_escape_segment(value)}")
    return "&".join(items)


def _jdcloud_friendly(message: str) -> str:
    """把京东云的 401 翻成用户能照着做的一句中文。

    踩过的坑：`[401] account xxx didn't open cdn service.（HTTP UNAUTHENTICATED）`
    看着像密钥错，其实是**这个账号根本没开通 CDN 服务**；
    照原样甩给用户只会让人去反复改 AK/SK。所以这里分两种情况给结论：
    「没开通 CDN」→ 去控制台开通，或改用只传证书中心的插件；
    其它 UNAUTHENTICATED → 才是 AK/SK 不对或没有 CDN 权限。
    """
    text = (message or "").strip()
    lower = text.lower()
    if "open cdn service" in lower:
        match = re.search(r"account\s+([A-Za-z0-9_.@-]+)\s+didn", text, re.IGNORECASE)
        who = f"「{match.group(1)}」" if match else ""
        return (
            f"京东云账号{who}还没有开通 CDN 服务，接口直接拒绝了这次调用"
            f"（原始返回：{text}）。两种解决方式："
            "① 登录京东云控制台 → 域名与网站 → CDN → 开通服务，开通后重跑流水线即可；"
            "② 不想开通 CDN，就把部署方式换成「上传到京东云证书中心」，"
            "证书进证书中心后再到控制台手动绑定（这条不需要 CDN）。"
        )
    if "unauthenticated" in lower:
        return (
            f"京东云鉴权失败（原始返回：{text}）。"
            "先确认授权里的 AccessKeyId / SecretAccessKey 没填错、没带多余空格；"
            "再去京东云访问控制（IAM）确认这个 AK 有 CDN 相关权限。"
        )
    return text


def _jd_error(resp: httpx.Response) -> str:
    try:
        data = resp.json() or {}
    except ValueError:
        return f"HTTP {resp.status_code} {resp.text[:200]}"
    error = data.get("error") or data.get("Error") or {}
    if isinstance(error, dict) and error:
        code = error.get("code") or ""
        message = error.get("message") or ""
        status = error.get("status")
        text = f"[{code}] {message}" if code else str(message)
        if status:
            text += f"（HTTP {status}）"
        return text.strip() or f"HTTP {resp.status_code}"
    return f"HTTP {resp.status_code} {resp.text[:200]}"


def jdcloud_request(config: dict, method: str, host: str, path: str,
                    service: str, query: dict | None = None,
                    body: dict | None = None) -> dict:
    """京东云 JDCLOUD2-HMAC-SHA256（结构同 AWS SigV4，只是密钥前缀与 scope 不同）。"""
    ak = config.get("accessKeyId") or ""
    sk = config.get("secretAccessKey") or ""
    if not ak or not sk:
        raise DeployError("京东云授权缺少 accessKeyId / secretAccessKey")

    region = config.get("region") or JD_REGION
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body else ""
    now = dt.datetime.now(dt.timezone.utc)
    jd_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_part = jd_date[:8]
    nonce = uuid.uuid4().hex

    # 签名里的 host 必须和真正请求的 Host 头一致，所以先算出完整 URL
    base = _base_url(config, "")
    url = f"{base}{path}" if base else f"https://{host}{path}"
    host_header = urllib.parse.urlparse(url).netloc

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "host": host_header,
        "x-jdcloud-date": jd_date,
        "x-jdcloud-nonce": nonce,
    }
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in sorted(headers))
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    canonical_request = "\n".join([
        method.upper(), path, _jd_canonical_query(query),
        canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date_part}/{region}/{service}/jdcloud2_request"
    string_to_sign = "\n".join([
        "JDCLOUD2-HMAC-SHA256", jd_date, scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _sign(("JDCLOUD2" + sk).encode(), date_part)
    signing_key = _sign(signing_key, region)
    signing_key = _sign(signing_key, service)
    signing_key = _sign(signing_key, "jdcloud2_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"JDCLOUD2-HMAC-SHA256 Credential={ak}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    resp = _cloud_request(method.upper(), url, params=query or None,
                          content=payload or None, headers=headers)
    if resp.status_code >= 400:
        raise DeployError(f"京东云 {service} 接口失败：{_jdcloud_friendly(_jd_error(resp))}")
    data = resp.json() if resp.content else {}
    if not isinstance(data, dict):
        raise DeployError(f"京东云返回格式异常：{resp.text[:200]}")
    if data.get("error"):
        raise DeployError(f"京东云 {service} 接口失败：{_jdcloud_friendly(_jd_error(resp))}")
    return data.get("result") or {}


def jdcloud_upload_cert(config: dict, cert_name: str, crt: str, key: str) -> int:
    result = jdcloud_request(config, "POST", JD_SSL_HOST, "/v1/sslCert:upload", "ssl",
                             body={"certName": cert_name, "certFile": crt,
                                   "keyFile": key, "aliasName": cert_name})
    cert_id = result.get("certId")
    if not cert_id:
        raise DeployError("京东云上传证书成功但没有返回 certId")
    return int(cert_id)


def jdcloud_cdn_domains(config: dict) -> list[dict]:
    result = jdcloud_request(config, "GET", JD_CDN_HOST, "/v1/domain", "cdn",
                             query={"pageNumber": 1, "pageSize": 50})
    return result.get("domains") or []


@_register("DeployToJDCloudCert")
def deploy_to_jdcloud_cert(ctx: CertContext, config: dict, log: Callable) -> None:
    """只把证书传到京东云「数字证书中心」，不依赖 CDN 服务。

    账号没开通 CDN 时（接口返回 [401] account xxx didn't open cdn service）
    这是唯一可用的落地方式：证书先进证书中心，控制台里手动绑定即可。
    """
    cert_name = ctx.render(config.get("certName") or "certd-{domain}-{timestamp}")
    cert_id = config.get("certId")
    if cert_id:
        log(f"京东云：复用已有证书 ID {cert_id}")
    else:
        log(f"京东云：上传证书到数字证书中心 {cert_name}")
        cert_id = jdcloud_upload_cert(config, cert_name, ctx.crt, ctx.key)
    log(f"京东云证书已就绪，certId={cert_id}（可在控制台证书中心查看并手动绑定）")


@_register("DeployToJDCloudCdn")
def deploy_to_jdcloud_cdn(ctx: CertContext, config: dict, log: Callable) -> None:
    """京东云 CDN：先传证书到 SSL 证书中心，再给加速域名设置 https。"""
    domains = _as_list(config.get("domains")) or [ctx.domain]
    cert_name = ctx.render(config.get("certName") or "certd-{domain}-{timestamp}")
    jump_type = config.get("jumpType") or "default"

    cert_id = config.get("certId")
    if cert_id:
        log(f"京东云：复用已有证书 ID {cert_id}")
    else:
        log(f"京东云：上传证书到数字证书中心 {cert_name}")
        cert_id = jdcloud_upload_cert(config, cert_name, ctx.crt, ctx.key)
        log(f"证书上传成功，certId={cert_id}")

    for domain in domains:
        try:
            jdcloud_request(config, "POST", JD_CDN_HOST,
                            f"/v1/domain/{_jd_escape_segment(domain)}/httpType", "cdn",
                            body={
                                "httpType": "https",
                                "jumpType": jump_type,
                                "certFrom": "ssl",
                                "sslCertId": cert_id,
                                "syncToSsl": False,
                                "certName": cert_name,
                            })
        except DeployError as exc:
            message = str(exc)
            # jdcloud_request 已经把「没开通 CDN」翻译成中文结论了，这里只补一句证书状态
            if "open cdn service" in message.lower() or "开通 CDN" in message:
                raise DeployError(f"{message}（证书已经上传成功，certId={cert_id}）") from exc
            raise
        log(f"京东云域名 {domain} 证书部署成功")


# ================================================================ 注册
from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
