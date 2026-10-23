"""探测各家云 API 的端点/动作是否真实存在。

判断依据：用假密钥请求，如果返回「鉴权失败 / 资源不存在」，说明接口本身存在；
如果返回 404、InvalidAction、InvalidURL，说明我记错了接口。
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import urllib.parse

import httpx

c = httpx.Client(timeout=30)


def show(name, resp, keys=("Code", "Message", "code", "message", "error", "error_code")):
    body = resp.text[:220].replace("\n", " ")
    print(f"  [{name}] HTTP {resp.status_code} | {body}")


# ---------------------------------------------------------------- 阿里云 DCDN
def aliyun_dcdn():
    params = {
        "Action": "SetDcdnDomainSSLCertificate", "Format": "JSON", "Version": "2018-01-15",
        "AccessKeyId": "LTAIfakeProbe", "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0", "SignatureNonce": "probe1234",
        "Timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DomainName": "probe.example.com", "CertName": "probe",
        "CertType": "upload", "SSLProtocol": "on", "SSLPub": "x", "SSLPri": "y",
    }
    enc = lambda s: urllib.parse.quote(str(s), safe="~")
    canonical = "&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(params.items()))
    sts = "GET&%2F&" + enc(canonical)
    params["Signature"] = base64.b64encode(
        hmac.new(b"fakeSecret&", sts.encode(), hashlib.sha1).digest()).decode()
    show("阿里云DCDN", c.get("https://dcdn.aliyuncs.com/", params=params))


# ---------------------------------------------------------------- 华为云 CDN
def huawei_cdn():
    host = "cdn.myhuaweicloud.com"
    path = "/v1.0/cdn/domains/probe.example.com/certificate"
    body = json.dumps({"cert_name": "probe", "certificate": "x", "private_key": "y",
                       "certificate_type": 0})
    sdk_date = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    signed = "\n".join(["POST", path, "", f"content-type:application/json", f"host:{host}",
                        f"x-sdk-date:{sdk_date}", "", "content-type;host;x-sdk-date",
                        hashlib.sha256(body.encode()).hexdigest()])
    sts = "\n".join(["SDK-HMAC-SHA256", sdk_date, hashlib.sha256(signed.encode()).hexdigest()])
    sig = hmac.new(b"fakeSecret", sts.encode(), hashlib.sha256).hexdigest()
    auth = (f"SDK-HMAC-SHA256 Access=AKIAfakeProbe, SignedHeaders=content-type;host;x-sdk-date, "
            f"Signature={sig}")
    show("华为云CDN", c.post(f"https://{host}{path}", content=body, headers={
        "Content-Type": "application/json", "Host": host,
        "X-Sdk-Date": sdk_date, "Authorization": auth}))


# ---------------------------------------------------------------- 又拍云
def upyun():
    auth = base64.b64encode(b"operator:password").decode()
    show("又拍云", c.post("https://api.upyun.com/certificates",
                          json={"certificate": "x", "private_key": "y"},
                          headers={"Authorization": f"Basic {auth}"}))


# ---------------------------------------------------------------- Cloudflare
def cloudflare():
    show("Cloudflare", c.get(
        "https://api.cloudflare.com/client/v4/zones/fakezoneid/custom_hostnames",
        headers={"Authorization": "Bearer fakeToken"}))


# ---------------------------------------------------------------- 腾讯云 COS
def tencent_cos():
    host = "probe-1250000000.cos.ap-guangzhou.myqcloud.com"
    show("腾讯云COS", c.put(f"https://{host}/?cert", content="<x/>", headers={
        "Host": host, "Content-Type": "application/xml",
        "Authorization": "q-sign-algorithm=sha1&q-ak=AKIDfakeProbe&q-sign-time=1;2"
                         "&q-key-time=1;2&q-header-list=&q-url-param-list=&q-signature=deadbeef"}))


# ---------------------------------------------------------------- AWS ACM
def aws_acm():
    show("AWS ACM", c.post("https://acm.us-east-1.amazonaws.com/",
                           content="{}", headers={
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "CertificateManager.RequestCertificate",
        "Authorization": "AWS4-HMAC-SHA256 Credential=AKIAfake/20260101/us-east-1/acm/aws4_request, "
                         "SignedHeaders=host, Signature=deadbeef"}))


print("== 云 API 存在性探测 ==")
for fn in (aliyun_dcdn, huawei_cdn, upyun, cloudflare, tencent_cos, aws_acm):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        print(f"  [{fn.__name__}] 请求异常：{exc.__class__.__name__} {exc}")
