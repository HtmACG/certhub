"""出网代理（HTTP 代理 + 反向代理域名）
=================================
分两层：

1. **系统设置 → 网络设置**：httpProxy / httpsProxy / noProxy。
   与 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` 环境变量同一套语义——
   填了代理就默认所有出网请求都走代理，命中 noProxy 排除清单的才直连。
   调用方显式传 `trust_env=False`（内网 / 回环地址）时同样跳过代理。
2. **反向代理域名映射**（ACME）：把 CA 端点域名换成反代域名，例如
   `dv.acme-v02.api.pki.goog` → `gg.px.certd.handfree.work`。
   只替换实际传输地址，JWS 里签名用的仍是 ACME 原始 URL（协议要求）。
   证书申请任务里填的反代域名优先于这里的默认值。

两者解决的是不同场景：代理要有本地/上游的 http 代理进程；反代是「别人把一个能
直连的域名反代到 CA」，没有代理进程的机器用反代就能签发。
"""
from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..db import SessionLocal
from ..defaults import merge_defaults
from ..models import Setting

#: 配置缓存有效期（秒）——流水线里 DNS/ACME 是循环调用，不能每次都查库
CACHE_TTL = 5.0
#: 代理连通性探测超时（秒）
PROBE_TIMEOUT = 8.0

#: 默认反代域名：Let's Encrypt 与 Google 各有一个可直接使用的公共反代
DEFAULT_REVERSE_PROXIES = {
    "acme-v02.api.letsencrypt.org": "le.px.certd.handfree.work",
    "dv.acme-v02.api.pki.goog": "gg.px.certd.handfree.work",
    "acme.zerossl.com": "",
    "api.buypass.com": "",
}

_cache_lock = threading.Lock()
_cache: tuple[float, dict] = (0.0, {})


class ProxyError(Exception):
    """代理配置有问题（地址非法等），文案直接给用户看。"""


# ---------------------------------------------------------------- 配置
def _read() -> dict:
    db = SessionLocal()
    try:
        row = db.get(Setting, "network")
        stored = {}
        if row and row.value:
            try:
                stored = json.loads(row.value)
            except Exception:  # noqa: BLE001
                stored = {}
        return merge_defaults("network", stored)
    finally:
        db.close()


def invalidate() -> None:
    """设置保存后调用，让下一次读取立刻拿到新值。"""
    global _cache
    with _cache_lock:
        _cache = (0.0, {})


def config() -> dict:
    global _cache
    now = time.time()
    with _cache_lock:
        ts, cached = _cache
        if cached and now - ts < CACHE_TTL:
            return cached
    data = _read()
    with _cache_lock:
        _cache = (now, data)
    return data


def http_proxy() -> str:
    return str(config().get("httpProxy") or "").strip()


def https_proxy() -> str:
    return str(config().get("httpsProxy") or "").strip()


def enabled() -> bool:
    return bool(http_proxy() or https_proxy())


# ---------------------------------------------------------------- 域名工具
def host_of(url_or_host: str) -> str:
    value = (url_or_host or "").strip()
    if "://" in value:
        return (urlsplit(value).hostname or "").lower()
    return value.split("/")[0].split(":")[0].lower()


def _norm_host(value: str) -> str:
    host = host_of(value)
    while host.startswith("*."):
        host = host[2:]
    return host.strip(".")


def _no_proxy_rules() -> list[str]:
    raw = str(config().get("noProxy") or "")
    items: list[str] = []
    for chunk in raw.replace(",", "\n").replace(" ", "\n").split("\n"):
        item = chunk.strip()
        if item:
            items.append(item)
    return items


def _rule_matches(rule: str, url: str) -> bool:
    """NO_PROXY 语义：localhost / .example.com / 192.168.* / host:port / *"""
    rule = rule.strip().lower()
    if not rule:
        return False
    if rule == "*":
        return True
    host = host_of(url)
    if not host:
        return False
    # host:port / ip:port 形式
    rule_host = rule
    rule_port = ""
    if rule.count(":") == 1 and "://" not in rule:
        rule_host, rule_port = rule.split(":", 1)
    if rule_port:
        try:
            port = urlsplit(url).port or (443 if url.startswith("https") else 80)
        except ValueError:
            port = 0
        if str(port) != rule_port:
            return False
    if rule_host.startswith("*."):
        rule_host = rule_host[2:]
    elif rule_host.startswith("."):
        rule_host = rule_host[1:]
    if "*" in rule_host:
        # 通配符（192.168.*）按前缀/后缀逐段比
        pattern = rule_host.replace(".", r"\.")
        pattern = pattern.replace("*", ".*")
        import re

        return re.fullmatch(pattern, host) is not None
    return host == rule_host or host.endswith("." + rule_host)


def bypass(url: str) -> bool:
    """命中 noProxy 排除清单 → 直连。"""
    for rule in _no_proxy_rules():
        if _rule_matches(rule, url):
            return True
    return False


def proxy_for(url: str) -> str | None:
    """这个地址要用的代理（null 表示直连）。"""
    if not url or bypass(url):
        return None
    scheme = urlsplit(url).scheme.lower() if "://" in url else "https"
    if scheme == "https":
        return https_proxy() or http_proxy() or None
    return http_proxy() or https_proxy() or None


def describe_proxy(url: str = "") -> str:
    """日志用的一句话，不含账号密码。"""
    proxy = proxy_for(url) if url else (https_proxy() or http_proxy())
    if not proxy:
        return "未启用（直连）"
    parts = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.hostname}{port}"


# ---------------------------------------------------------------- httpx 入口
def _direct_mounts(verify, existing: dict) -> dict:
    """noProxy 命中的域名要显式挂「直连」transport，否则会被默认代理吃掉。"""
    for rule in _no_proxy_rules():
        host = _norm_host(rule)
        if not host or "*" in host:
            continue
        existing[f"all://{host}"] = httpx.HTTPTransport(verify=verify)
        existing[f"all://*.{host}"] = httpx.HTTPTransport(verify=verify)
    return existing


def proxy_mounts(verify=True) -> dict | None:
    """给 httpx.Client 用的 mounts：按协议挂代理，noProxy 命中的挂直连。"""
    mounts: dict = {}
    http_p, https_p = http_proxy(), https_proxy()
    if http_p:
        mounts["http://"] = httpx.HTTPTransport(proxy=_with_scheme(http_p), verify=verify)
    if https_p or http_p:
        proxy = _with_scheme(https_p or http_p)
        mounts["https://"] = httpx.HTTPTransport(proxy=proxy, verify=verify)
    if not mounts:
        return None
    return _direct_mounts(verify, mounts)


def client(**kwargs) -> httpx.Client:
    """构造一个「按系统设置走代理、noProxy 直连」的 httpx.Client。

    trust_env 默认 False：代理只认「系统设置 → 网络代理」里填的值，
    不继承宿主机的 HTTP_PROXY / HTTPS_PROXY 环境变量。
    否则装了 Clash 这类本地代理的机器，连内网 / 回环地址也会被甩给代理，
    表现成「本地 mock 服务、宝塔面板、K8s API 一律 502」——
    排查时很难想到是环境变量在捣乱。
    """
    kwargs.setdefault("trust_env", False)
    mounts = proxy_mounts(kwargs.get("verify", True))
    if mounts and "mounts" not in kwargs:
        kwargs["mounts"] = mounts
    return httpx.Client(**kwargs)


def _with_scheme(proxy: str) -> str:
    proxy = proxy.strip()
    if not proxy:
        return proxy
    if "://" not in proxy:
        proxy = "http://" + proxy
    parts = urlsplit(proxy)
    if not parts.hostname:
        raise ProxyError(f"代理地址不合法：{proxy}")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def request(method: str, url: str, **kwargs) -> httpx.Response:
    # 代理只认系统设置：调用方传 trust_env=False 表示「这个地址完全不走代理」。
    # 注意这边连着 httpx 自己的 trust_env 一起关掉，避免宿主机环境变量里的代理
    # 偷偷接管请求（内网 / 回环地址尤其致命）。
    use_proxy = bool(kwargs.pop("trust_env", True))
    kwargs.setdefault("trust_env", False)
    proxy = None
    if use_proxy:
        try:
            proxy = proxy_for(url)
        except ProxyError:
            proxy = None
    if proxy and "proxy" not in kwargs:
        kwargs["proxy"] = _with_scheme(proxy)
    return httpx.request(method, url, **kwargs)


def get(url: str, **kwargs) -> httpx.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> httpx.Response:
    return request("POST", url, **kwargs)


def put(url: str, **kwargs) -> httpx.Response:
    return request("PUT", url, **kwargs)


def delete(url: str, **kwargs) -> httpx.Response:
    return request("DELETE", url, **kwargs)


# ---------------------------------------------------------------- 反向代理
def reverse_proxy_map() -> dict[str, str]:
    """CA 域名 → 反代域名。系统设置里的覆盖默认值，空字符串表示禁用该映射。"""
    merged = dict(DEFAULT_REVERSE_PROXIES)
    custom = config().get("reverseProxies") or {}
    if isinstance(custom, dict):
        for key, value in custom.items():
            host = _norm_host(key)
            if host:
                merged[host] = _norm_host(str(value or ""))
    return merged


def reverse_proxy_for(directory_url: str, override: str = "") -> str:
    """该 CA 用哪个反代域名：任务里填的优先，其次系统配置/内置默认。"""
    if override and str(override).strip():
        return _norm_host(str(override).strip())
    return reverse_proxy_map().get(host_of(directory_url), "")


def probe(url: str, proxy: str | None = None, timeout: float = PROBE_TIMEOUT) -> dict:
    """探测一个地址通不通，返回 {ok, status, ms, error}。"""
    started = time.time()
    try:
        # trust_env=False：连通性测试要如实反映「系统设置里配的代理」的效果，
        # 不能因为宿主机有 HTTP_PROXY 环境变量就把直连测成「可用」
        kw = {"timeout": timeout, "follow_redirects": True, "trust_env": False}
        if proxy:
            kw["proxy"] = _with_scheme(proxy)
        resp = httpx.request("GET", url, **kw)
        return {
            "ok": resp.status_code < 400,
            "status": resp.status_code,
            "ms": int((time.time() - started) * 1000),
            "error": "" if resp.status_code < 400 else f"HTTP {resp.status_code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": 0,
            "ms": int((time.time() - started) * 1000),
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
