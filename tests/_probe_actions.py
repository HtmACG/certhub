"""探测云厂商 action 是否存在。

判断依据：用假密钥调用，返回鉴权错误说明 action 存在；
返回 InvalidAction / NotFound 说明接口名写错了。
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.parse

import httpx

c = httpx.Client(timeout=25)


def aliyun(endpoint, version, action, extra=None):
    params = {
        "Action": action, "Format": "JSON", "Version": version,
        "AccessKeyId": "LTAIfakeProbeKey", "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": hashlib.md5(os.urandom(8)).hexdigest(),
        "Timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    params.update(extra or {})
    enc = lambda s: urllib.parse.quote(str(s), safe="~")
    canonical = "&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(params.items()))
    sts = "GET&%2F&" + enc(canonical)
    params["Signature"] = base64.b64encode(
        hmac.new(b"fakeSecret&", sts.encode(), hashlib.sha1).digest()).decode()
    try:
        r = c.get(endpoint, params=params)
        body = r.text[:180].replace("\n", " ")
        code = ""
        try:
            code = r.json().get("Code", "")
        except Exception:
            pass
        ok = code not in ("InvalidAction", "InvalidAction.NotFound", "NotFound")
        print(f"  {'OK  ' if ok else 'BAD '} {action:42} {r.status_code} {code or body}")
    except Exception as e:
        print(f"  ERR  {action:42} {e.__class__.__name__}")


def tencent(host, service, version, action, body=None):
    payload = json.dumps(body or {}, separators=(",", ":"))
    ts = int(time.time())
    date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
    ct = "application/json; charset=utf-8"
    ch = f"content-type:{ct}\nhost:{host}\nx-tc-action:{action.lower()}\n"
    sh = "content-type;host;x-tc-action"
    cr = "\n".join(["POST", "/", "", ch, sh, hashlib.sha256(payload.encode()).hexdigest()])
    scope = f"{date}/{service}/tc3_request"
    sts = "\n".join(["TC3-HMAC-SHA256", str(ts), scope,
                     hashlib.sha256(cr.encode()).hexdigest()])
    k = hmac.new(b"TC3fakeSecret", date.encode(), hashlib.sha256).digest()
    k = hmac.new(k, service.encode(), hashlib.sha256).digest()
    k = hmac.new(k, b"tc3_request", hashlib.sha256).digest()
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"TC3-HMAC-SHA256 Credential=fakeId/{scope}, "
                         f"SignedHeaders={sh}, Signature={sig}",
        "Content-Type": ct, "Host": host, "X-TC-Action": action,
        "X-TC-Timestamp": str(ts), "X-TC-Version": version,
    }
    try:
        r = c.post(f"https://{host}", content=payload, headers=headers)
        d = r.json().get("Response", {})
        err = d.get("Error") or {}
        code = err.get("Code", "")
        ok = code not in ("InvalidAction", "InvalidAction.NotFound")
        print(f"  {'OK  ' if ok else 'BAD '} {action:42} {r.status_code} {code} {err.get('Message','')[:60]}")
    except Exception as e:
        print(f"  ERR  {action:42} {e.__class__.__name__}")


print("== 阿里云 ==")
for ep, ver, act in [
    ("https://dcdn.aliyuncs.com/", "2018-01-15", "SetDcdnDomainSSLCertificate"),
    ("https://live.aliyuncs.com/", "2016-11-01", "SetLiveDomainCertificate"),
    ("https://vod.aliyuncs.com/", "2017-03-21", "SetVodDomainCertificate"),
    ("https://slb.aliyuncs.com/", "2014-05-15", "UploadServerCertificate"),
    ("https://alb.aliyuncs.com/", "2020-06-16", "AssociateAdditionalCertificatesWithListener"),
    ("https://nlb.aliyuncs.com/", "2022-04-30", "AssociateAdditionalCertificatesWithListener"),
    ("https://esa.aliyuncs.com/", "2024-09-10", "SetCertificate"),
    ("https://waf.aliyuncs.com/", "2021-10-01", "ModifyDomainCert"),
    ("https://ga.aliyuncs.com/", "2019-11-20", "AssociateAdditionalCertificatesWithListener"),
    ("https://fc.aliyuncs.com/", "2023-03-30", "UpdateCustomDomain"),
    ("https://apigateway.aliyuncs.com/", "2016-07-14", "SetDomainCertificate"),
]:
    aliyun(ep, ver, act)

print("== 腾讯云 ==")
for host, svc, ver, act in [
    ("ssl.tencentcloudapi.com", "ssl", "2019-12-25", "UploadCertificate"),
    ("cdn.tencentcloudapi.com", "cdn", "2018-06-06", "UpdateDomainConfig"),
    ("teo.tencentcloudapi.com", "teo", "2022-09-01", "ModifyHostsCertificate"),
    ("live.tencentcloudapi.com", "live", "2018-08-01", "BindLiveDomainCert"),
    ("live.tencentcloudapi.com", "live", "2018-08-01", "ModifyLiveDomainCertBindings"),
    ("clb.tencentcloudapi.com", "clb", "2018-03-17", "ModifyCertificate"),
    ("clb.tencentcloudapi.com", "clb", "2018-03-17", "ModifyListener"),
]:
    tencent(host, svc, ver, act)
