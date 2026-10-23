"""
DNS 服务商适配层
================
统一接口：add_txt / remove_txt，用于完成 ACME dns-01 验证。
已支持：阿里云、腾讯云 DNSPod、Cloudflare、华为云、GoDaddy、NameSilo
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import random
import string
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Callable

import httpx

from . import net
from .certutil import acme_record_name, root_domain, txt_record_name


class DnsError(Exception):
    pass


def _rnd(n: int = 8) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def _resp_error(resp: httpx.Response) -> str:
    """把各家的错误响应压成一行人话。

    各家格式不一样：阿里云 Message+Code、腾讯云 Response.Error、
    Cloudflare errors[]、华为 message、NameSilo detail。直接甩原文，
    用户只能看到一坨 JSON 加一串 RequestId，看不出到底错在哪。
    """
    try:
        data = resp.json()
    except Exception:
        return f"HTTP {resp.status_code} {resp.text[:200]}"
    if isinstance(data, dict):
        err = data.get("Error") or (data.get("Response") or {}).get("Error") or data
        if isinstance(err, dict):
            msg = (err.get("Message") or err.get("message") or err.get("error")
                   or err.get("detail") or "")
            code = err.get("Code") or err.get("error_code") or ""
            if msg and code and str(code) not in str(msg):
                return f"{msg}（{code}）"
            if msg or code:
                return str(msg or code)
        errors = data.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            first = errors[0]
            return f"{first.get('message')}（code {first.get('code')}）"
    return f"HTTP {resp.status_code} {resp.text[:200]}"


class _DnsHttpClient(httpx.Client):
    """所有请求都经过这里，连接类异常统一翻成 DnsError。

    get/post 内部都会走到 request()，所以包一层就覆盖了全部服务商，
    用户不会再看到裸的 ConnectError / SSL 错误。
    """

    def request(self, method: str, url, **kwargs):
        try:
            return super().request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise DnsError(f"请求 {url} 失败：{exc.__class__.__name__}"
                           f"（{str(exc) or '无详细原因'}）") from exc


def main_domain_for(domain: str, roots: list[str] | None = None) -> str:
    """解析记录所属的主域名，子域名托管优先。

    免费二级域名（sub.example.com）在服务商那边是一个独立 zone，
    但 root_domain() 只会截到 example.com，记录就被写到上级域名里了。
    托管列表命中最长后缀时以它为准，否则退回通用规则。
    """
    name = (domain or "").lstrip("*.").strip(".").lower()
    candidates = sorted(
        {str(item).strip().lower().lstrip("*.").strip(".") for item in (roots or []) if str(item).strip()},
        key=len, reverse=True,
    )
    for root in candidates:
        if name == root or name.endswith("." + root):
            return root
    return root_domain(domain)


class BaseDnsProvider:
    #: TXT 记录前缀。ACME dns-01 用 _acme-challenge，
    #: 火山引擎等云厂商的域名验证用 _dnsauth，可在实例上覆盖。
    record_prefix = "_acme-challenge"

    def __init__(self, config: dict, log: Callable[[str], None] | None = None,
                 root_map: list[str] | None = None):
        self.config = config or {}
        self.log = log or (lambda msg: None)
        # 子域名托管列表：这些域名本身就是 zone，解析记录时不能再往上一级截
        self.root_map = [str(item).strip() for item in (root_map or []) if str(item).strip()]
        # 海外 DNS（Cloudflare 等）走代理，国内厂商直连
        self.http = _DnsHttpClient(timeout=30, follow_redirects=True,
                                   mounts=net.proxy_mounts())

    def resolve_root(self, domain: str) -> str:
        return main_domain_for(domain, self.root_map)

    def close(self):
        self.http.close()

    def add_txt(self, domain: str, value: str) -> None:  # pragma: no cover - 抽象
        raise NotImplementedError

    def remove_txt(self, domain: str, value: str) -> None:  # pragma: no cover
        raise NotImplementedError

    # ---- 通用工具 ----
    def record_name(self, domain: str) -> str:
        return txt_record_name(domain, self.record_prefix, root=self.resolve_root(domain))

    # ---- 通用记录管理（CNAME 记录管理用）----
    # 子类按厂商 API 实现；没实现的服务商给出中文结论，不让页面整体报 500。
    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        raise DnsError(f"{self.__class__.__name__} 暂不支持记录管理")

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        raise DnsError(f"{self.__class__.__name__} 暂不支持记录管理")

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        raise DnsError(f"{self.__class__.__name__} 暂不支持记录管理")

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        raise DnsError(f"{self.__class__.__name__} 暂不支持记录管理")

    @staticmethod
    def full_name(root: str, host: str) -> str:
        host = (host or "").strip().strip(".")
        if host in ("", "@"):
            return root
        return f"{host}.{root}"

    @staticmethod
    def relative_host(root: str, name: str) -> str:
        name = (name or "").strip().strip(".").lower()
        root = (root or "").strip().strip(".").lower()
        if name == root:
            return "@"
        if name.endswith("." + root):
            return name[: -(len(root) + 1)]
        return name

    #: 各家「同名同值的记录已存在」的错误关键字。
    #: 命中就当添加成功：说明要验证的那个值本来就在 DNS 里
    #: （同一个账号重复申请、或上一轮没清理干净时都会遇到）。
    #: 不认这个码的话，运行会直接以「记录已存在」失败，看起来像 DNS 授权坏了。
    DUPLICATE_HINTS = ("already exists", "domainrecordduplicate", "recordexist",
                       "record already exist", "duplicate record", "81057")

    def _tolerate_duplicate(self, action, **kwargs) -> None:
        """添加 TXT 记录，把「已存在」当成成功。"""
        try:
            self._request(action, **kwargs)
        except Exception as exc:  # noqa: BLE001
            text = str(exc).lower()
            if any(hint in text for hint in self.DUPLICATE_HINTS):
                self.log(f"TXT 记录已存在，跳过添加（{kwargs.get('Value', '')[:16]}…）")
                return
            raise

    def _check(self, resp: httpx.Response, action: str):
        if resp.status_code >= 400:
            raise DnsError(f"{action} 失败：{_resp_error(resp)}")
        return resp


# ---------------------------------------------------------------- 阿里云
class AliyunDns(BaseDnsProvider):
    ENDPOINT = "https://alidns.aliyuncs.com/"

    def _sign(self, params: dict) -> str:
        def enc(s):
            return urllib.parse.quote(str(s), safe="~")

        items = sorted(params.items())
        canonical = "&".join(f"{enc(k)}={enc(v)}" for k, v in items)
        string_to_sign = "GET&%2F&" + enc(canonical)
        key = (self.config.get("accessKeySecret", "") + "&").encode()
        digest = hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def _request(self, action: str, **kwargs) -> dict:
        params = {
            "Action": action,
            "Format": "JSON",
            "Version": "2015-01-09",
            "AccessKeyId": self.config.get("accessKeyId", ""),
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": _rnd(16),
            "Timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        params.update({k: v for k, v in kwargs.items() if v not in (None, "")})
        params["Signature"] = self._sign(params)
        resp = self.http.get(self.ENDPOINT, params=params)
        self._check(resp, f"阿里云 DNS {action}")
        return resp.json()

    def add_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        self._tolerate_duplicate("AddDomainRecord", DomainName=root,
                                 RR=self.record_name(domain), Type="TXT", Value=value, TTL=600)

    def remove_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        data = self._request("DescribeDomainRecords", DomainName=root,
                             RRKeyWord=self.record_name(domain), Type="TXT")
        for rec in data.get("DomainRecords", {}).get("Record", []):
            if rec.get("Value") == value:
                self._request("DeleteDomainRecord", RecordId=rec["RecordId"])

    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        data = self._request("DescribeDomainRecords", DomainName=root, Type=rtype, PageSize=500)
        rows = (data.get("DomainRecords") or {}).get("Record") or []
        return [{"id": row.get("RecordId"), "host": row.get("RR") or "@",
                 "type": row.get("Type") or rtype, "value": row.get("Value") or "",
                 "ttl": row.get("TTL"), "line": row.get("Line") or ""} for row in rows]

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        data = self._request("AddDomainRecord", DomainName=root, RR=host or "@",
                             Type=rtype, Value=value, TTL=ttl)
        return str(data.get("RecordId") or "")

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        rid = record_id or self._find_record_id(root, host, rtype)
        self._request("UpdateDomainRecord", RecordId=rid, RR=host or "@",
                      Type=rtype, Value=value, TTL=ttl)

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        rid = self._find_record_id(root, host, rtype, value)
        if rid:
            self._request("DeleteDomainRecord", RecordId=rid)

    def _find_record_id(self, root: str, host: str, rtype: str, value: str = "") -> str:
        for rec in self.list_records(root, rtype):
            if (rec.get("host") or "").lower() != (host or "@").lower():
                continue
            if value and (rec.get("value") or "").rstrip(".") != value.rstrip("."):
                continue
            return str(rec.get("id") or "")
        raise DnsError(f"阿里云 DNS 中未找到 {host or '@'}.{root} 的 {rtype} 记录")

    def list_domains(self) -> list[str]:
        data = self._request("DescribeDomains", PageSize=100)
        rows = (data.get("Domains") or {}).get("Domain") or []
        return [row.get("DomainName", "") for row in rows if row.get("DomainName")]


# ---------------------------------------------------------------- 腾讯云 DNSPod
class TencentDns(BaseDnsProvider):
    HOST = "dnspod.tencentcloudapi.com"
    SERVICE = "dnspod"
    VERSION = "2021-03-23"

    def _headers(self, action: str, payload: str) -> dict:
        ts = int(time.time())
        date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{self.HOST}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        canonical_request = "\n".join([
            "POST", "/", "",
            canonical_headers, signed_headers,
            hashlib.sha256(payload.encode()).hexdigest(),
        ])
        scope = f"{date}/{self.SERVICE}/tc3_request"
        string_to_sign = "\n".join([
            "TC3-HMAC-SHA256", str(ts), scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        secret = self.config.get("secretKey", "")
        k_date = hmac.new(("TC3" + secret).encode(), date.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_date, self.SERVICE.encode(), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        auth = (f"TC3-HMAC-SHA256 Credential={self.config.get('secretId','')}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}")
        return {"Authorization": auth, "Content-Type": ct, "Host": self.HOST,
                "X-TC-Action": action, "X-TC-Timestamp": str(ts), "X-TC-Version": self.VERSION}

    def _request(self, action: str, body: dict) -> dict:
        payload = json.dumps(body, separators=(",", ":"))
        resp = self.http.post(f"https://{self.HOST}", content=payload,
                              headers=self._headers(action, payload))
        self._check(resp, f"DNSPod {action}")
        data = resp.json().get("Response", {})
        if data.get("Error"):
            raise DnsError(f"DNSPod {action} 失败：{data['Error'].get('Message')}")
        return data

    def _domain_id(self, root: str) -> int:
        data = self._request("DescribeDomain", {"Domain": root})
        info = data.get("DomainInfo")
        if not info:
            raise DnsError(f"DNSPod 中未找到域名 {root}")
        return info["DomainId"]

    def add_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        self._tolerate_duplicate("CreateRecord", **{
            "Domain": root, "SubDomain": self.record_name(domain),
            "RecordType": "TXT", "RecordLine": "默认", "Value": value, "TTL": 600,
        })

    def remove_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        data = self._request("DescribeRecordList", {
            "Domain": root, "Subdomain": self.record_name(domain), "RecordType": "TXT",
        })
        for rec in data.get("RecordList", []):
            if rec.get("Value") == value:
                self._request("DeleteRecord", {"Domain": root, "RecordId": rec["RecordId"]})

    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        data = self._request("DescribeRecordList", {
            "Domain": root, "RecordType": rtype, "Limit": 3000,
        })
        rows = data.get("RecordList") or []
        return [{"id": row.get("RecordId"), "host": row.get("Name") or "@",
                 "type": row.get("Type") or rtype, "value": row.get("Value") or "",
                 "ttl": row.get("TTL"), "line": row.get("Line") or ""} for row in rows]

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        data = self._request("CreateRecord", {
            "Domain": root, "SubDomain": host or "@", "RecordType": rtype,
            "RecordLine": "默认", "Value": value, "TTL": ttl,
        })
        return str(data.get("RecordId") or "")

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        rid = record_id or self._find_record_id(root, host, rtype)
        self._request("ModifyRecord", {
            "Domain": root, "RecordId": int(rid), "SubDomain": host or "@",
            "RecordType": rtype, "RecordLine": "默认", "Value": value, "TTL": ttl,
        })

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        rid = self._find_record_id(root, host, rtype, value)
        if rid:
            self._request("DeleteRecord", {"Domain": root, "RecordId": int(rid)})

    def _find_record_id(self, root: str, host: str, rtype: str, value: str = "") -> str:
        for rec in self.list_records(root, rtype):
            if (rec.get("host") or "").lower() != (host or "@").lower():
                continue
            if value and (rec.get("value") or "").rstrip(".") != value.rstrip("."):
                continue
            return str(rec.get("id") or "")
        raise DnsError(f"DNSPod 中未找到 {host or '@'}.{root} 的 {rtype} 记录")

    def list_domains(self) -> list[str]:
        data = self._request("DescribeDomainList", {"Offset": 0, "Limit": 100})
        rows = data.get("DomainList") or []
        return [row.get("Name", "") for row in rows if row.get("Name")]


# ---------------------------------------------------------------- Cloudflare
class CloudflareDns(BaseDnsProvider):
    BASE = "https://api.cloudflare.com/client/v4"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.config.get('apiToken','')}",
                "Content-Type": "application/json"}

    def _zone_id(self, root: str) -> str:
        if self.config.get("zoneId"):
            return self.config["zoneId"]
        resp = self.http.get(f"{self.BASE}/zones", params={"name": root}, headers=self._headers())
        self._check(resp, "Cloudflare 查询 Zone")
        data = resp.json()
        if not data.get("result"):
            raise DnsError(f"Cloudflare 中未找到域名 {root}，请检查 API Token 权限")
        return data["result"][0]["id"]

    def _find(self, zone: str, name: str) -> list[dict]:
        resp = self.http.get(f"{self.BASE}/zones/{zone}/dns_records",
                             params={"type": "TXT", "name": name}, headers=self._headers())
        self._check(resp, "Cloudflare 查询记录")
        return resp.json().get("result", [])

    def add_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        zone = self._zone_id(root)
        name = f"{self.record_name(domain)}.{root}"
        resp = self.http.post(f"{self.BASE}/zones/{zone}/dns_records", headers=self._headers(),
                              json={"type": "TXT", "name": name, "content": value, "ttl": 120})
        try:
            self._check(resp, "Cloudflare 添加记录")
        except DnsError as exc:
            if any(hint in str(exc).lower() for hint in self.DUPLICATE_HINTS):
                self.log("TXT 记录已存在，跳过添加")
                return
            raise

    def remove_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        zone = self._zone_id(root)
        name = f"{self.record_name(domain)}.{root}"
        for rec in self._find(zone, name):
            if rec.get("content", "").strip('"') == value:
                self.http.delete(f"{self.BASE}/zones/{zone}/dns_records/{rec['id']}",
                                 headers=self._headers())

    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        zone = self._zone_id(root)
        resp = self.http.get(f"{self.BASE}/zones/{zone}/dns_records",
                             params={"type": rtype, "per_page": 100}, headers=self._headers())
        self._check(resp, "Cloudflare 查询记录")
        rows = resp.json().get("result", [])
        return [{"id": row.get("id"), "host": self.relative_host(root, row.get("name") or ""),
                 "type": row.get("type") or rtype, "value": row.get("content") or "",
                 "ttl": row.get("ttl"), "line": ""} for row in rows]

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        zone = self._zone_id(root)
        resp = self.http.post(f"{self.BASE}/zones/{zone}/dns_records", headers=self._headers(),
                              json={"type": rtype, "name": self.full_name(root, host),
                                    "content": value, "ttl": ttl})
        self._check(resp, "Cloudflare 添加记录")
        return str((resp.json().get("result") or {}).get("id") or "")

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        zone = self._zone_id(root)
        rid = record_id or self._find_record_id(root, host, rtype)
        resp = self.http.patch(f"{self.BASE}/zones/{zone}/dns_records/{rid}",
                               headers=self._headers(), json={"content": value, "ttl": ttl})
        self._check(resp, "Cloudflare 修改记录")

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        zone = self._zone_id(root)
        rid = self._find_record_id(root, host, rtype, value)
        if rid:
            resp = self.http.delete(f"{self.BASE}/zones/{zone}/dns_records/{rid}",
                                    headers=self._headers())
            self._check(resp, "Cloudflare 删除记录")

    def _find_record_id(self, root: str, host: str, rtype: str, value: str = "") -> str:
        for rec in self.list_records(root, rtype):
            if (rec.get("host") or "").lower() != (host or "@").lower():
                continue
            if value and (rec.get("value") or "").rstrip(".") != value.rstrip("."):
                continue
            return str(rec.get("id") or "")
        raise DnsError(f"Cloudflare 中未找到 {host or '@'}.{root} 的 {rtype} 记录")

    def list_domains(self) -> list[str]:
        resp = self.http.get(f"{self.BASE}/zones", params={"per_page": 100},
                             headers=self._headers())
        self._check(resp, "Cloudflare 查询域名")
        return [row.get("name", "") for row in resp.json().get("result", []) if row.get("name")]


# ---------------------------------------------------------------- 华为云
class HuaweiDns(BaseDnsProvider):
    HOST = "dns.myhuaweicloud.com"

    def _request(self, method: str, uri: str, query: dict | None = None, body: dict | None = None):
        query = query or {}
        payload = json.dumps(body) if body is not None else ""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='~')}={urllib.parse.quote(str(v), safe='~')}"
            for k, v in sorted(query.items())
        )
        headers = {"content-type": "application/json", "host": self.HOST, "x-sdk-date": now}
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        canonical_request = "\n".join([
            method, uri, canonical_query, canonical_headers, signed_headers,
            hashlib.sha256(payload.encode()).hexdigest(),
        ])
        string_to_sign = "\n".join([
            "SDK-HMAC-SHA256", now,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        signature = hmac.new(self.config.get("secretAccessKey", "").encode(),
                             string_to_sign.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = (
            f"SDK-HMAC-SHA256 Access={self.config.get('accessKeyId','')}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        url = f"https://{self.HOST}{uri}"
        resp = self.http.request(method, url, params=query, content=payload or None,
                                 headers=headers)
        self._check(resp, f"华为云 DNS {method} {uri}")
        return resp.json() if resp.text else {}

    def _zone_id(self, root: str) -> str:
        data = self._request("GET", "/v2/zones", {"name": root + "."})
        zones = data.get("zones") or []
        if not zones:
            raise DnsError(f"华为云 DNS 中未找到域名 {root}")
        return zones[0]["id"]

    def add_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        zone = self._zone_id(root)
        name = f"{self.record_name(domain)}.{root}."
        self._request("POST", f"/v2/zones/{zone}/recordsets", body={
            "name": name, "type": "TXT", "ttl": 300, "records": [f'"{value}"'],
        })

    def remove_txt(self, domain: str, value: str) -> None:
        root = self.resolve_root(domain)
        zone = self._zone_id(root)
        name = f"{self.record_name(domain)}.{root}."
        data = self._request("GET", f"/v2/zones/{zone}/recordsets",
                             {"name": name, "type": "TXT"})
        for rec in data.get("recordsets", []):
            if any(value in r for r in rec.get("records", [])):
                self._request("DELETE", f"/v2/zones/{zone}/recordsets/{rec['id']}")

    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        zone = self._zone_id(root)
        data = self._request("GET", f"/v2/zones/{zone}/recordsets",
                             {"type": rtype, "limit": 500})
        rows = data.get("recordsets") or []
        return [{"id": row.get("id"), "host": self.relative_host(root, row.get("name") or ""),
                 "type": row.get("type") or rtype,
                 "value": ",".join(row.get("records") or []).rstrip("."),
                 "ttl": row.get("ttl"), "line": ""} for row in rows]

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        zone = self._zone_id(root)
        data = self._request("POST", f"/v2/zones/{zone}/recordsets", body={
            "name": f"{self.full_name(root, host)}.", "type": rtype,
            "ttl": ttl, "records": [f"{value.rstrip('.')}."],
        })
        return str(data.get("id") or "")

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        zone = self._zone_id(root)
        rid = record_id or self._find_record_id(root, host, rtype)
        self._request("PUT", f"/v2/zones/{zone}/recordsets/{rid}",
                      body={"ttl": ttl, "records": [f"{value.rstrip('.')}."]})

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        zone = self._zone_id(root)
        rid = self._find_record_id(root, host, rtype, value)
        if rid:
            self._request("DELETE", f"/v2/zones/{zone}/recordsets/{rid}")

    def _find_record_id(self, root: str, host: str, rtype: str, value: str = "") -> str:
        for rec in self.list_records(root, rtype):
            if (rec.get("host") or "").lower() != (host or "@").lower():
                continue
            if value and (rec.get("value") or "").rstrip(".") != value.rstrip("."):
                continue
            return str(rec.get("id") or "")
        raise DnsError(f"华为云 DNS 中未找到 {host or '@'}.{root} 的 {rtype} 记录")

    def list_domains(self) -> list[str]:
        data = self._request("GET", "/v2/zones", {"limit": 100})
        return [(row.get("name") or "").rstrip(".") for row in data.get("zones") or []
                if row.get("name")]


# ---------------------------------------------------------------- GoDaddy
class GodaddyDns(BaseDnsProvider):
    BASE = "https://api.godaddy.com/v1"

    def _headers(self) -> dict:
        return {"Authorization": f"sso-key {self.config.get('apiKey','')}:{self.config.get('apiSecret','')}",
                "Content-Type": "application/json"}

    def _path(self, domain: str) -> tuple[str, str]:
        root = self.resolve_root(domain)
        name = self.record_name(domain)
        if name == "_acme-challenge":
            return root, "_acme-challenge"
        return root, name

    def add_txt(self, domain: str, value: str) -> None:
        root, name = self._path(domain)
        resp = self.http.put(f"{self.BASE}/domains/{root}/records/TXT/{name}",
                             headers=self._headers(),
                             json=[{"data": value, "ttl": 600}])
        self._check(resp, "GoDaddy 添加记录")

    def remove_txt(self, domain: str, value: str) -> None:
        root, name = self._path(domain)
        self.http.delete(f"{self.BASE}/domains/{root}/records/TXT/{name}",
                         headers=self._headers())

    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        resp = self.http.get(f"{self.BASE}/domains/{root}/records/{rtype}",
                             headers=self._headers())
        self._check(resp, f"GoDaddy 查询 {rtype} 记录")
        rows = resp.json() or []
        return [{"id": f"{root}|{row.get('name') or '@'}", "host": row.get("name") or "@",
                 "type": rtype, "value": row.get("data") or "",
                 "ttl": row.get("ttl"), "line": ""} for row in rows]

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        host = host or "@"
        resp = self.http.put(f"{self.BASE}/domains/{root}/records/{rtype}/{host}",
                             headers=self._headers(),
                             json=[{"data": value, "ttl": ttl}])
        self._check(resp, f"GoDaddy 添加 {rtype} 记录")
        return f"{root}|{host}"

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        self.add_record(root, host, rtype, value, ttl)

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        host = host or "@"
        resp = self.http.delete(f"{self.BASE}/domains/{root}/records/{rtype}/{host}",
                                headers=self._headers())
        self._check(resp, f"GoDaddy 删除 {rtype} 记录")

    def list_domains(self) -> list[str]:
        resp = self.http.get(f"{self.BASE}/domains", params={"limit": 100},
                             headers=self._headers())
        self._check(resp, "GoDaddy 查询域名")
        return [row.get("domain", "") for row in (resp.json() or []) if row.get("domain")]


# ---------------------------------------------------------------- NameSilo
class NamesiloDns(BaseDnsProvider):
    BASE = "https://www.namesilo.com/api"

    def _call(self, action: str, **params) -> ET.Element:
        params.update({"version": "1", "type": "xml",
                       "key": self.config.get("apiKey", "")})
        resp = self.http.get(f"{self.BASE}/{action}", params=params)
        self._check(resp, f"NameSilo {action}")
        root = ET.fromstring(resp.text)
        detail = root.findtext(".//detail")
        if root.findtext(".//code") != "300":
            raise DnsError(f"NameSilo {action} 失败：{detail}")
        return root

    def _host(self, domain: str) -> str:
        name = self.record_name(domain)
        return name if name == "_acme-challenge" else name.replace("_acme-challenge.", "")

    def add_txt(self, domain: str, value: str) -> None:
        try:
            self._call("dnsAddRecord", domain=self.resolve_root(domain), rrtype="TXT",
                       rrhost=self._host(domain), rrvalue=value, rrttl="3600")
        except Exception as exc:  # noqa: BLE001
            if any(hint in str(exc).lower() for hint in self.DUPLICATE_HINTS):
                self.log("TXT 记录已存在，跳过添加")
                return
            raise

    def remove_txt(self, domain: str, value: str) -> None:
        root = self._call("dnsListRecords", domain=self.resolve_root(domain))
        for rec in root.iter("record"):
            if rec.findtext("type") == "TXT" and rec.findtext("value", "") == value:
                self._call("dnsDeleteRecord", domain=self.resolve_root(domain),
                           rrid=rec.findtext("record_id"))

    def list_records(self, root: str, rtype: str = "CNAME") -> list[dict]:
        data = self._call("dnsListRecords", domain=root)
        records = []
        for rec in data.iter("record"):
            if (rec.findtext("type") or "").upper() != rtype.upper():
                continue
            records.append({
                "id": rec.findtext("record_id") or "",
                "host": rec.findtext("host") or "@",
                "type": rec.findtext("type") or rtype,
                "value": rec.findtext("value") or "",
                "ttl": rec.findtext("ttl"),
                "line": "",
            })
        return records

    def add_record(self, root: str, host: str, rtype: str, value: str, ttl: int = 600) -> str:
        data = self._call("dnsAddRecord", domain=root, rrtype=rtype,
                          rrhost=("" if (host or "@") == "@" else host),
                          rrvalue=value, rrttl=str(ttl))
        return data.findtext(".//record_id") or ""

    def update_record(self, root: str, host: str, rtype: str, value: str,
                      record_id: str | int | None = None, ttl: int = 600) -> None:
        rid = record_id or self._find_record_id(root, host, rtype)
        self._call("dnsUpdateRecord", domain=root, rrid=str(rid),
                   rrhost=("" if (host or "@") == "@" else host),
                   rrvalue=value, rrttl=str(ttl))

    def delete_record(self, root: str, host: str, rtype: str, value: str = "") -> None:
        rid = self._find_record_id(root, host, rtype, value)
        if rid:
            self._call("dnsDeleteRecord", domain=root, rrid=str(rid))

    def _find_record_id(self, root: str, host: str, rtype: str, value: str = "") -> str:
        for rec in self.list_records(root, rtype):
            if (rec.get("host") or "").lower() != (host or "@").lower():
                continue
            if value and (rec.get("value") or "").rstrip(".") != value.rstrip("."):
                continue
            return str(rec.get("id") or "")
        raise DnsError(f"NameSilo 中未找到 {host or '@'}.{root} 的 {rtype} 记录")

    def list_domains(self) -> list[str]:
        root = self._call("listDomains")
        return [(node.text or "") for node in root.iter("domain") if node.text]


PROVIDERS = {
    "aliyun": AliyunDns,
    "tencentcloud": TencentDns,
    "cloudflare": CloudflareDns,
    "huawei": HuaweiDns,
    "godaddy": GodaddyDns,
    "namesilo": NamesiloDns,
}


def list_domains(access_type: str, config: dict, log=None) -> list[str]:
    """列出某个 DNS 授权下的主域名。

    用途：申请证书时选中 DNS 授权后，把该账号里的域名直接带出来，
    省得用户凭记忆手敲（敲错一个字母就是一次签发失败）。
    """
    provider = create_dns_provider(access_type, config, log)
    try:
        domains = provider.list_domains()
    except AttributeError as exc:
        raise DnsError(f"{access_type} 暂不支持域名嗅探") from exc
    finally:
        try:
            provider.close()
        except Exception:  # noqa: BLE001
            pass
    return sorted({d.strip() for d in domains if d and d.strip()})


def create_dns_provider(access_type: str, config: dict, log=None,
                        root_map: list[str] | None = None) -> BaseDnsProvider:
    cls = PROVIDERS.get(access_type)
    if not cls:
        raise DnsError(f"不支持的 DNS 服务商：{access_type}")
    return cls(config, log, root_map=root_map)


# ---------------------------------------------------------------- 通用记录管理
def _with_provider(access_type: str, config: dict, action, log=None,
                   root_map: list[str] | None = None):
    """开一个 provider、执行、保证关闭。"""
    provider = create_dns_provider(access_type, config, log, root_map=root_map)
    try:
        return action(provider)
    finally:
        try:
            provider.close()
        except Exception:  # noqa: BLE001
            pass


def list_records(access_type: str, config: dict, root: str, rtype: str = "CNAME",
                 log=None) -> list[dict]:
    return _with_provider(access_type, config,
                          lambda p: p.list_records(root, rtype), log)


def add_record(access_type: str, config: dict, root: str, host: str, rtype: str,
               value: str, ttl: int = 600, log=None) -> str:
    return _with_provider(access_type, config,
                          lambda p: p.add_record(root, host, rtype, value, ttl), log)


def update_record(access_type: str, config: dict, root: str, host: str, rtype: str,
                  value: str, ttl: int = 600, log=None) -> None:
    _with_provider(access_type, config,
                   lambda p: p.update_record(root, host, rtype, value, ttl=ttl), log)


def delete_record(access_type: str, config: dict, root: str, host: str, rtype: str,
                  value: str = "", log=None) -> None:
    _with_provider(access_type, config,
                   lambda p: p.delete_record(root, host, rtype, value), log)


def check_cname(domain: str, expected: str) -> tuple[bool, str, str]:
    """校验 CNAME 是否指向 expected（支持多级 CNAME 链）。

    返回 (是否通过, 实际指向, 错误说明)。查询失败只给一句中文，
    由调用方决定是展示还是入库。
    """
    import dns.resolver

    expected = (expected or "").strip().rstrip(".").lower()
    current = (domain or "").strip().rstrip(".").lower()
    actual = ""
    seen: set[str] = set()
    for _ in range(6):
        if current in seen:
            break
        seen.add(current)
        try:
            answers = dns.resolver.resolve(current, "CNAME", lifetime=6)
        except dns.resolver.NoAnswer:
            break
        except dns.resolver.NXDOMAIN:
            return False, actual, f"域名 {current} 不存在（记录尚未生效或填错）"
        except dns.resolver.NoNameservers:
            return False, actual, f"查询 {current} 的权威 DNS 无响应，请稍后重试"
        except Exception as exc:  # noqa: BLE001
            return False, actual, f"查询 {current} 失败：{exc.__class__.__name__}"
        if not answers:
            break
        actual = str(answers[0].target).rstrip(".").lower()
        if actual == expected:
            return True, actual, ""
        current = actual

    if not actual:
        return False, "", f"{domain} 还没有 CNAME 记录"
    return False, actual, f"当前指向 {actual}，与记录值 {expected} 不一致"


def check_subdomain(domain: str, access_type: str = "",
                    config: dict | None = None) -> tuple[bool, list[str], str]:
    """校验子域名托管是否真的生效。

    两件事都要成立：公网 DNS 上有 NS 委派记录，且该 zone 能在所选 DNS 授权里读到。
    只查 NS 会把「委派了但没在服务商建 zone」判成成功，申请证书时照样写不进记录。
    返回 (是否通过, 委派 NS 列表, 错误说明)。
    """
    import dns.resolver

    name = (domain or "").strip().strip(".").lower()
    if not name:
        return False, [], "请填写子域名"

    ns_list: list[str] = []
    try:
        answers = dns.resolver.resolve(name, "NS", lifetime=8)
        ns_list = sorted({str(record.target).rstrip(".").lower() for record in answers})
    except dns.resolver.NoAnswer:
        return False, [], f"{name} 还没有 NS 委派记录，请先在上级域名添加 NS 解析"
    except dns.resolver.NXDOMAIN:
        return False, [], f"域名 {name} 不存在（记录尚未生效或填错）"
    except dns.resolver.NoNameservers:
        return False, [], f"查询 {name} 的权威 DNS 无响应，请稍后重试"
    except Exception as exc:  # noqa: BLE001
        return False, [], f"查询 {name} 的 NS 失败：{exc.__class__.__name__}"

    if not ns_list:
        return False, [], f"{name} 还没有 NS 委派记录，请先在上级域名添加 NS 解析"

    if access_type and config is not None:
        try:
            provider = create_dns_provider(access_type, config)
            try:
                provider.list_records(name, "NS")
            finally:
                provider.close()
        except DnsError as exc:
            return False, ns_list, f"NS 已委派，但 DNS 授权里读不到该 zone：{exc}"
        except Exception as exc:  # noqa: BLE001
            return False, ns_list, f"NS 已委派，校验 DNS 授权失败：{exc}"
    return True, ns_list, ""


def _authoritative_servers(name: str, root: str | None = None) -> list[str]:
    """查权威 NS 的 IP，用来绕过递归解析器的缓存。"""
    import dns.resolver

    zone = root or root_domain(name)
    ips: list[str] = []
    for record in dns.resolver.resolve(zone, "NS", lifetime=8):
        host = str(record.target).rstrip(".")
        try:
            for addr in dns.resolver.resolve(host, "A", lifetime=8):
                ips.append(addr.address)
        except Exception:  # noqa: BLE001 - 部分 NS 只有 AAAA
            continue
    return ips


def _txt_has(name: str, value: str, nameservers: list[str] | None = None) -> bool:
    import dns.resolver

    if nameservers:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = nameservers
    else:
        resolver = dns.resolver.Resolver()
    answers = resolver.resolve(name, "TXT", lifetime=8)
    return any(value in str(r) for r in answers)


def wait_dns_propagation(domain: str, value: str, log=None, timeout: int = 120,
                         roots: list[str] | None = None) -> bool:
    """等 TXT 记录在权威 DNS 上生效（失败不阻塞流程，仅提示）。

    为什么优先问权威 NS：递归解析器会按 TTL 缓存（阿里云 DNS 免费版最短 600 秒），
    上一轮清理掉的旧值会在缓存里躺着，用系统 resolver 判断会一直「没生效」，
    而 CA 那边其实拨到的是权威服务器。两个都查一次，命中任意一个就算生效。
    """
    log = log or (lambda m: None)
    try:
        import dns.resolver  # noqa: F401

        root = main_domain_for(domain, roots)
        name = f"{acme_record_name(domain, root)}.{root}"
        authoritative: list[str] = []
        try:
            authoritative = _authoritative_servers(name, root)
        except Exception:  # noqa: BLE001 - 拿不到权威 NS 就退回系统解析器
            authoritative = []

        deadline = time.time() + timeout
        while time.time() < deadline:
            if authoritative and _txt_has(name, value, authoritative):
                log(f"DNS 记录已生效（权威 DNS）：{name}")
                return True
            try:
                if _txt_has(name, value):
                    log(f"DNS 记录已生效：{name}")
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
        log(f"DNS 记录校验超时（可忽略，CA 侧仍会验证）：{name}")
        return False
    except Exception as exc:  # pragma: no cover
        log(f"跳过 DNS 记录校验：{exc}")
        return False
