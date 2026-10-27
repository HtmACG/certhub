"""授权资源自动拉取
==================
只要有 Key / Token 的授权，就能把对端已有的资源拉回来：
DNS 域名、面板站点、CDN 加速域名、WAF 证书、K8s 命名空间……
表单里直接下拉选，用户不用再去控制台抄一遍。

每个解析器返回 (items, error)：

- items: [{"label": "...", "value": "...", "extra": "..."}]
- error: 拉取失败时给用户看的一句中文（不抛异常，别让表单整体挂掉）

解析器只读，不做任何写操作；调用都走 net.*，内网目标传 trust_env=False。
"""
from __future__ import annotations

import hashlib
import time
from typing import Callable

import httpx

from . import dns as dns_service
from . import net


class ResourceError(Exception):
    """资源拉取失败（文案直接给用户看）。"""


# ---------------------------------------------------------------- 通用工具
def _baota_token(api_key: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    token = hashlib.md5((ts + hashlib.md5(api_key.encode()).hexdigest()).encode()).hexdigest()
    return ts, token


def _one_panel_token(api_key: str) -> tuple[str, str]:
    ts = str(int(time.time()))
    return hashlib.md5((api_key + ts).encode()).hexdigest(), ts


def _get_json(method: str, url: str, **kwargs) -> dict:
    try:
        resp = net.request(method, url, timeout=30, trust_env=False, **kwargs)
    except httpx.HTTPError as exc:
        raise ResourceError(f"连接 {url} 失败：{exc.__class__.__name__}"
                            f"（{str(exc) or '无详细原因'}）") from exc
    if resp.status_code >= 400:
        raise ResourceError(f"HTTP {resp.status_code}：{resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ResourceError(f"返回内容不是 JSON：{resp.text[:200]}") from exc


def _items(values: list[str], prefix: str = "") -> list[dict]:
    return [{"label": value, "value": value, "extra": prefix} for value in values if value]


# ---------------------------------------------------------------- 宝塔
def _baota_site_items(rows: list) -> list[dict]:
    """宝塔站点行 → 下拉项。

    站点名不一定是域名（宝塔允许自定义名称，例如 wwwhtmacg.cn、10.10.12.50），
    所以把备注 ps 也放进 extra：自动匹配时一起参与比较，域名写在备注里也能命中。
    """
    items: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name:
            continue
        extra_parts: list[str] = []
        remark = row.get("ps")
        if isinstance(remark, str) and remark:
            extra_parts.append(remark)
        extra = (row.get("domain") or row.get("domains") or row.get("domain_list") or "")
        if isinstance(extra, (list, tuple)):
            extra_parts.extend(str(item) for item in extra if item)
        elif isinstance(extra, str) and extra and extra != "1":
            extra_parts.append(extra)
        items.append({"label": str(name), "value": str(name), "extra": ",".join(extra_parts)})
    return items


def baota_sites(config: dict) -> tuple[list[dict], str]:
    url = (config.get("url") or "").rstrip("/")
    if not url:
        raise ResourceError("宝塔授权缺少面板地址")
    ts, token = _baota_token(config.get("apiKey") or "")
    auth = {"request_time": ts, "request_token": token}
    errors: list[str] = []
    # 面板站点列表：/data?action=getData（POST 表单）
    # 注意参数必须齐全（order / sort / search / tojs），少了宝塔直接回
    # {"status": false, "msg": "指定参数无效!"}，看起来像接口密钥不对，其实只是缺参数。
    try:
        data = _get_json("POST", f"{url}/data?action=getData", data={
            **auth, "table": "sites", "limit": "9999", "p": "1", "type": "-1",
            "order": "", "sort": "", "search": "", "tojs": "on",
        })
        items = _baota_site_items(data.get("data") or [])
        if items:
            return items, ""
    except ResourceError as exc:
        errors.append(str(exc))

    # 老版本面板：/site?action=GetSiteList（同样要带齐参数）
    for method, kw in (("POST", {"data": auth}), ("GET", {"params": auth})):
        try:
            data = _get_json(method, f"{url}/site?action=GetSiteList", **kw)
            rows = data.get("data") or []
            if rows and isinstance(rows[0], str):
                items = _items([str(name) for name in rows if name])
            else:
                items = _baota_site_items(rows)
            if items:
                return items, ""
        except ResourceError as exc:
            errors.append(str(exc))
    return [], "；".join(errors) or "宝塔没有返回站点列表"


# ---------------------------------------------------------------- 1Panel
def one_panel_sites(config: dict) -> tuple[list[dict], str]:
    url = (config.get("url") or "").rstrip("/")
    if not url:
        raise ResourceError("1Panel 授权缺少面板地址")
    token, ts = _one_panel_token(config.get("apiKey") or "")
    headers = {"1Panel-Token": token, "1Panel-Timestamp": ts}
    errors: list[str] = []
    for path in ("/api/v2/websites/search", "/api/v1/websites/search"):
        try:
            data = _get_json("POST", f"{url}{path}", headers=headers,
                             json={"page": 1, "pageSize": 500})
        except ResourceError as exc:
            errors.append(str(exc))
            continue
        payload = data.get("data") or {}
        rows = payload.get("items") if isinstance(payload, dict) else payload
        items: list[dict] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            domain = row.get("primaryDomain") or row.get("domain") or ""
            alias = row.get("alias") or row.get("name") or ""
            if not domain and not alias:
                continue
            label = f"{alias}（{domain}）" if alias and domain else (domain or alias)
            items.append({"label": label, "value": row.get("id") or domain or alias,
                          "extra": domain})
        if items:
            return items, ""
    return [], "；".join(errors) or "1Panel 没有返回网站列表"


# ---------------------------------------------------------------- 雷池 WAF
def safeline_certs(config: dict) -> tuple[list[dict], str]:
    url = (config.get("baseUrl") or config.get("url") or "").rstrip("/")
    if not url:
        raise ResourceError("雷池授权缺少控制台地址")
    data = _get_json("GET", f"{url}/api/open/cert",
                     headers={"X-SLCE-API-TOKEN": config.get("apiToken") or ""},
                     verify=not config.get("insecure", True))
    nodes = ((data.get("data") or {}).get("nodes")) or []
    items = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        domains = node.get("domains") or []
        label = f"{node.get('id')} · {', '.join(domains)}" if domains else str(node.get("id"))
        items.append({"label": label, "value": str(node.get("id")),
                      "extra": ", ".join(domains)})
    return items, ""


# ---------------------------------------------------------------- K8s
def k8s_namespaces(config: dict) -> tuple[list[dict], str]:
    base = (config.get("apiServer") or config.get("apiUrl") or "").rstrip("/")
    if not base:
        raise ResourceError("K8s 授权缺少 API Server 地址")
    data = _get_json("GET", f"{base}/api/v1/namespaces",
                     params={"limit": 500},
                     verify=not config.get("insecure", True),
                     headers={"Authorization": f"Bearer {config.get('token') or ''}"})
    items = []
    for row in data.get("items") or []:
        if not isinstance(row, dict):
            continue
        name = (row.get("metadata") or {}).get("name") or ""
        if name:
            items.append({"label": name, "value": name})
    return items, ""


# ---------------------------------------------------------------- 云 CDN 域名
def aliyun_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy

    result = deploy._aliyun_rpc(config, "DescribeUserDomains",
                                {"PageSize": "100", "PageNumber": "1"},
                                "https://cdn.aliyuncs.com/", "2018-05-10")
    rows = ((result.get("Domains") or {}).get("PageData")) or []
    names = [row.get("DomainName") for row in rows if isinstance(row, dict)]
    return _items([name for name in names if name], "阿里云 CDN"), ""


def _pick_domain(row) -> str:
    """国内 CDN 各家返回的字段名不一样，统一挑一个出来。"""
    if not isinstance(row, dict):
        return row if isinstance(row, str) else ""
    for key in ("domain", "domainName", "domain_name", "DomainName", "name", "host"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def ctyun_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy_cn

    rows = deploy_cn.ctyun_domains(config, config.get("productCode") or "008")
    names = [_pick_domain(row) for row in rows]
    return _items([name for name in names if name], "天翼云域名"), ""


def kuocai_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy_cn

    rows = deploy_cn.kuocai_domains(config)
    names = [_pick_domain(row) for row in rows]
    return _items([name for name in names if name], "括彩云域名"), ""


def doge_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy_cn

    rows = deploy_cn.doge_domains(config)
    names = [_pick_domain(row) for row in rows]
    return _items([name for name in names if name], "多吉云域名"), ""


def jdcloud_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy_cn
    from .deploy import DeployError

    try:
        rows = deploy_cn.jdcloud_cdn_domains(config)
    except DeployError as exc:
        # 京东云的错误已经被翻译成中文结论（没开通 CDN / AK 无权），
        # 原样给用户看，别再套一层「DeployError：」前缀
        return [], str(exc)
    names = [_pick_domain(row) for row in rows]
    return _items([name for name in names if name], "京东云域名"), ""


def upyun_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy_more

    rows = deploy_more.upyun_domains(config)
    names = [_pick_domain(row) for row in rows]
    return _items([name for name in names if name], "又拍云域名"), ""


def baiducloud_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import baiducloud

    names = baiducloud.list_domains(config)
    return _items(names, "百度云 CDN"), ""


def tencent_cdn_domains(config: dict) -> tuple[list[dict], str]:
    from . import deploy

    result = deploy._tencent_request(config, "DescribeDomains",
                                     {"Offset": 0, "Limit": 100},
                                     "cdn.tencentcloudapi.com", "cdn", "2018-06-06")
    rows = result.get("Domains") or []
    names = [row.get("Domain") for row in rows if isinstance(row, dict)]
    return _items([name for name in names if name], "腾讯云 CDN"), ""


# ---------------------------------------------------------------- 调度
#: kind → {授权类型: 解析器}
_RESOLVERS: dict[str, dict[str, Callable[[dict], tuple[list[dict], str]]]] = {
    "sites": {
        "baota": baota_sites,
        "1panel": one_panel_sites,
    },
    "certs": {
        "safeline": safeline_certs,
    },
    "namespaces": {
        "k8s": k8s_namespaces,
    },
    "cdnDomains": {
        "aliyun": aliyun_cdn_domains,
        "tencentcloud": tencent_cdn_domains,
        "ctyun": ctyun_cdn_domains,
        "kuocaicdn": kuocai_cdn_domains,
        "dogecloud": doge_cdn_domains,
        "jdcloud": jdcloud_cdn_domains,
        "upyun": upyun_cdn_domains,
        "baiducloud": baiducloud_cdn_domains,
    },
}

#: 「domains」走 DNS 服务商的域名列表
DNS_KIND = "domains"


def supports(access_type: str, kind: str) -> bool:
    if kind == DNS_KIND:
        return access_type in dns_service.PROVIDERS
    return access_type in (_RESOLVERS.get(kind) or {})


def resolve(access_type: str, config: dict, kind: str) -> tuple[list[dict], str]:
    """拉取某类授权下的资源。返回 (items, error)，失败不抛异常。"""
    if kind == DNS_KIND:
        try:
            names = dns_service.list_domains(access_type, config)
        except Exception as exc:  # noqa: BLE001
            return [], f"{exc.__class__.__name__}：{str(exc)[:180]}"
        return _items(sorted({name for name in names or [] if name}), "DNS 域名"), ""

    resolver = (_RESOLVERS.get(kind) or {}).get(access_type)
    if not resolver:
        return [], f"{access_type} 暂不支持自动拉取「{kind}」，请手动填写"
    try:
        return resolver(config)
    except ResourceError as exc:
        return [], str(exc)
    except Exception as exc:  # noqa: BLE001
        return [], f"{exc.__class__.__name__}：{str(exc)[:180]}"


def kinds_for(access_type: str) -> list[str]:
    """这个授权能拉哪些资源（前端「资源」按钮按它列）。"""
    kinds = []
    if access_type in dns_service.PROVIDERS:
        kinds.append(DNS_KIND)
    for kind, table in _RESOLVERS.items():
        if access_type in table:
            kinds.append(kind)
    return kinds
