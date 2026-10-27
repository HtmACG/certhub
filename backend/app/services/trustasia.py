"""TrustAsia（亚洲诚信）CertCloud OpenAPI v3 客户端。

只实现「申请 SSL 证书」这条主线，官方文档：https://docs.trustasia.com/certcloud/openapi/v3/

鉴权（guide/authentication）：
    每个请求带两个头 X-CC-Key-ID / X-CC-Auth-Key，明文传，不需要自己算 HMAC（HTTPS 加密）。
    正式环境 https://api.certcloud.cn/openapi/v3，测试环境 https://api-uat.certcloud.cn/openapi/v3。
    返回结构 {"code": "success", "data": {...}}；出错时 code 是错误码（unauthenticated_request 等），
    响应头 X-CC-Request-ID 是排障用的追踪 ID，出错时一并带回日志。

申请流程（guide/workflows + api/orders/create + api/dcv）：
    1. 本地生成密钥与 CSR（私钥不出本机）；
    2. POST /orders/{product_id} 下单，拿订单 ID + 域名验证值 dcv_val[]；
    3. 把每一条 dcv_val 写成 DNS TXT / CNAME（或 HTTP 文件）；
    4. 记录生效后 PUT /orders/{order_id}/dcv-completed 通知 CA 去验；
    5. 轮询 GET /orders/{order_id} 直到 status=issued；
    6. GET /certs/{cert_id} 取 pem + ica_pem，和本地私钥拼成完整证书链。

订单状态见 guide/statuses：auditing / submitting / domain_verifing / wait_verify / issuing /
issued / failed / rejected / overtime / canceled / expired …
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

from . import certutil, net

PROD_BASE = "https://api.certcloud.cn/openapi/v3"
UAT_BASE = "https://api-uat.certcloud.cn/openapi/v3"


class TrustAsiaError(RuntimeError):
    """业务错误：消息只有一行中文，进执行日志时不打堆栈。"""


# ---------------------------------------------------------------- 产品（guide/products）
#: product_id -> 能力描述。下单时 product_id 就是 /orders/:id 里的 :id。
#: 价格与额度以账号为准，这里只描述「能不能签泛域名 / 要不要组织审核 / 支持哪些验证方式」。
PRODUCTS: dict[str, dict] = {
    "trustasia_ssl_dv_v2": {
        "name": "TrustAsia 域名型 SSL（DV，单域名）",
        "domainType": "单域名", "needOrg": False,
        "dcv": ["dns", "dns-persist", "cname", "file", "email"],
    },
    "trustasia_ssl_dv_wildcard_v2": {
        "name": "TrustAsia 域名型通配符 SSL（DV，通配符）",
        "domainType": "通配符", "needOrg": False,
        "dcv": ["dns", "dns-persist", "cname", "email"],
    },
    "trustasia_ssl_dv_sans_v2": {
        "name": "TrustAsia 域名型多域名 SSL（DV，多域名 / 多域名通配符）",
        "domainType": "多域名", "needOrg": False,
        "dcv": ["dns", "dns-persist", "cname", "file", "email"],
    },
    "trustasia_ssl_ov_v2": {
        "name": "TrustAsia 企业型 SSL（OV，单域名）",
        "domainType": "单域名", "needOrg": True,
        "dcv": ["dns", "dns-persist", "cname", "file", "email"],
    },
    "trustasia_ssl_ov_wildcard_v2": {
        "name": "TrustAsia 企业型通配符 SSL（OV，通配符）",
        "domainType": "通配符", "needOrg": True,
        "dcv": ["dns", "dns-persist", "cname", "email"],
    },
    "trustasia_ssl_ov_sans_v2": {
        "name": "TrustAsia 企业型多域名 SSL（OV，多域名 / 多域名通配符）",
        "domainType": "多域名", "needOrg": True,
        "dcv": ["dns", "dns-persist", "cname", "file", "email"],
    },
    "trustasia_ssl_ev_v2": {
        "name": "TrustAsia 增强型 SSL（EV，单域名）",
        "domainType": "单域名", "needOrg": True,
        "dcv": ["dns", "dns-persist", "cname", "file", "email"],
    },
    "trustasia_ssl_ev_sans_v2": {
        "name": "TrustAsia 增强型多域名 SSL（EV，多域名）",
        "domainType": "多域名", "needOrg": True,
        "dcv": ["dns", "dns-persist", "cname", "file", "email"],
    },
}

#: 订单状态 -> 人话（guide/statuses）
STATUS_TEXT = {
    "auditing": "待审核",
    "submitting": "正在提交 CA",
    "domain_verifing": "待域名验证",
    "wait_verify": "待验证",
    "issuing": "签发中",
    "issued": "已签发",
    "failed": "订单失败",
    "rejected": "审核被拒",
    "overtime": "订单超时",
    "canceled": "已取消",
    "expired": "已过期",
    "need_renew": "待续费",
    "renewed": "已续费",
    "revoked": "已吊销",
    "revoking": "吊销中",
    "reissue": "待重颁发",
    "reissuing": "重颁发中",
}

#: 这些状态出现即判失败，不用再等
FAILED_STATUS = {"failed", "rejected", "overtime", "canceled", "expired"}

#: 常见错误码 -> 该干什么（比原文好懂）
ERROR_HINTS = {
    "unauthenticated_request": "Key ID / API Key 不对，或请求没带上鉴权头",
    "api_key_disabled": "这个 API Key 已被禁用，去 CertCloud 控制台启用或换一个",
    "api_key_overdue": "当前套餐不包含该权益，需要先在 CertCloud 购买对应产品",
    "ip_limit": "请求 IP 不在 API Key 白名单里，去控制台加上本机出口 IP",
    "permission_denied": "这个 API Key 没有该操作的权限",
    "request_too_fast": "请求太频繁，稍后重试",
    "invalid_domain": "域名格式不对，或该产品不支持这个域名（例如单域名产品传了泛域名）",
    "invalid_dcv_method": "该产品不支持所选的域名验证方式",
    "invalid_organization_info": "组织信息不完整或有误（OV / EV 必须填组织与联系人）",
    "duplicate_alternative_order_id": "同一次申请重复提交了（备用订单 ID 重复）",
    "order_not_found": "订单不存在，可能是订单 ID 填错了",
    "resource_not_found": "找不到对应的订单 / 证书",
}


def status_text(status: str) -> str:
    return STATUS_TEXT.get(str(status or "").strip(), str(status or "未知状态"))


# ---------------------------------------------------------------- 基础请求
def _base_url(config: dict) -> str:
    """接口地址：留空按环境选官方地址；填了就用填的（自建代理 / 联调用本地 mock）。"""
    custom = str(config.get("apiBase") or "").strip().rstrip("/")
    if custom:
        return custom
    if str(config.get("environment") or "prod").strip().lower() in ("uat", "test", "测试"):
        return UAT_BASE
    return PROD_BASE


def _headers(config: dict) -> dict:
    key_id = str(config.get("keyId") or "").strip()
    auth_key = str(config.get("authKey") or "").strip()
    if not key_id or not auth_key:
        raise TrustAsiaError("请填写 TrustAsia 的 Key ID 与 API Key（CertCloud 控制台 → OpenAPI）")
    return {
        "X-CC-Key-ID": key_id,
        "X-CC-Auth-Key": auth_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _error_text(resp) -> str:
    """把错误响应压成一行：HTTP 码 + 错误码 + 说明 + 追踪 ID。"""
    request_id = ""
    try:
        request_id = (resp.headers.get("X-CC-Request-ID") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    code, message = "", ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            code = str(body.get("code") or "").strip()
            message = str(body.get("message") or body.get("msg") or body.get("detail") or "").strip()
            if not message and body.get("errors"):
                message = json.dumps(body["errors"], ensure_ascii=False)[:200]
    except Exception:  # noqa: BLE001
        message = (resp.text or "").strip()[:200]
    parts = [f"TrustAsia 接口返回 HTTP {resp.status_code}"]
    if code and code != "success":
        parts.append(f"错误码 {code}")
    if message:
        parts.append(message)
    if request_id:
        parts.append(f"Request-ID {request_id}")
    return "，".join(parts)


def _request(config: dict, method: str, path: str, body: dict | None = None,
             params: dict | None = None, timeout: float = 40) -> dict:
    """发请求并返回 data；出错抛 TrustAsiaError（一行中文）。"""
    url = _base_url(config) + path
    # 先取鉴权头：缺密钥是配置问题，不该被下面的「连接失败」包起来
    headers = _headers(config)
    try:
        resp = net.request(method, url, headers=headers, json=body,
                           params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 网络层异常统一成一句中文
        raise TrustAsiaError(f"连接 TrustAsia 接口失败（{url}）：{exc}") from exc

    if resp.status_code >= 400:
        text = _error_text(resp)
        try:
            code = str((resp.json() or {}).get("code") or "")
        except Exception:  # noqa: BLE001
            code = ""
        hint = ERROR_HINTS.get(code, "")
        raise TrustAsiaError(text + ("。" + hint if hint else ""))

    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001 - /ping 返回纯文本
        return {"raw": (resp.text or "").strip()}
    if not isinstance(payload, dict):
        return {"raw": payload}
    code = str(payload.get("code") or "success")
    if code not in ("success", "ok", ""):
        hint = ERROR_HINTS.get(code, "")
        message = str(payload.get("message") or payload.get("msg") or "").strip()
        detail = ("：" + message) if message else ""
        raise TrustAsiaError(f"TrustAsia 返回错误 {code}{detail}" + ("。" + hint if hint else ""))
    data = payload.get("data")
    return data if isinstance(data, dict) else {"raw": data}


# ---------------------------------------------------------------- 连通性
def ping(config: dict) -> str:
    """GET /ping：官方建议用它验证密钥是否正确。"""
    data = _request(config, "GET", "/ping", timeout=20)
    raw = str(data.get("raw") or "")
    return raw or "连接成功"


def _account_summary(config: dict) -> str:
    """尽量多给一点信息：账号下已有多少张证书。取不到就只报连通。"""
    try:
        data = _request(config, "GET", "/certs", params={"page": 1, "page_size": 1})
    except TrustAsiaError:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("total", "count", "total_count", "totalCount"):
        if data.get(key) is not None:
            return f"账号下共 {data[key]} 张证书"
    return ""


def test_connection(config: dict) -> str:
    """授权里的「测试」按钮：先 ping，再尽量报一下证书数量。"""
    message = ping(config)
    summary = _account_summary(config)
    if summary:
        return f"{message}（{summary}）"
    return message


# ---------------------------------------------------------------- 组织信息（OV / EV）
def build_organization(config: dict) -> dict | None:
    """OV / EV 要的组织与联系人；DV 不传。只填了组织 ID 时直接复用已有组织。"""
    org_id = str(config.get("organizationId") or "").strip()
    name = str(config.get("organizationName") or "").strip()
    if org_id and not name:
        return {"id": org_id}
    if not name:
        return None
    org = {
        "name": name,
        "address_line1": str(config.get("organizationAddress") or "").strip(),
        "city": str(config.get("organizationCity") or "").strip(),
        "state": str(config.get("organizationState") or "").strip(),
        "zip_code": str(config.get("organizationZipCode") or "").strip(),
        "country": str(config.get("organizationCountry") or "").strip() or "CN",
        "telephone": str(config.get("organizationTelephone") or "").strip(),
        "contact": {
            "first_name": str(config.get("contactFirstName") or "").strip(),
            "last_name": str(config.get("contactLastName") or "").strip(),
            "telephone": str(config.get("contactTelephone") or "").strip(),
            "email": str(config.get("contactEmail") or "").strip(),
        },
    }
    if org_id:
        org["id"] = org_id
    uscc = str(config.get("organizationUscc") or "").strip()
    if uscc:
        org["uscc"] = uscc
    email = str(config.get("email") or "").strip()
    if email and not org["contact"]["email"]:
        org["contact"]["email"] = email
    job_title = str(config.get("contactJobTitle") or "").strip()
    if job_title:
        org["contact"]["job_title"] = job_title
    return org


def check_organization(config: dict, product_id: str) -> None:
    """OV / EV 必须把组织信息填全，缺什么当场说清楚（别等 CA 回个 invalid_organization_info）。"""
    product = PRODUCTS.get(product_id) or {}
    if not product.get("needOrg"):
        return
    org = build_organization(config)
    if not org:
        raise TrustAsiaError(
            "「" + str(product.get("name") or product_id) + "」需要组织审核：请填写组织名称、地址、"
            "城市、省份、邮编、国家、组织电话，以及联系人姓名 / 电话 / 邮箱")
    if len(org) == 1 and org.get("id"):
        return
    missing = []
    for key, title in (("name", "组织名称"), ("address_line1", "组织地址"), ("city", "城市"),
                       ("state", "省份 / 地区"), ("zip_code", "邮编"), ("country", "国家代码"),
                       ("telephone", "组织电话")):
        if not str(org.get(key) or "").strip():
            missing.append(title)
    contact = org.get("contact") or {}
    for key, title in (("first_name", "联系人名"), ("last_name", "联系人姓"),
                       ("telephone", "联系人电话"), ("email", "联系人邮箱")):
        if not str(contact.get(key) or "").strip():
            missing.append(title)
    if missing:
        raise TrustAsiaError("「" + str(product.get("name") or product_id)
                             + "」需要组织审核，还缺：" + "、".join(missing))


# ---------------------------------------------------------------- 订单
def _alt_order_id() -> str:
    return "certhub-" + os.urandom(8).hex()


def create_order(config: dict, *, product_id: str, domains: list[str], csr_pem: str,
                 dcv_method: str = "dns", validity_months: int = 3,
                 organization: dict | None = None, user_external_id: str = "",
                 alternative_order_id: str = "") -> dict:
    """POST /orders/{product_id} 下单，返回 {id, status, certId, dcvVal}。"""
    domains = [str(d).strip() for d in domains if str(d).strip()]
    payload: dict = {
        "certificate": {
            "common_name": domains[0],
            "dns_names": domains,
            "csr": csr_pem,
            "sign_hash": "SHA256",
        },
        "dcv_method": dcv_method or "dns",
        "alternative_order_id": alternative_order_id or _alt_order_id(),
    }
    if int(validity_months or 0) > 0:
        payload["validity_months"] = int(validity_months)
    if organization:
        payload["organization"] = organization
    if user_external_id:
        payload["user_external_id"] = user_external_id
    data = _request(config, "POST", "/orders/" + product_id, body=payload)
    order_id = str(data.get("id") or "").strip()
    if not order_id:
        raise TrustAsiaError("下单成功但没拿到订单 ID：" + json.dumps(data, ensure_ascii=False)[:200])
    certificate = data.get("certificate") or {}
    return {
        "id": order_id,
        "status": str(data.get("status") or ""),
        "certId": str(certificate.get("id") or ""),
        "dcvVal": data.get("dcv_val") or [],
    }


def get_order(config: dict, order_id: str) -> dict:
    """GET /orders/{id}：状态、域名验证值，签发后带 pem。"""
    data = _request(config, "GET", "/orders/" + str(order_id))
    certificate = data.get("certificate") or {}
    return {
        "id": str(data.get("id") or order_id),
        "status": str(data.get("status") or ""),
        "statusDesc": str(data.get("status_desc") or ""),
        "certId": str(certificate.get("id") or ""),
        "pem": str(certificate.get("pem") or ""),
        "dcvVal": data.get("dcv_val") or [],
        "dcvMethod": str(data.get("dcv_method") or ""),
    }


def dcv_completed(config: dict, order_id: str) -> dict:
    """PUT /orders/{id}/dcv-completed：告诉 CA「验证值已经放好了，去验吧」。"""
    return _request(config, "PUT", "/orders/" + str(order_id) + "/dcv-completed")


def get_cert(config: dict, cert_id: str) -> dict:
    """GET /certs/{id}：证书 PEM 与中间证书（官方字段可能在 data 或 data.Certificate 里）。"""
    data = _request(config, "GET", "/certs/" + str(cert_id))
    cert = data.get("Certificate") if isinstance(data.get("Certificate"), dict) else data
    return {
        "pem": str(cert.get("pem") or cert.get("cert") or ""),
        "icaPem": str(cert.get("ica_pem") or cert.get("icaPem") or ""),
        "notBefore": str(cert.get("not_before") or ""),
        "notAfter": str(cert.get("not_after") or ""),
    }


# ---------------------------------------------------------------- 申请（完整流程）
def apply_certificate(config: dict, *, domains: list[str], log: Callable[[str], None],
                      product_id: str = "trustasia_ssl_dv_v2", dcv_method: str = "dns",
                      key_type: str = "rsa2048", validity_months: int = 3,
                      poll_seconds: int = 10, timeout_seconds: int = 1800,
                      dcv_handler: Callable[[str, str, str], None] | None = None,
                      file_handler: Callable[[str, str], None] | None = None,
                      user_external_id: str = "") -> dict:
    """下单 → 写验证记录 → 通知验证 → 等签发 → 取证书，返回含本地私钥的结果。

    dcv_handler(记录类型, 记录名, 记录值)：TXT / CNAME 走这里；
    file_handler(文件路径, 文件内容)：HTTP 文件验证走这里。
    """
    domains = certutil.split_domains(domains)
    if not domains:
        raise TrustAsiaError("请填写证书域名")
    product = PRODUCTS.get(product_id)
    if not product:
        raise TrustAsiaError("未知的 TrustAsia 产品：" + str(product_id))
    if dcv_method not in (product.get("dcv") or []):
        raise TrustAsiaError("「" + product["name"] + "」不支持 " + str(dcv_method)
                             + " 验证，可选：" + "、".join(product["dcv"]))
    if any(str(d).startswith("*.") for d in domains) and product.get("domainType") == "单域名":
        raise TrustAsiaError("「" + product["name"] + "」是单域名产品，不能签泛域名，请换成通配符或多域名产品")
    if len(domains) > 1 and product.get("domainType") == "单域名":
        raise TrustAsiaError("「" + product["name"] + "」只能签一个域名，当前填了 "
                             + str(len(domains)) + " 个")
    check_organization(config, product_id)

    key = certutil.generate_key(key_type)
    csr_pem = certutil.csr_to_pem(certutil.build_csr(key, domains))
    key_pem = certutil.key_to_pem(key)
    log("已生成密钥与 CSR（" + key_type + "），主域名 " + domains[0])

    order = create_order(
        config, product_id=product_id, domains=domains, csr_pem=csr_pem,
        dcv_method=dcv_method, validity_months=validity_months,
        organization=build_organization(config) if product.get("needOrg") else None,
        user_external_id=user_external_id,
    )
    order_id = order["id"]
    log("已提交订单 " + order_id + "（" + product["name"] + "），当前状态："
        + status_text(order["status"]))

    deadline = time.time() + max(int(timeout_seconds or 0), 60)
    published = False
    last_status = ""
    cert_pem = ""
    cert_id = order.get("certId") or ""
    dcv_val = order.get("dcvVal") or []
    status = order["status"]

    while time.time() < deadline:
        if dcv_val and not published:
            published = True
            record_type = "CNAME" if dcv_method == "cname" else "TXT"
            for item in dcv_val:
                name = str(item.get("auth_path") or item.get("domain") or "").strip()
                value = str(item.get("auth_val") or "").strip()
                if not name or not value:
                    continue
                if dcv_method == "file":
                    if file_handler:
                        file_handler(name, value)
                    else:
                        log("请在网站根目录放验证文件 " + name + "，内容：" + value)
                    continue
                if dcv_method == "email":
                    log("邮件验证需要人工点确认邮件：" + name + " ← " + value)
                    continue
                if not dcv_handler:
                    log("请手动添加验证记录：" + name + " " + record_type + " " + value)
                    continue
                log("域名验证记录：" + name + " " + record_type + " " + value)
                dcv_handler(record_type, name, value)
            if dcv_handler and dcv_method in ("dns", "dns-persist", "cname"):
                # 记录刚写完，稍等一下再通知 CA，避免它立刻去查拿到空记录
                time.sleep(min(max(int(poll_seconds or 10), 2), 30))
                dcv_completed(config, order_id)
                log("已通知 TrustAsia 进行域名验证")

        order = get_order(config, order_id)
        status = order["status"]
        text = status_text(status)
        desc = order.get("statusDesc") or ""
        if text != last_status:
            log("当前状态：" + text + ("（" + desc + "）" if desc else ""))
            last_status = text
        if not published and order.get("dcvVal"):
            dcv_val = order["dcvVal"]
            continue
        if order.get("pem"):
            cert_pem = order["pem"]
        cert_id = order.get("certId") or cert_id
        if status == "issued":
            break
        if status in FAILED_STATUS:
            raise TrustAsiaError("TrustAsia 订单未签发：" + text + ("（" + desc + "）" if desc else ""))
        time.sleep(max(int(poll_seconds or 10), 2))
    else:
        raise TrustAsiaError("等待 TrustAsia 签发超时（" + str(timeout_seconds) + " 秒），最后状态："
                             + (last_status or "未知") + "。订单可能仍在 CA 审核中，可到 CertCloud 控制台查看订单 "
                             + order_id)

    ica_pem = ""
    if cert_id:
        try:
            detail = get_cert(config, cert_id)
            cert_pem = detail.get("pem") or cert_pem
            ica_pem = detail.get("icaPem") or ""
        except TrustAsiaError as exc:
            log("读取证书详情失败（改用订单里的证书内容）：" + str(exc))
    if not cert_pem.strip():
        raise TrustAsiaError("订单 " + order_id + " 已签发，但接口没返回证书内容："
                             "请到 CertCloud 控制台下载后导入证书库")
    chain = cert_pem.strip() + ("\n" + ica_pem.strip() if ica_pem.strip() else "")
    log("证书已签发（订单 " + order_id + "），已取回" + ("证书 + 中间证书" if ica_pem else "证书"))
    return {
        "orderId": order_id,
        "certId": cert_id,
        "certificate": chain,
        "privateKey": key_pem,
        "status": "issued",
    }
