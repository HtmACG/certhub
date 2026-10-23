"""阿里云数字证书管理服务（CAS，cas.aliyuncs.com）客户端。

只实现证书申请需要的部分：
- 申请：CreateCertificateForPackageRequest（ProductCode 决定规格，
  digicert-free-1-free = 3 个月个人测试证书（免费版），仅中国站）
- 轮询：DescribeCertificateState（Type：domain_verify / process / certificate / verify_fail…，
  DNS 验证时带 RecordType / RecordDomain / RecordValue，签发后带 Certificate / PrivateKey）
- 兜底：GetUserCertificateDetail（State 没返回证书内容时按 CertId 再取一次）

官方文档要点（已核对）：申请前账号里必须有对应规格的证书额度，
额度不足会直接返回业务错误（错误码里能看到 ProductCode）。
"""
from __future__ import annotations

import json
import time
from typing import Callable

from .aliyun import AliyunError, call

ENDPOINT = "https://cas.aliyuncs.com/"
VERSION = "2020-04-07"

TYPE_TEXT = {
    "domain_verify": "待域名验证", "process": "CA 审核中", "verify_fail": "审核失败",
    "certificate": "已签发", "payed": "待申请", "unknow": "状态未知",
}

# 常用规格：前两个是免费/测试证书
PRODUCT_CODES = {
    "digicert-free-1-free": "DigiCert 个人测试证书（免费，3 个月）",
    "symantec-free-1-free": "Symantec 个人测试证书 Pro（免费，12 个月）",
}


class AliyunCasError(RuntimeError):
    pass


def test_connection(config: dict) -> str:
    """连通性测试：能查到订单列表就说明 AK/SK 与 CAS 权限都正常。"""
    data = call(config, ENDPOINT, "ListUserCertificateOrder", VERSION,
                {"CurrentPage": 1, "ShowSize": 1})
    total = data.get("TotalCount") or 0
    return f"连接成功，账号下共有 {total} 条证书/订单记录"


def create_order(config: dict, domains: list[str], product_code: str,
                 validate_type: str = "DNS", email: str = "") -> int:
    body = {
        "ProductCode": product_code or "digicert-free-1-free",
        "Domain": ",".join(domains),
        "ValidateType": validate_type,
    }
    if email:
        body["Email"] = email
    data = call(config, ENDPOINT, "CreateCertificateForPackageRequest", VERSION, body)
    order_id = data.get("OrderId")
    if not order_id:
        raise AliyunCasError(f"未拿到订单 ID：{json.dumps(data, ensure_ascii=False)[:300]}")
    return int(order_id)


def describe_state(config: dict, order_id: int) -> dict:
    return call(config, ENDPOINT, "DescribeCertificateState", VERSION, {"OrderId": order_id})


def _fetch_issued(config: dict, state: dict) -> tuple[str, str]:
    """取签发后的证书与私钥：先看 State，取不到再按 CertId 查详情。"""
    cert = (state.get("Certificate") or "").strip()
    key = (state.get("PrivateKey") or "").strip()
    if cert and key:
        return cert, key

    cert_id = state.get("CertId")
    if not cert_id:
        raise AliyunCasError("证书已签发但接口未返回证书内容，也没有 CertId 可查")
    detail = call(config, ENDPOINT, "GetUserCertificateDetail", VERSION, {"CertId": cert_id})
    cert = (detail.get("Cert") or "").strip()
    key = (detail.get("Key") or "").strip()
    if not cert or not key:
        raise AliyunCasError("证书已签发，但阿里云未返回证书/私钥内容，"
                             "请到数字证书管理服务控制台下载后手动导入证书库")
    return cert, key


def apply_certificate(config: dict, domains: list[str], log: Callable,
                      product_code: str = "digicert-free-1-free", email: str = "",
                      poll_seconds: int = 10, timeout_seconds: int = 900,
                      dcv_handler: Callable[[str, str, str], None] | None = None) -> dict:
    """提交证书申请并等到签发，返回 {orderId, certificate, privateKey}。

    dcv_handler(记录类型, 主机记录, 记录值) —— 记录类型通常是 TXT，个别规格给 CNAME。
    """
    order_id = create_order(config, domains, product_code, "DNS", email)
    log(f"已提交证书申请，订单号 {order_id}（规格 {product_code}），等待域名验证 ...")

    deadline = time.time() + timeout_seconds
    dcv_done = False
    last = ""
    while time.time() < deadline:
        state = describe_state(config, order_id)
        state_type = (state.get("Type") or "").strip()
        text = TYPE_TEXT.get(state_type, state_type or "未知")
        if text != last:
            log(f"当前状态：{text}")
            last = text

        if state_type == "domain_verify" and dcv_handler and not dcv_done:
            record_type = (state.get("RecordType") or "TXT").upper()
            name = state.get("RecordDomain") or ""
            value = state.get("RecordValue") or ""
            if name and value:
                log(f"DNS 验证记录：{name} {record_type} {value}")
                dcv_handler(record_type, name, value)
                dcv_done = True
            else:
                log("暂未取到 DNS 验证记录，稍后重试（若持续为空请到控制台手动添加）")
        elif state_type == "verify_fail":
            raise AliyunCasError(
                f"阿里云审核失败：{state.get('Reason') or state.get('Message') or '请到控制台查看失败原因'}")

        if state_type == "certificate":
            cert, key = _fetch_issued(config, state)
            return {"orderId": order_id, "certificate": cert, "privateKey": key,
                    "certId": state.get("CertId")}

        time.sleep(poll_seconds)

    raise AliyunCasError(f"等待阿里云签发超时（{timeout_seconds} 秒），最后状态：{last or '未知'}")
