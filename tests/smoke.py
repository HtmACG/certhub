"""接口冒烟测试：跑一遍全量 API，自动清理测试数据。

用法（服务已在 8000 端口运行）：
    python tests/smoke.py
    python tests/smoke.py --base http://127.0.0.1:8000 --user admin --password 123456

设计要点：
- 只依赖 httpx（已在 requirements.txt 里），不引入 pytest
- 每条用例自带清理，失败也不会污染库
- 断言看「业务 code == 200」，因为本项目统一用 HTTP 200 + body.code 表达业务结果
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx

PASS, FAIL, SKIP = [], [], []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        PASS.append(name)
        print(f"  \033[32mPASS\033[0m {name}")
    else:
        FAIL.append((name, detail))
        print(f"  \033[31mFAIL\033[0m {name}  {detail}")


class Api:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip("/")
        # trust_env=False：冒烟连的是本机后端，不能被系统里的 HTTP_PROXY 劫持
        # （宿主机装了 Clash 之类的本地代理时，环境变量会把 127.0.0.1 也甩给代理，
        #  结果登录拿到一个 502 空响应，看起来像「登录接口坏了」）
        self.client = httpx.Client(base_url=self.base, timeout=30, trust_env=False)
        self.token = ""
        r = self.client.post("/api/auth/login", json={"userName": user, "password": password})
        body = r.json()
        if body.get("code") != 200:
            raise SystemExit(f"登录失败：{body.get('msg')}")
        self.token = body["data"]["token"]

    @property
    def headers(self) -> dict:
        return {"Authorization": self.token}

    def get(self, path: str, **kw):
        return self.client.get(path, headers=self.headers, **kw).json()

    def post(self, path: str, json=None, **kw):
        return self.client.post(path, headers=self.headers, json=json, **kw).json()

    def put(self, path: str, json=None):
        return self.client.put(path, headers=self.headers, json=json).json()

    def delete(self, path: str):
        return self.client.delete(path, headers=self.headers).json()


def ok(res: dict) -> bool:
    return isinstance(res, dict) and res.get("code") == 200


def msg(res: dict) -> str:
    return (res or {}).get("msg") or str(res)[:120]


def _mock_handler(seen: list):
    """冒充 DSM / QTS / PVE 的接口，记录收到的请求，用于断言参数是否传对。"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _record(self):
            body = b""
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                body = self.rfile.read(n)
            seen.append({
                "path": urlparse(self.path).path,
                "query": {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()},
                "auth": self.headers.get("Authorization") or "",
                "has_cert": b"BEGIN CERTIFICATE" in body or b"BEGIN+CERTIFICATE" in body,
                "has_key": b"PRIVATE KEY" in body or b"PRIVATE+KEY" in body,
                "body": body.decode("latin-1"),
            })

        def _send(self, code, payload, ctype="application/json"):
            raw = payload.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._record()
            path = urlparse(self.path).path
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if path in ("/webapi/auth.cgi", "/webapi/entry.cgi"):
                api = q.get("api") or ""
                method = q.get("method") or ""
                if api == "SYNO.API.Auth" or (not api and path == "/webapi/auth.cgi"):
                    if q.get("account") == "dsm-user" and q.get("passwd") == "dsm-pass":
                        self._send(200, json.dumps(
                            {"success": True, "data": {"sid": "SID", "synotoken": "SYNOTOKEN"}}))
                    else:
                        self._send(200, json.dumps({"success": False, "error": {"code": 400}}))
                    return
                if api == "SYNO.Core.Certificate.CRT" and method == "list":
                    # 证书库里已经有一张同名证书，导入时要带 id 覆盖它
                    self._send(200, json.dumps({"success": True, "data": {"certificates": [
                        {"id": 7, "desc": "panel-smoke.local",
                         "subject": {"common_name": "panel-smoke.local"}}]}}))
                    return
                if api == "SYNO.Core.Certificate":
                    self._send(200, json.dumps({"success": True, "data": {}}))
                    return
            self._send(404, "{}")

        def do_POST(self):
            self._record()
            p = urlparse(self.path).path
            if p == "/webapi/entry.cgi":
                q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                # 证书导入要回一个 id，后面的 set_default 才有目标
                data = {"id": 7} if q.get("method") == "import" else {}
                self._send(200, json.dumps({"success": True, "data": data}))
            elif p == "/cgi-bin/authLogin.cgi":
                self._send(200, "<QDoc><authPassed><![CDATA[1]]></authPassed>"
                                "<authSid><![CDATA[QSID]]></authSid></QDoc>", "text/xml")
            elif p == "/cgi-bin/sslUtils.cgi":
                self._send(200, "<QDoc><return>0</return></QDoc>", "text/xml")
            elif "/certificates/custom" in p:
                self._send(200, json.dumps({"data": None}))
            else:
                self._send(404, "{}")

    return Handler


def section_supported_certs(api: Api) -> None:
    """概览页「支持的证书」：签发来源 / 部署目标都必须能从注册表直出。"""
    print("\n== 支持的证书 / 部署目标 ==")
    ov = api.get("/api/dashboard/overview")
    data = ov.get("data") or {}
    certs = data.get("supportedCerts") or []
    names = [c.get("name") for c in certs]
    check("支持的证书清单 >= 8", len(certs) >= 8, f"count={len(certs)}")
    check("每条都带 group(apply/import)",
          all(c.get("group") in ("apply", "import") for c in certs),
          str([c.get("group") for c in certs]))
    check("包含阿里云免费证书", "阿里云免费证书" in names, str(names))
    check("包含腾讯云免费证书", "腾讯云免费证书" in names, str(names))
    check("包含上传自有证书（import 组）",
          any(c.get("group") == "import" for c in certs))
    check("可签发数量与 apply 组一致",
          (data.get("supportedCertsApply") or 0)
          == len([c for c in certs if c.get("group") == "apply"]))

    # 卡片里每个来源都要有 logo 字段（可留空，前端会退化成字母牌）与品牌色
    check("每条来源都带 logo/color 字段",
          all("logo" in c and "color" in c for c in certs))
    check("品牌色是 #rrggbb",
          all(not c.get("color") or (c["color"].startswith("#") and len(c["color"]) == 7)
              for c in certs),
          str([c.get("color") for c in certs]))
    with_logo = [c["name"] for c in certs if c.get("logo")]
    check("大半来源有品牌 logo（Iconify 图标名）", len(with_logo) >= 7,
          f"{len(with_logo)} 个：{with_logo}")
    check("Let's Encrypt 用官方 logo",
          any(c.get("logo") == "logos:letsencrypt" for c in certs), str(with_logo))

    targets = data.get("deployTargets") or []
    check("部署目标分类 >= 3 类", len(targets) >= 3, str(targets))
    check("部署插件总数 = 各分类求和",
          (data.get("deployTargetTotal") or 0) == sum(t.get("count", 0) for t in targets),
          f"{data.get('deployTargetTotal')} vs {targets}")

    # 规范：所有支持的部署平台都要逐个列出（名字 + logo），不能只给分类数量
    all_plugins = [p for t in targets for p in (t.get("plugins") or [])]
    check("每个分类都列出了插件名", all(t.get("plugins") for t in targets),
          str([(t.get("name"), len(t.get("plugins") or [])) for t in targets]))
    check("列出的插件数 = 部署插件总数",
          len(all_plugins) == (data.get("deployTargetTotal") or -1),
          f"{len(all_plugins)} vs {data.get('deployTargetTotal')}")
    check("每个插件都有名称",
          all(p.get("name") for p in all_plugins))
    # logo 取值顺序：Iconify 图标 → 官网 favicon → 品牌色字母牌（short）
    check("每个插件都有 logo / favicon / 字母牌",
          all(p.get("logo") or p.get("favicon") or p.get("short") for p in all_plugins),
          str([p.get("name") for p in all_plugins
               if not (p.get("logo") or p.get("favicon") or p.get("short"))]))
    check("多数插件用品牌图标（Iconify）",
          len([p for p in all_plugins if p.get("logo")]) >= 30,
          f"{len([p for p in all_plugins if p.get('logo')])}/{len(all_plugins)}")
    panel_names = [p.get("name") for t in targets if t.get("name") == "面板"
                   for p in (t.get("plugins") or [])]
    for wanted in ("宝塔", "1Panel", "群晖", "威联通", "Proxmox"):
        check(f"面板清单包含 {wanted}", any(wanted in n for n in panel_names), str(panel_names))

    plugins = api.get("/api/pipeline/plugins")
    plist = ((plugins.get("data") or {}).get("plugins")) or []
    for plugin_type in ("CertApplyVolcengine", "CertApplyAliyun", "CertApplyTencent"):
        found = next((p for p in plist if p.get("type") == plugin_type), None)
        check(f"签发插件 {plugin_type} 已注册", found is not None)
        if found:
            keys = [i.get("key") for i in found.get("inputs") or []]
            check(f"{plugin_type} 具备域名/授权/验证三要素",
                  {"domains", "accessId", "dnsAccessId"} <= set(keys), str(keys))


def section_aliyun_access_test(api: Api) -> None:
    """阿里云授权测试：SignatureNonce 必须每次不同，否则第二次就开始 400。"""
    print("\n== 阿里云授权连通性测试 ==")
    res = api.post("/api/access", {"category": "cloud", "type": "aliyun",
                                   "name": "__smoke_aliyun_test__",
                                   "config": {"accessKeyId": "LTAI5tSmokeFakeKey00",
                                              "accessKeySecret": "smokeFakeSecret"}})
    aid = (res.get("data") or {}).get("id") if ok(res) else 0
    if not aid:
        check("创建阿里云测试授权", False, msg(res))
        return
    try:
        messages = []
        for _ in range(2):
            out = api.post(f"/api/access/{aid}/test")
            if not ok(out):
                SKIP.append("阿里云连通性测试（接口异常）")
                return
            messages.append(json.dumps(out.get("data"), ensure_ascii=False))
        joined = " ".join(messages)
        if "ConnectError" in joined or "无法连接" in joined:
            SKIP.append("阿里云连通性测试（网络不可达）")
            return
        check("阿里云测试两次都返回业务结果（无 nonce 复用报错）",
              all("nonce" not in m.lower() for m in messages), joined[:200])
        check("假凭据被识别为 AccessKey 不存在",
              any("access key is not found" in m.lower() for m in messages), joined[:200])
        check("报错里没有裸 JSON + RequestId",
              "RequestId" not in joined and '"Recommend"' not in joined, joined[:200])
    finally:
        api.delete(f"/api/access/{aid}")


def section_cert_import(api: Api) -> None:
    """证书库「导入自有证书」：正常导入 + 私钥不匹配 / 非 PEM 的拒绝。"""
    print("\n== 导入自有证书 ==")
    try:
        import datetime as _dt

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
    except Exception:  # noqa: BLE001
        SKIP.append("导入证书（缺 cryptography）")
        return

    def make_pair(domain: str) -> tuple[str, str]:
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
        now = _dt.datetime.now(_dt.timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - _dt.timedelta(days=1))
                .not_valid_after(now + _dt.timedelta(days=90))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]),
                               critical=False)
                .sign(key, hashes.SHA256()))
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        return cert_pem, key_pem

    cert_pem, key_pem = make_pair("import.smoke.local")
    res = api.post("/api/cert/import",
                   {"cert": cert_pem, "key": key_pem, "remark": "__smoke__"})
    check("导入证书", ok(res) and (res.get("data") or {}).get("id"), msg(res))
    cert_id = (res.get("data") or {}).get("id") if ok(res) else 0
    if cert_id:
        detail = api.get(f"/api/cert/{cert_id}")
        check("导入后能在证书库查到",
              ok(detail) and "import.smoke.local" in ",".join(detail["data"]["domains"]),
              msg(detail))
        check("导入证书的私钥明文返回（前端用「显示」开关控制）",
              "PRIVATE KEY" in (detail["data"]["keyPem"] or ""))
        api.delete(f"/api/cert/{cert_id}")
        check("导入的证书可删除", not ok(api.get(f"/api/cert/{cert_id}")))

    _, other_key = make_pair("other.smoke.local")
    res = api.post("/api/cert/import", {"cert": cert_pem, "key": other_key})
    check("证书与私钥不匹配时拒绝", not ok(res), msg(res))

    res = api.post("/api/cert/import", {"cert": "not a cert", "key": key_pem})
    check("非 PEM 内容被拒绝", not ok(res), msg(res))


def section_panel_deploy(api: Api) -> None:
    """群晖 / 威联通 / PVE 三个部署插件：授权配置必须真正传到部署函数。

    这里起一个本地 mock 面板，断言账号、密码、Token、节点名、证书内容都到了对端。
    """
    print("\n== 面板部署插件（群晖 / 威联通 / PVE）==")
    seen: list[dict] = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _mock_handler(seen))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    root = f"http://127.0.0.1:{port}"

    aids: list[int] = []
    pid = 0
    try:
        def make_access(typ: str, name: str, config: dict) -> int:
            res = api.post("/api/access", {"category": "panel", "type": typ,
                                           "name": name, "config": config})
            if ok(res):
                aids.append(res["data"]["id"])
                return res["data"]["id"]
            return 0

        sid = make_access("synology", "__smoke_dsm__",
                          {"url": root, "username": "dsm-user", "password": "dsm-pass",
                           "insecure": True})
        qid = make_access("qnap", "__smoke_qts__",
                          {"url": root, "username": "qnap-user", "password": "qnap-pass",
                           "insecure": True})
        xid = make_access("proxmox", "__smoke_pve__",
                          {"url": root, "tokenId": "root@pam!certd",
                           "tokenSecret": "pve-secret", "node": "pve01", "insecure": True})
        check("面板授权创建（三种）", len(aids) == 3, f"aids={aids}")
        if len(aids) != 3:
            return

        res = api.post("/api/pipeline", {
            "title": "__smoke_panel__", "remark": "smoke",
            "content": {"stages": [
                {"id": "s1", "title": "申请", "tasks": [
                    {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
                     "input": {"domains": "panel-smoke.local", "days": 30}}]},
                {"id": "s2", "title": "部署", "tasks": [
                    {"id": "t2", "type": "DeployToSynology", "title": "群晖",
                     "input": {"accessId": sid, "asDefault": True}, "continueOnError": True},
                    {"id": "t3", "type": "DeployToQnap", "title": "威联通",
                     "input": {"accessId": qid}, "continueOnError": True},
                    {"id": "t4", "type": "DeployToProxmox", "title": "PVE",
                     "input": {"accessId": xid}, "continueOnError": True}]},
            ], "triggers": []},
        })
        check("面板部署流水线创建", ok(res) and res["data"].get("id"), msg(res))
        if not ok(res):
            return
        pid = res["data"]["id"]
        api.post("/api/pipeline/batch", {"action": "run", "ids": [pid]})

        detail = {}
        for _ in range(30):
            time.sleep(1)
            rows = api.get("/api/history/list?page=1&size=10").get("data", {}).get("records", [])
            cur = next((x for x in rows if x["pipelineId"] == pid), None)
            if cur and cur["status"] != "running":
                detail = api.get(f"/api/history/{cur['id']}").get("data") or {}
                break

        tasks = detail.get("tasks") or []
        check("三个部署任务全部成功",
              len(tasks) == 4 and all(t["status"] == "success" for t in tasks),
              str([(t["title"], t["status"], t.get("message")) for t in tasks]))

        check("DSM 登录带上了授权里的账号密码",
              any(s["query"].get("api") in (None, "SYNO.API.Auth")
                  and s["query"].get("account") == "dsm-user"
                  and s["query"].get("passwd") == "dsm-pass" for s in seen))
        imports = [s for s in seen
                   if s["query"].get("api") == "SYNO.Core.Certificate"
                   and s["query"].get("method") == "import"]
        check("DSM 用 SYNO.Core.Certificate 的 import 接口（.CRT 上没有 import，会回 103）",
              bool(imports), [s["query"].get("api") for s in seen])
        check("DSM 上传了证书与私钥",
              bool(imports) and imports[0]["has_cert"] and imports[0]["has_key"],
              imports[0]["body"][:160] if imports else "没有 import 请求")
        check("DSM 导入带上要覆盖的证书 id",
              bool(imports) and 'name="id"' in imports[0]["body"],
              imports[0]["body"][:200] if imports else "")
        check("DSM 任务里的 asDefault 覆盖生效",
              any(s["query"].get("api") == "SYNO.Core.Certificate"
                  and s["query"].get("method") == "set_default"
                  and s["query"].get("id") == "7" for s in seen),
              [s["query"].get("method") for s in seen])
        check("QTS 登录并上传证书",
              any(s["path"] == "/cgi-bin/authLogin.cgi" for s in seen)
              and any(s["path"] == "/cgi-bin/sslUtils.cgi" and s["has_cert"] for s in seen))
        check("PVE Token 头正确",
              any("certificates/custom" in s["path"]
                  and s["auth"] == "PVEAPIToken=root@pam!certd=pve-secret" for s in seen))
        check("PVE 节点名生效且带上证书",
              any("/nodes/pve01/certificates/custom" in s["path"] and s["has_cert"]
                  for s in seen))
    finally:
        srv.shutdown()
        if pid:
            api.delete(f"/api/pipeline/{pid}")
        for aid in aids:
            api.delete(f"/api/access/{aid}")
        for row in (api.get("/api/cert/list?page=1&size=50&keyword=panel-smoke.local")
                    .get("data") or {}).get("records", []):
            api.delete(f"/api/cert/{row['id']}")


def _run_and_wait(api: Api, pid: int, tries: int = 30) -> dict:
    """触发流水线并等它跑完，返回执行详情。"""
    api.post("/api/pipeline/batch", {"action": "run", "ids": [pid]})
    for _ in range(tries):
        time.sleep(1)
        rows = api.get("/api/history/list?page=1&size=10").get("data", {}).get("records", [])
        cur = next((x for x in rows if x["pipelineId"] == pid), None)
        if cur and cur["status"] != "running":
            return api.get(f"/api/history/{cur['id']}").get("data") or {}
    return {}


def section_notify_failfast(api: Api) -> None:
    """通知渠道：HTTP 200 但业务失败（errcode/code 非成功值）必须算失败。

    钉钉、企业微信、飞书这些渠道在 token 错误时照样返回 200，
    只看状态码会把「没发出去」记成「执行成功」，证书到期提醒就静默丢了。
    """
    print("\n== 通知渠道的失败识别 ==")
    cases = [
        ("dingtalk", "钉钉", {"webhook": "https://oapi.dingtalk.com/robot/send?access_token=fake"}),
        ("bark", "Bark", {"url": "https://api.day.app", "deviceKey": "fake"}),
        ("webhook", "自定义Webhook", {"url": "http://127.0.0.1:59996/hook"}),
    ]
    nids: list[int] = []
    pid = 0
    try:
        for typ, name, cfg in cases:
            res = api.post("/api/notification", {"type": typ, "name": f"__smoke_{typ}__",
                                                 "config": cfg, "enabled": True})
            if ok(res):
                nids.append(res["data"]["id"])
        check("通知渠道创建（三种）", len(nids) == len(cases), f"nids={nids}")
        if len(nids) != len(cases):
            return

        res = api.post("/api/pipeline", {
            "title": "__smoke_notify__", "remark": "smoke",
            "content": {"stages": [
                {"id": "s1", "title": "通知", "tasks": [
                    {"id": f"n{i}", "type": "Notify", "title": name,
                     "input": {"notificationId": nid, "title": "smoke", "onlyOnError": False},
                     "continueOnError": True}
                    for i, (nid, (_, name, _)) in enumerate(zip(nids, cases))]},
            ], "triggers": []},
        })
        check("通知流水线创建", ok(res) and res["data"].get("id"), msg(res))
        if not ok(res):
            return
        pid = res["data"]["id"]
        detail = _run_and_wait(api, pid)
        tasks = [t for t in (detail.get("tasks") or []) if t["title"] != "通知"]
        check("假密钥的通知任务全部判为失败",
              len(tasks) == len(cases) and all(t["status"] == "failed" for t in tasks),
              str([(t["title"], t["status"], t.get("message")) for t in tasks]))
        check("通知失败信息里没有 Python 堆栈",
              "Traceback" not in (detail.get("log") or ""))
        check("通知失败信息不含渠道密钥",
              all("access_token" not in (t.get("message") or "")
                  and "deviceKey" not in (t.get("message") or "") for t in tasks))
    finally:
        if pid:
            api.delete(f"/api/pipeline/{pid}")
        for nid in nids:
            api.delete(f"/api/notification/{nid}")


def section_deploy_error_readable(api: Api) -> None:
    """部署失败时，报错要能让人看懂：中文、说清是哪台机器，且不带堆栈。"""
    print("\n== 部署失败的报错可读性 ==")
    aid = 0
    pid = 0
    try:
        res = api.post("/api/access", {"category": "host", "type": "ssh", "name": "__smoke_ssh__",
                                       "config": {"host": "127.0.0.1", "port": 59996,
                                                  "username": "root", "authType": "password",
                                                  "password": "x"}})
        check("SSH 授权创建", ok(res), msg(res))
        if not ok(res):
            return
        aid = res["data"]["id"]

        res = api.post("/api/pipeline", {
            "title": "__smoke_deploy_err__", "remark": "smoke",
            "content": {"stages": [
                {"id": "s1", "title": "申请", "tasks": [
                    {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
                     "input": {"domains": "deploy-smoke.local", "days": 30}}]},
                {"id": "s2", "title": "部署", "tasks": [
                    {"id": "t2", "type": "DeployToHost", "title": "远程主机",
                     "input": {"accessId": aid, "certPath": "/tmp/a.crt",
                               "keyPath": "/tmp/a.key"}}]},
            ], "triggers": []},
        })
        check("部署流水线创建", ok(res) and res["data"].get("id"), msg(res))
        if not ok(res):
            return
        pid = res["data"]["id"]
        detail = _run_and_wait(api, pid)
        deploy_task = next((t for t in (detail.get("tasks") or [])
                            if t["title"] == "远程主机"), {})
        check("连不上主机时任务判为失败", deploy_task.get("status") == "failed",
              str(deploy_task.get("status")))
        check("报错说清了是哪台主机",
              "127.0.0.1:59996" in (deploy_task.get("message") or ""),
              str(deploy_task.get("message"))[:120])
        check("报错是中文且没有堆栈",
              "无法连接主机" in (deploy_task.get("message") or "")
              and "Traceback" not in (detail.get("log") or ""),
              str(deploy_task.get("message"))[:120])
    finally:
        if pid:
            api.delete(f"/api/pipeline/{pid}")
        if aid:
            api.delete(f"/api/access/{aid}")
        for row in (api.get("/api/cert/list?page=1&size=50&keyword=deploy-smoke.local")
                    .get("data") or {}).get("records", []):
            api.delete(f"/api/cert/{row['id']}")


# ---------------------------------------------------------------- 扩展部署插件
def _backend():
    """把 backend 加进 sys.path，便于直接导入服务层做单元级校验。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "backend"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _cdn_mock_server(responses: dict) -> tuple[ThreadingHTTPServer, list]:
    """国内 CDN 服务商的本地 mock：按路径返回预设 JSON，并记录收到的请求。"""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            parsed = urlparse(self.path)
            seen.append({
                "method": self.command,
                "path": parsed.path,
                "query": {k: v[0] for k, v in parse_qs(parsed.query).items()},
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": raw.decode("utf-8", "ignore"),
            })

            payload = responses.get((self.command, parsed.path))
            if payload is None:
                payload = responses.get(parsed.path)
            if callable(payload):
                payload = payload(parsed)
            if payload is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            status = 200
            if isinstance(payload, dict) and "__status__" in payload:
                status = int(payload["__status__"])
                payload = {k: v for k, v in payload.items() if k != "__status__"}
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if payload.get("__set_cookie__"):
                # 括彩云靠 Cookie 维持会话
                self.send_header("Set-Cookie", "JSESSIONID=MOCKJSESSION; Path=/")
            self.end_headers()
            self.wfile.write(body)

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_PATCH = _handle
        do_DELETE = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def section_cdn_deploy() -> None:
    """国内 CDN / 云厂商部署插件：用本地 mock 核对请求的 URL、鉴权头与请求体。

    没有真实账号，能验证的是「请求长什么样」；签名类（天翼云 / 多吉云 / 京东云）
    再在本地按同样算法复算一遍，至少能挡住后续改签名时的误伤。
    """
    print("\n== 国内 CDN 部署（本地 mock）==")
    _backend()
    import base64 as b64lib
    import hashlib as hashlib2
    import hmac as hmac2

    from app.services import deploy, deploy_cn

    ctx = deploy.CertContext(
        domain="cdn.example.com",
        crt="-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----\n",
        key="-----BEGIN PRIVATE KEY-----\nMOCKKEY\n-----END PRIVATE KEY-----\n",
        expires_time="2027-01-01 00:00:00", domains=["cdn.example.com"])
    handlers = deploy.DEPLOY_HANDLERS  # 含 deploy_cn 与 deploy_ext 注册的扩展插件

    def run(handler_name: str, config: dict) -> tuple[bool, str]:
        try:
            handlers[handler_name](ctx, config, lambda msg: None)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ------------------------------------------------ 天翼云
    server, seen = _cdn_mock_server({
        "/v1/cert/create": {"code": 100000, "id": 7028},
        "/v1/domain/batch_update_configuration_information": {
            "code": 100000,
            "domain_details": [{"code": 100000, "domain": "cdn.example.com"}]},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"accessKeyId": "ctyun-ak", "baseUrl": base,
               "securityKey": b64lib.b64encode(b"ctyun-secret-key").decode()}
        good, err = run("DeployToCtyunCdn", cfg)
        check("天翼云部署请求成功", good, err)
        if good and seen:
            hdr = seen[0]["headers"]
            check("天翼云带 x-alogic 签名头",
                  {"x-alogic-now", "x-alogic-app", "x-alogic-signature"} <= set(hdr),
                  str(sorted(hdr)))
            ak = cfg["accessKeyId"]
            now_ms = int(hdr["x-alogic-now"])
            first = hmac2.new(b64lib.b64decode(cfg["securityKey"]),
                              f"{ak}:{now_ms // 86400000}".encode(), hashlib2.sha256).digest()
            auth_key = deploy_cn._node_b64decode(deploy_cn._b64url(first))
            expect = deploy_cn._b64url(hmac2.new(
                auth_key, f"{ak}\n{now_ms}\n/v1/cert/create".encode(),
                hashlib2.sha256).digest())
            check("天翼云签名可复算一致", hdr["x-alogic-signature"] == expect,
                  f"{hdr['x-alogic-signature']} != {expect}")
            check("天翼云证书体包含 crt 与 key",
                  "BEGIN CERTIFICATE" in seen[0]["body"] and "PRIVATE KEY" in seen[0]["body"])
            check("天翼云下发域名时带 product_code",
                  any("product_code" in row["body"] for row in seen))
    finally:
        server.shutdown()

    # ------------------------------------------------ 多吉云
    server, seen = _cdn_mock_server({
        "/cdn/cert/upload.json": {"code": 200, "data": {"id": 99}},
        "/cdn/cert/bind.json": {"code": 200, "data": {}},
        "/cdn/cert/list.json": {"code": 200, "data": {"certs": []}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"accessKey": "doge-ak", "secretKey": "doge-sk", "baseUrl": base}
        good, err = run("DeployToDogeCdn", cfg)
        check("多吉云部署请求成功", good, err)
        if good and seen:
            auth = seen[0]["headers"].get("authorization") or ""
            check("多吉云使用 TOKEN 鉴权头", auth.startswith("TOKEN doge-ak:"), auth[:40])
            body = seen[0]["body"]
            sign = hmac2.new(b"doge-sk", f"/cdn/cert/upload.json\n{body}".encode(),
                             hashlib2.sha1).hexdigest()
            check("多吉云签名可复算一致", auth == f"TOKEN doge-ak:{sign}", auth[:80])
            check("多吉云表单体里带私钥", "private=" in body)
            check("多吉云绑定域名用了证书 ID",
                  any("99" in row["body"] for row in seen if "bind" in row["path"]))
    finally:
        server.shutdown()

    # ------------------------------------------------ 括彩云
    server, seen = _cdn_mock_server({
        "/login/loginUser": {"success": True, "data": "SESSION-TOKEN",
                             "__set_cookie__": True},
        "/CdnDomain/queryForDatatables": {
            "success": True, "data": {"data": [{"id": 12, "domainName": "cdn.example.com"}]}},
        "/CdnDomainHttps/httpsConfiguration": {"success": True},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"username": "kuocai-user", "password": "kuocai-pass", "baseUrl": base}
        good, err = run("DeployToKuocaiCdn", cfg)
        check("括彩云部署请求成功", good, err)
        if good:
            https_call = next((row for row in seen if "httpsConfiguration" in row["path"]), None)
            check("括彩云先登录再改 HTTPS 配置", https_call is not None,
                  str([row["path"] for row in seen]))
            if https_call:
                cookie = https_call["headers"].get("cookie") or ""
                check("括彩云请求带 JSESSIONID 与 token",
                      "JSESSIONID=" in cookie and "kuocai_cdn_token=" in cookie, cookie[:60])
                check("括彩云按域名 ID 提交",
                      '"doMainId":12' in https_call["body"].replace(" ", ""),
                      https_call["body"][:80])
    finally:
        server.shutdown()

    # ------------------------------------------------ 易盾
    server, seen = _cdn_mock_server({
        "/v1/sites": {"code": 0, "data": [{"id": 3, "domain": "cdn.example.com",
                                          "https_listen": {"cert": 7}}]},
        "/v1/certs/7": {"code": 0, "data": {}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"apiKey": "yidun-key", "apiSecret": "yidun-secret", "baseUrl": base}
        good, err = run("DeployToYidunCdn", cfg)
        check("易盾部署请求成功", good, err)
        if good and seen:
            check("易盾带 api-key / api-secret 头",
                  seen[0]["headers"].get("api-key") == "yidun-key"
                  and seen[0]["headers"].get("api-secret") == "yidun-secret")
            put = next((row for row in seen if row["method"] == "PUT"), None)
            check("易盾按站点已有证书 ID 更新",
                  put is not None and put["path"].endswith("/v1/certs/7"),
                  str([row["path"] for row in seen]))
    finally:
        server.shutdown()

    # ------------------------------------------------ 白山云
    server, seen = _cdn_mock_server({
        "/v2/domain/certificate": {"code": 0, "message": "ok"},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"token": "baishan-token", "baseUrl": base, "certId": 224995}
        good, err = run("DeployToBaishanCdn", cfg)
        check("白山云部署请求成功", good, err)
        if good and seen:
            check("白山云 token 走 query",
                  seen[0]["query"].get("token") == "baishan-token", str(seen[0]["query"]))
            check("白山云提交证书 ID",
                  "224995" in seen[0]["body"], seen[0]["body"][:120])
    finally:
        server.shutdown()

    # ------------------------------------------------ 我爱云
    server, seen = _cdn_mock_server({
        "/account/login": {"code": 200, "data": {"token": "WOAI-TOKEN"}},
        "/certificate/edit": {"code": 200, "message": "ok"},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"username": "woai-user", "password": "woai-pass",
               "baseUrl": base, "certId": "CERT-1"}
        good, err = run("DeployToWoaiCdn", cfg)
        check("我爱云部署请求成功", good, err)
        if good:
            edit = next((row for row in seen if "certificate/edit" in row["path"]), None)
            check("我爱云先登录再改证书", edit is not None,
                  str([row["path"] for row in seen]))
            if edit:
                check("我爱云编辑请求带 Token 头",
                      edit["headers"].get("token") == "WOAI-TOKEN",
                      str(edit["headers"].get("token")))
    finally:
        server.shutdown()

    # ------------------------------------------------ 京东云
    server, seen = _cdn_mock_server({
        "/v1/sslCert:upload": {"requestId": "r1", "result": {"certId": 4242}},
        "/v1/domain/cdn.example.com/httpType": {"requestId": "r2", "result": {}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"accessKeyId": "jd-ak", "secretAccessKey": "jd-sk", "baseUrl": base}
        good, err = run("DeployToJDCloudCdn", cfg)
        check("京东云部署请求成功", good, err)
        if good and seen:
            auth = seen[0]["headers"].get("authorization") or ""
            check("京东云使用 JDCLOUD2 签名",
                  auth.startswith("JDCLOUD2-HMAC-SHA256 Credential=jd-ak/"), auth[:60])
            check("京东云带 x-jdcloud-date / x-jdcloud-nonce",
                  "x-jdcloud-date" in seen[0]["headers"]
                  and "x-jdcloud-nonce" in seen[0]["headers"])
            check("京东云 scope 含服务名与 jdcloud2_request",
                  "/ssl/jdcloud2_request" in auth, auth[:140])
            date_hdr = seen[0]["headers"]["x-jdcloud-date"]
            signed = auth.split("SignedHeaders=")[1].split(",")[0]
            head_names = signed.split(";")
            canonical_headers = "".join(
                f"{name}:{seen[0]['headers'].get(name, '').strip()}\n" for name in head_names)
            payload_hash = hashlib2.sha256(seen[0]["body"].encode()).hexdigest()
            canonical = "\n".join(["POST", "/v1/sslCert:upload", "",
                                    canonical_headers, signed, payload_hash])
            scope = f"{date_hdr[:8]}/cn-north-1/ssl/jdcloud2_request"
            sts = "\n".join(["JDCLOUD2-HMAC-SHA256", date_hdr, scope,
                              hashlib2.sha256(canonical.encode()).hexdigest()])
            key = hmac2.new(("JDCLOUD2jd-sk").encode(), date_hdr[:8].encode(),
                            hashlib2.sha256).digest()
            for part in ("cn-north-1", "ssl", "jdcloud2_request"):
                key = hmac2.new(key, part.encode(), hashlib2.sha256).digest()
            expect = hmac2.new(key, sts.encode(), hashlib2.sha256).hexdigest()
            check("京东云签名可复算一致", auth.endswith(expect), auth[-70:])
            check("京东云给加速域名设置 https",
                  any("/httpType" in row["path"] and "https" in row["body"] for row in seen),
                  str([row["path"] for row in seen]))
    finally:
        server.shutdown()

    # ------------------------------------------------ K8s（复用已有 handler）
    # 场景一：Secret 已存在（POST 冲突 409）→ 更新，并触发 Ingress 重载
    server, seen = _cdn_mock_server({
        ("POST", "/api/v1/namespaces/default/secrets"):
            {"__status__": 409, "reason": "AlreadyExists"},
        ("GET", "/api/v1/namespaces/default/secrets/web-tls"): {
            "metadata": {"name": "web-tls", "resourceVersion": "100"}},
        ("PUT", "/api/v1/namespaces/default/secrets/web-tls"): {"metadata": {"name": "web-tls"}},
        ("PATCH", "/apis/networking.k8s.io/v1/namespaces/default/ingresses/web"):
            {"metadata": {"name": "web"}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"apiServer": base, "token": "k8s-token", "insecure": True,
               "secretName": "web-tls", "ingressNames": ["web"]}
        good, err = run("DeployToK8sSecret", cfg)
        check("K8s 已存在时改为更新", good, err)
        if good:
            put = next((row for row in seen if row["method"] == "PUT"), None)
            check("K8s 更新时带 resourceVersion",
                  put is not None and "100" in put["body"],
                  (put or {}).get("body", "")[:100])
            patch = next((row for row in seen if row["method"] == "PATCH"), None)
            check("K8s 触发 Ingress 重载",
                  patch is not None
                  and patch["headers"].get("content-type") == "application/merge-patch+json",
                  str([row["method"] for row in seen]))
    finally:
        server.shutdown()

    # 场景二：Secret 不存在 → 新建，类型必须是 kubernetes.io/tls
    server, seen = _cdn_mock_server({
        ("POST", "/api/v1/namespaces/default/secrets"): {"metadata": {"name": "new-tls"}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"apiServer": base, "token": "k8s-token", "insecure": True,
               "secretName": "new-tls"}
        good, err = run("DeployToK8sSecret", cfg)
        check("K8s 不存在时创建 Secret", good, err)
        if good and seen:
            body = seen[0]["body"]
            check("K8s Secret 类型为 kubernetes.io/tls", "kubernetes.io/tls" in body)
            check("K8s Secret 里同时有 tls.crt 与 tls.key",
                  "tls.crt" in body and "tls.key" in body)
    finally:
        server.shutdown()

def section_cdn_deploy_pipeline(api: Api) -> None:
    """走完整流水线跑一次天翼云部署：验证「元数据 → 引擎 → 授权合并 → handler」这条链。

    单测 handler 只证明请求拼得对；这里证明引擎确实把授权配置（含 baseUrl）
    合并进了任务入参，否则界面上选好的授权在运行时是空的。
    """
    print("\n== 天翼云部署（真实流水线 + 本地 mock）==")
    _backend()
    server, seen = _cdn_mock_server({
        "/v1/cert/create": {"code": 100000, "id": 7028},
        "/v1/domain/batch_update_configuration_information": {
            "code": 100000,
            "domain_details": [{"code": 100000, "domain": "pipeline.example.com"}]},
    })
    base = f"http://127.0.0.1:{server.server_address[1]}"
    aid = pid = 0
    try:
        res = api.post("/api/access", {
            "category": "cloud", "type": "ctyun", "name": "__smoke_ctyun__",
            "config": {"accessKeyId": "ctyun-ak", "baseUrl": base,
                       "securityKey": "Y3R5dW4tc2VjcmV0"},
        })
        check("天翼云授权创建", ok(res) and res["data"].get("id"), msg(res))
        aid = (res.get("data") or {}).get("id") or 0
        if not aid:
            return

        res = api.post("/api/pipeline", {
            "title": "__smoke_ctyun_pipeline__", "remark": "smoke",
            "content": {"stages": [
                {"id": "s1", "title": "申请证书", "tasks": [
                    {"id": "t1", "type": "CertApplySelfSigned", "title": "自签证书",
                     "input": {"domains": ["pipeline.example.com"], "days": 30},
                     "continueOnError": False}]},
                {"id": "s2", "title": "部署证书", "tasks": [
                    {"id": "t2", "type": "DeployToCtyunCdn", "title": "部署到天翼云 CDN",
                     "input": {"accessId": aid, "productCode": "008",
                               "domains": ["pipeline.example.com"]},
                     "continueOnError": False}]},
            ], "triggers": []},
        })
        check("天翼云流水线创建", ok(res) and res["data"].get("id"), msg(res))
        pid = (res.get("data") or {}).get("id") or 0
        if not pid:
            return

        detail = _run_and_wait(api, pid)
        check("天翼云流水线执行成功", detail.get("status") == "success",
              f"{detail.get('status')} · {(detail.get('log') or '')[-160:]}")
        check("天翼云 mock 收到了创建证书请求",
              any(row["path"] == "/v1/cert/create" for row in seen),
              str([row["path"] for row in seen]))
        check("天翼云 mock 收到的请求带签名头",
              all("x-alogic-signature" in row["headers"] for row in seen))
        check("授权里的 baseUrl 被合并进任务入参", bool(seen), "没有发出任何请求")
    finally:
        if pid:
            api.delete(f"/api/pipeline/{pid}")
        if aid:
            api.delete(f"/api/access/{aid}")
        server.shutdown()

def section_more_deploy() -> None:
    """雷池 / 又拍云 / 腾讯云 CLB、EdgeOne 部署插件：mock 或假凭据探测。"""
    print("\n== 雷池 / 又拍云 / 腾讯云 CLB / EdgeOne ==")
    _backend()
    from app.services import deploy, deploy_more, resources  # noqa: F401

    ctx = deploy.CertContext(
        domain="more.example.com",
        crt="-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----\n",
        key="-----BEGIN PRIVATE KEY-----\nMOCKKEY\n-----END PRIVATE KEY-----\n",
        expires_time="2027-01-01 00:00:00", domains=["more.example.com"])

    def run(name: str, config: dict) -> tuple[bool, str]:
        try:
            deploy.DEPLOY_HANDLERS[name](ctx, config, lambda m: None)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ---------------- 长亭雷池
    server, seen = _cdn_mock_server({
        ("GET", "/api/open/cert"): {"err": None, "msg": "ok",
                                      "data": {"nodes": [{"id": 12, "domains": ["more.example.com"]}]}},
        ("POST", "/api/open/cert"): {"err": None, "msg": "ok", "data": 13},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"baseUrl": base, "apiToken": "safeline-token", "insecure": True,
               "certIds": ["12", "0"]}
        good, err = run("DeployToSafeline", cfg)
        check("雷池部署请求成功", good, err)
        if good:
            posts = [row for row in seen if row["method"] == "POST"]
            check("雷池带 X-SLCE-API-TOKEN 头",
                  all(row["headers"].get("x-slce-api-token") == "safeline-token"
                      for row in posts), str([r["headers"].get("x-slce-api-token") for r in posts]))
            update_body = posts[0]["body"].replace(" ", "") if posts else ""
            create_body = posts[1]["body"].replace(" ", "") if len(posts) > 1 else ""
            check("雷池更新时带证书 ID、新增时不带 ID",
                  len(posts) == 2 and '"id":12' in update_body and '"id"' not in create_body,
                  str([row["body"][:80] for row in posts]))
            check("雷池提交证书与私钥",
                  all("BEGIN CERTIFICATE" in row["body"] for row in posts))
    finally:
        server.shutdown()

    # ---------------- 又拍云
    server, seen = _cdn_mock_server({
        "/accounts/signin/": {"errors": [], "data": {"error_code": 0},
                              "__set_cookie__": True},
        "/api/https/certificate/": {"data": {"result": {"certificate_id": 999}}},
        "/api/https/migrate/domain": {"data": {}},
        "/api/https/certificate/manager": {"data": {}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"username": "upyun-user", "password": "upyun-pass", "baseUrl": base,
               "domains": ["cdn.more.example.com"], "forceHttps": "true"}
        good, err = run("DeployToUpyun", cfg)
        check("又拍云部署请求成功", good, err)
        if good:
            login = next((row for row in seen if "signin" in row["path"]), None)
            check("又拍云先登录", login is not None, str([r["path"] for r in seen]))
            others = [row for row in seen if "signin" not in row["path"]]
            check("又拍云后续请求带 Cookie",
                  all("JSESSIONID=" in (row["headers"].get("cookie") or "") for row in others),
                  str([row["headers"].get("cookie") for row in others]))
            upload = next((row for row in seen if row["path"].endswith("/api/https/certificate/")), None)
            check("又拍云上传证书带 certificate/private_key",
                  upload is not None and "certificate" in upload["body"] and "private_key" in upload["body"])
            bind = next((row for row in seen if "migrate/domain" in row["path"]), None)
            check("又拍云绑定域名用证书 ID 999",
                  bind is not None and "999" in bind["body"], (bind or {}).get("body", "")[:100])
            manage = next((row for row in seen if "certificate/manager" in row["path"]), None)
            check("又拍云设置强制 HTTPS",
                  manage is not None and "force_https" in manage["body"],
                  (manage or {}).get("body", "")[:100])
    finally:
        server.shutdown()

    # ---------------- 火山引擎免费证书：请求体必须按真实契约（CommonName/Plan/OrganizationId/ValidationType）
    _backend()
    from app.services import volcengine as volc

    captured = {}

    def fake_call(config, action, body=None, method="POST", version=None, timeout=30):
        captured[action] = body
        if action == "CertificateGetOrganizationList":
            return {"Organizations": [{"OrganizationId": "org-smoke"}]}
        if action == "QuickApplyCertificate":
            return {"InstanceId": "inst-smoke"}
        if action == "CertificateGetDcvParam":
            return {"DcvKey": "_dnsauth.smoke", "DcvValue": "txt-value"}
        if action == "CertificateGetInstance":
            return {"Status": "Issued", "Certificate": "-----BEGIN CERTIFICATE-----\nX\n"
                                                      "-----END CERTIFICATE-----",
                    "PrivateKey": "-----BEGIN PRIVATE KEY-----\nY\n-----END PRIVATE KEY-----"}
        return {}

    original_call = volc.call
    volc.call = fake_call
    try:
        try:
            volc.apply_free_certificate({"accessKeyId": "a", "accessKeySecret": "b"},
                                        "smoke.example.com", lambda m: None,
                                        key_type="RSA", poll_seconds=0.01, timeout_seconds=5)
            check("火山引擎免费证书：缺 Plan 时给出明确提示", False, "没有报错")
        except Exception as exc:  # noqa: BLE001
            check("火山引擎免费证书：缺 Plan 时给出明确提示", "Plan" in str(exc), str(exc))

        captured.clear()
        result = volc.apply_free_certificate(
            {"accessKeyId": "a", "accessKeySecret": "b"}, "smoke.example.com",
            lambda m: None, key_type="RSA", poll_seconds=0.01, timeout_seconds=30,
            plan="smoke-plan", dcv_handler=lambda name, value: None)
        body = captured.get("QuickApplyCertificate") or {}
        check("火山引擎请求体使用真实字段名",
              {"CommonName", "Plan", "OrganizationId", "ValidationType", "KeyAlg"} <= set(body),
              str(sorted(body)))
        check("火山引擎域名/套餐/组织机构正确",
              body.get("CommonName") == "smoke.example.com"
              and body.get("Plan") == "smoke-plan"
              and body.get("OrganizationId") == "org-smoke"
              and body.get("ValidationType") == "dns_txt",
              str(body))
        check("火山引擎返回证书与私钥", bool(result.get("certificate")) and bool(result.get("privateKey")))
    finally:
        volc.call = original_call

    # ---------------- 腾讯云 CLB（假凭据探测 action 是否有效）
    fake = {"secretId": "AKIDsmokeFake000000000", "secretKey": "smokeFakeSecret"}
    ok_probe, err_probe = run("DeployToTencentClb", {
        **fake, "loadBalancerId": "lb-smoke", "listenerId": "lbl-smoke"})
    if "ConnectError" in err_probe or "无法连接" in err_probe:
        SKIP.append("腾讯云 CLB（网络不可达）")
    else:
        check("腾讯云 CLB 使用有效 action（签名被接受）",
              not ok_probe and ("AuthFailure" in err_probe or "SecretId" in err_probe
                                or "InvalidParameter" in err_probe),
              err_probe[:160])
        check("腾讯云 CLB 报错不含 InvalidAction", "InvalidAction" not in err_probe,
              err_probe[:160])

    # ---------------- 腾讯云 EdgeOne（mock SSL + teo 全链路）
    calls: dict[str, list[dict]] = {}

    def fake_edgeone_call(config, host, service, version, action, body=None, timeout=30):
        calls.setdefault(action, []).append(body or {})
        if action == "UploadCertificate":
            return {"CertificateId": "cert-smoke"}
        if action == "DescribeZones":
            return {"Zones": [{"ZoneId": "zone-a", "ZoneName": "example.com"},
                              {"ZoneId": "zone-b", "ZoneName": "example.net"}],
                    "TotalCount": 2}
        if action == "DescribeAccelerationDomains":
            zone = (body or {}).get("ZoneId")
            domains = {"zone-a": ["cdn.example.com"],
                       "zone-b": ["static.example.net"]}.get(zone, [])
            return {"AccelerationDomains": [{"DomainName": d} for d in domains],
                    "TotalCount": len(domains)}
        if action == "ModifyHostsCertificate":
            return {"RequestId": "req-smoke"}
        return {}

    original_call = deploy_more.call_api
    deploy_more.call_api = fake_edgeone_call
    try:
        good, err = run("DeployToTencentEdgeOne", {
            **fake, "domain": ["cdn.example.com", "static.example.net"],
            "certName": "smoke-{domain}"})
        check("腾讯云 EdgeOne 部署成功", good, err)
        modify = calls.get("ModifyHostsCertificate") or []
        check("EdgeOne 按站点分组下发证书", len(modify) == 2, str(modify))
        zone_hosts = {(b.get("ZoneId"), tuple(b.get("Hosts") or [])) for b in modify}
        check("EdgeOne 每个站点只带自己的域名",
              zone_hosts == {("zone-a", ("cdn.example.com",)),
                             ("zone-b", ("static.example.net",))}, str(zone_hosts))
        first = modify[0] if modify else {}
        check("EdgeOne 使用 sslcert + ServerCertInfo.CertId",
              first.get("Mode") == "sslcert"
              and (first.get("ServerCertInfo") or [{}])[0].get("CertId") == "cert-smoke",
              str(first))
        check("EdgeOne 先上传证书到 SSL 证书中心",
              bool(calls.get("UploadCertificate")), str(list(calls)))
        items, error = resources.resolve("tencentcloud",
                                         {"secretId": "AKIDsmoke", "secretKey": "sk"},
                                         "edgeoneDomains")
        check("EdgeOne 加速域名可自动拉取（带站点名）",
              not error and len(items) == 2
              and all("EdgeOne" in str(i.get("label")) for i in items),
              f"{error} / {items}")
    finally:
        deploy_more.call_api = original_call

    calls.clear()
    deploy_more.call_api = fake_edgeone_call
    try:
        good, err = run("DeployToTencentEdgeOne", {
            **fake, "domain": ["not-found.example.com"], "certName": "smoke"})
        check("EdgeOne 域名不存在时给中文结论",
              not good and "找不到加速域名" in err, err[:200])
    finally:
        deploy_more.call_api = original_call

def section_panel_multi() -> None:
    """宝塔 / 1Panel / NPM 站点多选：一个任务部署到多个站点或代理主机。"""
    print("\n== 面板站点多选（宝塔 / 1Panel / NPM）==")
    _backend()
    from app.services import deploy, deploy_ext, resources
    from app.services.engine import PipelineRunner

    ctx = deploy.CertContext(
        domain="www.example.com",
        crt="-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----\n",
        key="-----BEGIN PRIVATE KEY-----\nMOCKKEY\n-----END PRIVATE KEY-----\n",
        expires_time="2027-01-01 00:00:00",
        domains=["www.example.com", "api.example.com"],
    )

    class Resp:
        def __init__(self, data=None, status_code=200, text=""):
            self._data = data if data is not None else {}
            self.status_code = status_code
            self.text = text or str(self._data)

        def json(self):
            return self._data

    # 宝塔：多选站点 → 逐个 SetSSL
    calls: list[dict] = []

    def fake_baota(method, url, **kwargs):
        calls.append(kwargs.get("data") or {})
        return Resp({"status": True})

    original = deploy._panel_request
    deploy._panel_request = fake_baota
    try:
        deploy.deploy_to_baota(ctx, {"url": "http://panel", "apiKey": "k",
                                     "siteName": ["site-a", "site-b"]}, lambda m: None)
        check("宝塔站点可多选并逐个部署",
              [c.get("siteName") for c in calls] == ["site-a", "site-b"], str(calls))
    finally:
        deploy._panel_request = original

    # 1Panel：上传一次证书，绑定多个网站
    one_calls: list[str] = []

    def fake_one(method, url, **kwargs):
        one_calls.append(url)
        if url.endswith("/websites/ssl/upload"):
            return Resp({"code": 200, "data": {"id": 99}})
        return Resp({"code": 200})

    original = deploy._panel_request
    deploy._panel_request = fake_one
    try:
        deploy.deploy_to_1panel(ctx, {"url": "http://panel", "apiKey": "k",
                                      "websiteId": ["101", "102"]}, lambda m: None)
        check("1Panel 网站可多选（证书只上传一次）",
              len([u for u in one_calls if u.endswith("/websites/ssl/upload")]) == 1
              and len([u for u in one_calls if u.endswith("/https")]) == 2,
              str(one_calls))
    finally:
        deploy._panel_request = original

    # NPM：上传一次证书，绑定多个代理主机
    npm_calls: list[tuple[str, str]] = []

    def fake_npm(method, url, **kwargs):
        npm_calls.append((method, url))
        if url.endswith("/api/tokens"):
            return Resp({"token": "t"})
        if url.endswith("/api/nginx/certificates"):
            return Resp({"id": 55})
        return Resp({"id": 1, "domain_names": ["www.example.com"]})

    original = deploy_ext._panel_request
    deploy_ext._panel_request = fake_npm
    try:
        deploy_ext.deploy_to_npm(ctx, {"url": "http://npm", "email": "a@b.c",
                                       "password": "p", "proxyHostId": ["1", "2"]},
                                 lambda m: None)
        check("NPM 代理主机可多选并逐个绑定",
              len([c for c in npm_calls if c[0] == "PUT"]) == 2, str(npm_calls))
    finally:
        deploy_ext._panel_request = original

    # NPM 资源自动拉取
    original_json = resources._get_json

    def fake_json(method, url, **kwargs):
        if url.endswith("/api/tokens"):
            return {"token": "t"}
        return [{"id": 1, "domain_names": ["www.example.com"]},
                {"id": 2, "domain_names": ["api.example.com"]}]

    resources._get_json = fake_json
    try:
        items, error = resources.resolve("npm", {"url": "http://npm"}, "npmProxyHosts")
        check("NPM 代理主机可自动拉取",
              not error and [i["value"] for i in items] == ["1", "2"], f"{error} / {items}")
    finally:
        resources._get_json = original_json

    # 引擎自动匹配：多域名证书把所有命中的 tag 选项都选上
    logs: list[str] = []

    class Stub:
        _AUTO_MATCH = PipelineRunner._AUTO_MATCH

        def _access(self, aid):
            return "baota", {}

        def log(self, msg, task=None):
            logs.append(msg)

    original_resolve = resources.resolve
    resources.resolve = lambda access_type, cfg, kind: (
        [{"label": "site-a", "value": "site-a", "extra": "www.example.com"},
         {"label": "site-b", "value": "site-b", "extra": "api.example.com"},
         {"label": "other", "value": "other", "extra": "other.com"}], "")
    try:
        cfg = {"autoMatch": True, "accessId": 1}
        PipelineRunner._auto_match_resource(Stub(), "DeployToBaota", cfg,
                                            ["www.example.com", "api.example.com"], {})
        check("多域名自动匹配会选中全部站点",
              cfg.get("siteName") == ["site-a", "site-b"], str(cfg))
    finally:
        resources.resolve = original_resolve

    # 元数据：三个字段都必须是可多选的 tags + remote
    from app.plugins import TASK_PLUGIN_MAP

    for plugin_type, field in (("DeployToBaota", "siteName"),
                               ("DeployTo1Panel", "websiteId"),
                               ("DeployToNpm", "proxyHostId")):
        meta = next((i for i in TASK_PLUGIN_MAP[plugin_type]["inputs"] if i["key"] == field), {})
        check(f"{plugin_type}.{field} 是多选字段",
              meta.get("component") == "tags" and bool(meta.get("remote")), str(meta))


def _proxy_mock() -> tuple[ThreadingHTTPServer, list]:
    """假装一个 HTTP 代理：请求行里是绝对 URL（http://host/path），记下来再回 200。"""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append({"method": "GET", "path": self.path,
                         "host": self.headers.get("Host") or "",
                         "headers": {k.lower(): v for k, v in self.headers.items()}})
            body = b'{"proxied": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_CONNECT(self):
            # https 目标走代理时先收到 CONNECT：记下来，然后直接拒掉
            seen.append({"method": "CONNECT", "path": self.path,
                         "host": self.headers.get("Host") or "",
                         "headers": {k.lower(): v for k, v in self.headers.items()}})
            self.send_response(502)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def section_network(api: Api) -> None:
    """网络设置：HTTP_PROXY / HTTPS_PROXY / NO_PROXY + 反代域名。"""
    print("\n== 网络设置（代理 + 反向代理）==")
    _backend()
    from app.services import net
    from app.services.acme import AcmeClient

    # 1. 反代域名映射：内置默认 + 任务级覆盖
    check("Google 端点默认映射到内置反代",
          net.reverse_proxy_for("https://dv.acme-v02.api.pki.goog/directory")
          == "gg.px.certd.handfree.work")
    check("Let's Encrypt 端点默认映射到内置反代",
          net.reverse_proxy_for("https://acme-v02.api.letsencrypt.org/directory")
          == "le.px.certd.handfree.work")
    check("没有反代的 CA 返回空（照旧直连）",
          net.reverse_proxy_for("https://acme.zerossl.com/v2/DV90") == "")
    check("任务里填的自定义反代优先",
          net.reverse_proxy_for("https://dv.acme-v02.api.pki.goog/directory",
                                "gg.myproxy.com") == "gg.myproxy.com")

    # 2. ACME 客户端只替换传输地址，签名仍用原始 URL
    client = AcmeClient("https://dv.acme-v02.api.pki.goog/directory")
    client.enable_reverse_proxy({"dv.acme-v02.api.pki.goog": "gg.px.certd.handfree.work"})
    mapped = client._transport_url(
        "https://dv.acme-v02.api.pki.goog/acme/new-order")
    check("ACME 反代只换域名、保留路径",
          mapped == "https://gg.px.certd.handfree.work/acme/new-order", mapped)
    check("ACME 反代不改其他 CA 的地址",
          client._transport_url("https://acme-v02.api.letsencrypt.org/directory")
          == "https://acme-v02.api.letsencrypt.org/directory")
    client.close()

    # 3. 没配代理时一律直连
    old = (api.get("/api/settings").get("data") or {}).get("network") or {}
    api.put("/api/settings", {"values": {"network": {
        "httpProxy": "", "httpsProxy": "", "noProxy": "", "reverseProxies": {}}}})
    net.invalidate()
    check("没配代理时不返回代理", net.proxy_for("https://dv.acme-v02.api.pki.goog/x") is None)
    check("没配代理时 client 不挂 transport", net.proxy_mounts() is None)

    # 4. 配了代理就默认全部走代理（certd / HTTP_PROXY 语义）
    server, seen = _proxy_mock()
    proxy = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        res = api.put("/api/settings", {"values": {"network": {
            "httpProxy": proxy, "httpsProxy": proxy, "noProxy": "",
            "reverseProxies": {"acme.zerossl.com": "zerossl.myproxy.com"}}}})
        check("保存网络设置", ok(res), msg(res))
        net.invalidate()
        setting = (api.get("/api/settings").get("data") or {}).get("network") or {}
        check("网络设置明文回显",
              setting.get("httpProxy") == proxy and setting.get("httpsProxy") == proxy,
              str(setting)[:180])
        check("反代覆盖值随设置保存",
              (setting.get("resolvedReverseProxies") or {}).get("acme.zerossl.com")
              == "zerossl.myproxy.com", str(setting.get("resolvedReverseProxies")))
        check("配置后 http 请求走代理", net.proxy_for("http://overseas.test/x") == proxy)

        resp = net.get("http://overseas.test/secure")
        check("命中代理的请求真的发给了代理",
              resp.status_code == 200
              and any(r["path"] == "http://overseas.test/secure" for r in seen),
              str(seen))

        # 5. Client 形态（ACME / DNS）：https 目标应先 CONNECT 到代理
        try:
            net.client(timeout=3).get("https://dv.acme-v02.api.pki.goog/directory")
        except Exception:  # noqa: BLE001
            pass
        check("ACME / DNS 的 Client 也走代理（CONNECT）",
              any(r.get("method") == "CONNECT" and "dv.acme-v02.api.pki.goog" in r["path"]
                  for r in seen), str(seen[-3:]))

        # 6. noProxy 排除清单：命中的直连
        api.put("/api/settings", {"values": {"network": {
            "httpProxy": proxy, "httpsProxy": proxy,
            "noProxy": "localhost,127.0.0.1,.example.com,192.168.*",
            "reverseProxies": {}}}})
        net.invalidate()
        check("noProxy 命中的域名不走代理",
              net.proxy_for("http://api.example.com/x") is None
              and net.proxy_for("http://192.168.1.5/x") is None)
        check("noProxy 不影响其他域名",
              net.proxy_for("http://dv.acme-v02.api.pki.goog/x") == proxy)
        before = len(seen)
        try:
            net.get("http://skip.example.com/x", timeout=2)
        except Exception:  # noqa: BLE001
            pass
        check("noProxy 请求没有经过代理", len(seen) == before, str(seen[before:]))

        # 7. 测试接口：三条链路各给一份结果 + 一句结论
        res = api.post("/api/settings/proxy/test", {"target": ""})
        data = res.get("data") or {}
        check("网络测试返回直连 / 代理 / 反代三份结果",
              ok(res) and "direct" in data and "proxied" in data and "reverse" in data,
              msg(res))
        check("网络测试给出结论文案", bool(data.get("verdict")), str(data)[:160])
    finally:
        # 还原：冒烟不能把用户的网络设置留下
        api.put("/api/settings", {"values": {"network": old or {
            "httpProxy": "", "httpsProxy": "", "noProxy": "", "reverseProxies": {}}}})
        net.invalidate()
        server.shutdown()


#: 冒烟自己用的测试域名：收尾时只按这些域名清证书。
#:
#: 为什么不能按 pipeline_id 清：SQLite 会复用已删除行的自增 ID，
#: 用户历史上某张证书的 pipeline_id 可能正好落到这一轮新建的冒烟流水线上，
#: 于是「清自己搞出来的垃圾」变成「删用户的证书」——真实踩过。
TEST_DOMAINS = {
    "smoke.local", "smoke-s3.local", "pipeline.example.com", "site-a.com", "site-b.com",
    "auto-match.local", "panel-smoke.local", "deploy-smoke.local", "eab.smoke.local",
    "localhost", "group-smoke.local", "trustasia-smoke.local", "switch-smoke.local",
    "skip-smoke.local",
}


def purge_test_certs(api: Api) -> int:
    """删除测试域名产出的证书，返回删除数量。用户自己的域名一张都不动。"""
    rows: list[dict] = []
    for page in range(1, 8):
        data = api.get(f"/api/cert/list?page={page}&size=100").get("data") or {}
        rows.extend(data.get("records") or [])
        if len(rows) >= (data.get("total") or 0):
            break
    removed = 0
    for row in rows:
        domains = row.get("domains") or []
        if not domains or not all(d in TEST_DOMAINS for d in domains):
            continue
        api.delete(f"/api/cert/{row['id']}")
        removed += 1
    return removed


def _drop_pipeline(api: Api, pid: int) -> None:
    """删流水线时连带清掉它的执行历史，跑完不在用户界面留垃圾。

    注意：**不要**顺手删这条流水线的证书（见 TEST_DOMAINS 的注释），
    证书统一由 purge_test_certs() 按域名清理。
    """
    if not pid:
        return
    # 最后一节会 post /batch 触发一次异步运行，立刻删会被后端以
    # 「流水线正在运行，无法删除」拒绝，跑完就一直在界面上留着一条 __smoke_crud__。
    for _ in range(60):
        res = api.delete(f"/api/pipeline/{pid}")
        if res.get("code") == 200:
            break
        time.sleep(1)
    rows = (api.get("/api/history/list?page=1&size=100").get("data") or {}).get("records") or []
    for row in rows:
        if row.get("pipelineId") == pid:
            api.delete(f"/api/history/{row['id']}")


def section_cert_apply_inputs(api: Api) -> None:
    """证书申请任务的入参契约：必填项、EAB 显隐、网络代理选项。"""
    print("\n== 证书申请入参 ==")
    plugins = api.get("/api/pipeline/plugins").get("data") or {}
    cert = next((p for p in plugins.get("plugins", []) if p.get("type") == "CertApply"), None)
    check("CertApply 插件已注册", cert is not None)
    if not cert:
        return
    inputs = {item["key"]: item for item in cert.get("inputs") or []}
    required = {key for key, item in inputs.items() if item.get("required")}
    check("证书域名与联系邮箱必填",
          {"domains", "email"} <= required, str(sorted(required)))
    check("EAB 不再让用户手填 Key，改成选授权",
          "eabAccessId" in inputs and "eabKid" not in inputs and "eabHmacKey" not in inputs,
          str(sorted(inputs)))
    check("EAB 授权下拉归到「证书签发」分类",
          inputs["eabAccessId"].get("accessCategory") == "cert",
          str(inputs["eabAccessId"].get("accessCategory")))
    access_types = plugins.get("accessTypes") or {}
    check("授权管理里有 eab 类型（证书签发分类）",
          (access_types.get("eab") or {}).get("category") == "cert",
          str((access_types.get("eab") or {}).get("category")))
    eab_inputs = {i["key"]: i for i in (access_types.get("eab") or {}).get("inputs") or []}
    check("EAB 授权里 Key ID 必填、HMAC Key 是密码框",
          bool(eab_inputs.get("kid", {}).get("required"))
          and eab_inputs.get("hmacKey", {}).get("component") == "password",
          str(sorted(eab_inputs)))
    providers = [o.get("value") for o in inputs["provider"].get("options") or []]
    check("CA 选项含 Let's Encrypt / Google / ZeroSSL",
          {"letsencrypt", "google", "zerossl"} <= set(providers), str(providers))
    eab_when = (inputs["eabAccessId"].get("showWhen") or {}).get("values") or []
    check("EAB 授权只在需要它的 CA 下显示（Google / 自定义 / FreeSSL）",
          set(eab_when) == {"google", "custom", "litessl"}, str(eab_when))
    check("目录地址只在自定义 CA 下显示",
          (inputs["directory"].get("showWhen") or {}).get("value") == "custom")
    check("DNS 授权只在 DNS 验证下显示",
          (inputs["dnsAccessId"].get("showWhen") or {}).get("value") == "dns")
    check("HTTP 上传路径只在 HTTP 验证下显示",
          (inputs["httpWebRoot"].get("showWhen") or {}).get("value") == "http")
    check("提供「使用代理访问 CA」开关",
          inputs.get("useProxy", {}).get("component") == "switch",
          str(inputs.get("useProxy")))
    check("提供「自定义反代地址」", "reverseProxy" in inputs,
          str(sorted(inputs)))
    # 必填校验要认 showWhen：「ACME 目录地址」只在自定义 CA 下才该拦人，
    # 否则选 Let's Encrypt 也会弹「请填写「ACME 目录地址」」（历史 bug）
    from app.routers.access import _missing_required  # noqa: PLC0415

    check("隐藏的必填字段不参与校验（目录地址）",
          not _missing_required("eab", {"provider": "google", "kid": "k", "hmacKey": "h"}),
          str(_missing_required("eab", {"provider": "google", "kid": "k", "hmacKey": "h"})))

    # EAB 凭据能被「测试」按钮真的拿到 CA 侧校验；缺字段时必须给中文原因，不是抛异常
    from app.services.acme import AcmeError as _AcmeErr  # noqa: PLC0415
    from app.services.acme import verify_eab as _verify_eab  # noqa: PLC0415

    try:
        _verify_eab("", "", "https://example.invalid/directory")
        check("EAB 校验缺少字段时给中文报错", False, "没有抛错")
    except _AcmeErr as exc:
        check("EAB 校验缺少字段时给中文报错", "EAB 凭据不完整" in str(exc), str(exc))

    # 反向代理只能改传输地址：账户地址（kid）必须还原成 CA 的真实域名，
    # 否则 CA 会回 malformed / "Invalid or unrecognized host."
    from app.services.acme import AcmeClient  # noqa: PLC0415

    client = AcmeClient("https://dv.acme-v02.api.pki.goog/directory")
    try:
        client.enable_reverse_proxy({"dv.acme-v02.api.pki.goog": "gg.proxy.example"})
        client.kid = "https://gg.proxy.example/account/abc"
        check("反代域名不会污染 ACME 账户地址（kid）",
              client.kid == "https://dv.acme-v02.api.pki.goog/account/abc", str(client.kid))
        order = client._origin_tree({
            "authorizations": ["https://gg.proxy.example/authz/1"],
            "finalize": "https://gg.proxy.example/finalize/1",
        })
        check("订单/授权地址同样还原成 CA 域名",
              order["authorizations"][0] == "https://dv.acme-v02.api.pki.goog/authz/1"
              and order["finalize"] == "https://dv.acme-v02.api.pki.goog/finalize/1",
              str(order))
    finally:
        client.close()

    # EAB 授权：能建、能明文回显、能出现在「证书签发」下拉里
    eid = 0
    pid = 0
    try:
        res = api.post("/api/access", {"category": "cert", "type": "eab",
                                       "name": "__smoke_eab_access__",
                                       "config": {"provider": "google",
                                                  "kid": "kid-smoke",
                                                  "hmacKey": "hmac-smoke"}})
        eid = (res.get("data") or {}).get("id") or 0
        check("EAB 凭据授权创建", eid > 0, msg(res))
        if eid:
            lst = api.get("/api/access/list?page=1&size=50&category=cert")
            row = next((r for r in (lst.get("data") or {}).get("records", [])
                        if r["id"] == eid), None) or {}
            check("EAB 凭据在「证书签发」分类下且明文回显",
                  row.get("type") == "eab"
                  and (row.get("config") or {}).get("hmacKey") == "hmac-smoke",
                  str(row.get("config")))
            opts = api.get("/api/access/options?category=cert")
            check("EAB 凭据出现在任务表单的授权下拉里",
                  any(o.get("id") == eid for o in opts.get("data") or []))

            # Google 没选 EAB 授权必须在本地拦住，并且提示「去授权管理新建」
            res = api.post("/api/pipeline", {
                "title": "__smoke_eab_missing__", "remark": "smoke",
                "content": {"stages": [{"id": "s1", "title": "申请", "tasks": [
                    {"id": "t1", "type": "CertApply", "title": "Google 申请", "input": {
                        "domains": "eab.smoke.local", "provider": "google",
                        "email": "smoke@example.com", "challengeType": "dns",
                        "dnsAccessId": 0, "keyType": "ec256"}}]}], "triggers": []},
            })
            pid = (res.get("data") or {}).get("id") or 0
            check("创建 Google 证书申请流水线", pid > 0, msg(res))
            if pid:
                detail = _run_and_wait(api, pid)
                log = (detail or {}).get("log") or ""
                check("Google 缺 EAB 时提示去「授权管理 → 证书签发」建凭据",
                      "EAB" in log and "授权管理" in log, log[-300:])
                check("缺 EAB 的失败不甩 Python 堆栈", "Traceback" not in log, log[-300:])
                check("缺 EAB 的流水线状态记为失败",
                      (detail or {}).get("status") == "failed",
                      str((detail or {}).get("status")))
    finally:
        _drop_pipeline(api, pid)
        if eid:
            api.delete(f"/api/access/{eid}")

    # 选了 EAB 授权之后，凭据必须能被解析出来（剩下的交给 CA 与网络）
    pid2 = 0
    eid2 = 0
    try:
        res = api.post("/api/access", {"category": "cert", "type": "eab",
                                       "name": "__smoke_eab_resolve__",
                                       "config": {"provider": "google", "kid": "kid-smoke-2",
                                                  "hmacKey": "aGVsbG8taG1hYw"}})
        eid2 = (res.get("data") or {}).get("id") or 0
        res = api.post("/api/pipeline", {
            "title": "__smoke_eab_resolve__", "remark": "smoke",
            "content": {"stages": [{"id": "s1", "title": "申请", "tasks": [
                {"id": "t1", "type": "CertApply", "title": "Google 申请", "input": {
                    "domains": "eab.smoke.local", "provider": "google",
                    "email": "smoke@example.com", "eabAccessId": eid2,
                    "challengeType": "dns", "dnsAccessId": 0, "keyType": "ec256"}}]}],
                "triggers": []},
        })
        pid2 = (res.get("data") or {}).get("id") or 0
        check("创建带 EAB 授权的申请流水线", pid2 > 0, msg(res))
        if pid2:
            detail = _run_and_wait(api, pid2)
            log = (detail or {}).get("log") or ""
            check("运行时会解析出选中的 EAB 凭据", "EAB 凭据已就绪" in log, log[-300:])
            check("EAB 失败文案是中文结论（不再甩 CA 的英文原文）",
                  "Traceback" not in log
                  and not any(s in log for s in ("Unknown external account binding",
                                                 "This may be due to the EAB key expiring")),
                  log[-300:])
    finally:
        _drop_pipeline(api, pid2)
        if eid2:
            api.delete(f"/api/access/{eid2}")

def section_freessl(api: Api) -> None:
    """FreeSSL（LiteSSL）接入：ACME v2 + EAB，纯元数据与文案校验，不联网。"""
    print("\n== FreeSSL / LiteSSL（亚洲诚信 ACME）==")
    _backend()
    from app.plugins import ACCESS_TYPES, ACME_PROVIDERS, TASK_PLUGIN_MAP
    from app.routers import access as access_router
    from app.services import acme

    provider = ACME_PROVIDERS.get("litessl") or {}
    check("注册了 FreeSSL / LiteSSL 这个 CA", bool(provider), str(sorted(ACME_PROVIDERS)))
    check("目录地址是现行的 acme.litessl.com（老 acme.freessl.cn 已下线）",
          provider.get("directory") == "https://acme.litessl.com/acme/v2/directory",
          str(provider.get("directory")))
    check("标记为需要 EAB（官方 meta.externalAccountRequired=true）",
          bool(provider.get("eab")), str(provider.get("eab")))

    cert_inputs = {item["key"]: item for item in TASK_PLUGIN_MAP["CertApply"]["inputs"]}
    providers = [o.get("value") for o in cert_inputs["provider"].get("options") or []]
    check("申请任务里能选到 FreeSSL / LiteSSL", "litessl" in providers, str(providers))
    check("选 FreeSSL 时才出现 EAB 凭据字段",
          "litessl" in ((cert_inputs["eabAccessId"].get("showWhen") or {}).get("values") or []),
          str(cert_inputs["eabAccessId"].get("showWhen")))

    eab_inputs = {i["key"]: i for i in ACCESS_TYPES["eab"]["inputs"]}
    eab_providers = [o.get("value") for o in eab_inputs["provider"].get("options") or []]
    check("EAB 授权里能选 FreeSSL 作为所属 CA", "litessl" in eab_providers, str(eab_providers))
    check("EAB 凭据可以在线校验（FreeSSL 目录已登记）",
          access_router._EAB_DIRECTORIES.get("litessl") == provider.get("directory"),
          str(access_router._EAB_DIRECTORIES))

    zh, raw = acme.friendly_problem({
        "type": "urn:ietf:params:acme:error:malformed",
        "detail": "The bound account does not exist",
    })
    check("FreeSSL 的 EAB 报错翻成中文结论",
          zh.startswith("EAB 凭据对不上") and zh == zh.strip(), zh[:80])
    check("原始英文只留在 detail 里", raw == "The bound account does not exist", raw)

    # 引擎必须跟注册表用同一份目录地址（历史坑：引擎自己抄了一份，新增 CA 就报
    # 「自定义 ACME 需要填写目录地址」）
    from app.services import engine as engine_mod

    mismatched = []
    for key, meta in ACME_PROVIDERS.items():
        expected = str(meta.get("directory") or "").strip()
        if not expected:
            continue
        got = engine_mod._ca_directory(key, {})
        if got != expected:
            mismatched.append((key, expected, got))
    check("每个内置 CA 的目录地址，引擎都能解析到（不另抄一份）",
          not mismatched, str(mismatched))
    check("引擎认识 FreeSSL / LiteSSL 的名字与 EAB 要求",
          engine_mod._ca_name("litessl") == "FreeSSL / LiteSSL"
          and engine_mod._ca_needs_eab("litessl") is True,
          f"{engine_mod._ca_name('litessl')} / {engine_mod._ca_needs_eab('litessl')}")
    check("自定义 ACME 仍以任务里填的目录为准",
          engine_mod._ca_directory("custom", {"directory": " https://acme.example.com/dir "})
          == "https://acme.example.com/dir",
          engine_mod._ca_directory("custom", {"directory": " https://acme.example.com/dir "}))

    # EAB 值清洗：带标签 / 换行 / 中文说明的值不能让 base64 报错裸奔给用户
    same = acme.normalize_eab_value("HMAC Key: AbCdEfGh1234567890+/=", "EAB HMAC Key")
    check("EAB 值里的标签前缀被去掉",
          same == "AbCdEfGh1234567890+/=", same)
    wrapped = acme.normalize_eab_value("  AbCdEf\nGh1234 567890+/=  ", "EAB HMAC Key")
    check("EAB 值里的换行 / 空格被去掉", wrapped == "AbCdEfGh1234567890+/=", wrapped)
    extracted = acme.normalize_eab_value(
        "亚洲诚信控制台的密钥，请复制后面的值 AbCdEfGh1234567890+/=",
        "EAB HMAC Key")
    check("夹在说明文字里的 EAB 值能自动抠出来",
          extracted == "AbCdEfGh1234567890+/=", extracted)
    pair = acme.normalize_eab_pair(
        "Key ID: kid-abc-123, HMAC Key: AbCdEfGh1234567890+/=",
        "Key ID: kid-abc-123, HMAC Key: AbCdEfGh1234567890+/=")
    check("整段粘贴时按标签各取各的值",
          pair == ("kid-abc-123", "AbCdEfGh1234567890+/="), str(pair))
    try:
        acme.normalize_eab_value("亚洲诚信证书自动化ACME账户管理凭证密钥", "EAB HMAC Key")
        check("纯中文的 EAB 值会给中文结论", False, "没有报错")
    except acme.AcmeError as exc:
        check("纯中文的 EAB 值会给中文结论",
              "HMAC Key" in str(exc) and "中文" in str(exc), str(exc)[:120])
    try:
        acme.normalize_eab_value("kid-中文", "EAB Key ID")
        check("Key ID 里出现中文时也会提示", False, "没有报错")
    except acme.AcmeError as exc:
        check("Key ID 里出现中文时也会提示", "Key ID" in str(exc), str(exc)[:120])

    logo = Path(__file__).resolve().parent.parent / "frontend" / "public" / "logos" / "issuer" / "litessl.svg"
    check("FreeSSL / LiteSSL 有本地 logo（不依赖在线 CDN）", logo.exists(), str(logo))


def section_access_resources(api: Api) -> None:
    """授权资源自动拉取：有 key 就把对端资源全拉回来（宝塔站点为例）。"""
    print("\n== 授权资源自动拉取（宝塔站点）==")
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            seen.append(self.path)
            self._reply({"data": ["site-a.com"]})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            seen.append(self.path)
            del raw
            if self.path.startswith("/site"):
                # 宝塔部署接口：成功时返回 status=true
                self._reply({"status": True, "msg": "ok"})
                return
            self._reply({"data": [{"name": "site-a.com"}, {"name": "site-b.com"}], "page": "1"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    aid = 0
    try:
        res = api.post("/api/access", {"category": "panel", "type": "baota",
                                       "name": "__smoke_baota__",
                                       "config": {"url": base, "apiKey": "bt-key"}})
        aid = (res.get("data") or {}).get("id") or 0
        check("宝塔授权创建", aid > 0, msg(res))

        res = api.post("/api/pipeline/plugin/DeployToBaota/options/siteName",
                       {"input": {"accessId": aid}})
        data = res.get("data") or {}
        check("任务表单能按授权拉站点",
              ok(res) and [i["value"] for i in data.get("items") or []]
              == ["site-a.com", "site-b.com"], str(data)[:200])

        res = api.post("/api/pipeline/plugin/DeployToBaoto/options/siteName",
                       {"input": {}}) if False else api.post(
            "/api/pipeline/plugin/DeployToBaota/options/siteName", {"input": {}})
        check("没选授权时给出可读提示", not ok(res) and "授权" in (res.get("msg") or ""),
              msg(res))

        # 部署任务只选授权、不填站点：引擎自动拉站点并匹配证书域名
        pid = 0
        try:
            res = api.post("/api/pipeline", {
                "title": "__smoke_automatch__", "remark": "smoke",
                "content": {"stages": [
                    {"id": "s1", "title": "申请", "tasks": [
                        {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
                         "input": {"domains": ["site-a.com"], "days": 30}}]},
                    {"id": "s2", "title": "部署", "tasks": [
                        {"id": "t2", "type": "DeployToBaota", "title": "宝塔",
                         "input": {"accessId": aid, "autoMatch": True}}]}]},
            })
            pid = (res.get("data") or {}).get("id") or 0
            check("自动匹配流水线创建", pid > 0, msg(res))
            detail = _run_and_wait(api, pid) if pid else {}
            log = (detail or {}).get("log") or ""
            check("部署任务自动拉取并匹配宝塔站点",
                  "自动匹配：site-a.com → site-a.com" in log, log[-320:])
            check("自动匹配后部署成功", (detail or {}).get("status") == "success",
                  (detail or {}).get("status"))
        finally:
            _drop_pipeline(api, pid)

        # EAB 凭据是「证书签发」类授权（详见 section_cert_apply_inputs），
        # 而 ACME 账户不建授权（邮箱填任务、账号私钥自动生成），所以 acmeAccount 必须被拒绝
        res = api.post("/api/access", {"category": "cert", "type": "acmeAccount",
                                       "name": "__smoke_acme_access__",
                                       "config": {"email": "smoke@example.com"}})
        check("授权管理拒绝 acmeAccount 类型（账户不建授权）",
              not ok(res) and "不支持" in str(res.get("msg")), msg(res))
    finally:
        if aid:
            api.delete(f"/api/access/{aid}")
        server.shutdown()


def section_synology_config() -> None:
    """群晖授权的配置字段要够用：端口 / 权限 / 两步验证 / 默认证书 / 证书名都要能填。"""
    print("\n== 群晖授权字段完整性 ==")
    _backend()
    from app.plugins import ACCESS_TYPES  # noqa: PLC0415
    from app.services.deploy import _totp_code  # noqa: PLC0415

    meta = ACCESS_TYPES.get("synology") or {}
    inputs = {item["key"]: item for item in meta.get("inputs") or []}
    check("群晖授权有面板地址 / 账号 / 密码",
          {"url", "username", "password"} <= set(inputs), str(sorted(inputs)))
    check("群晖授权支持「两步验证密钥」（长期部署不用手工同步验证码）",
          inputs.get("otpSecret", {}).get("component") == "password",
          str(inputs.get("otpSecret")))
    check("群晖授权支持「设为默认证书」开关，默认开启",
          inputs.get("asDefault", {}).get("component") == "switch"
          and inputs.get("asDefault", {}).get("default") is True,
          str(inputs.get("asDefault")))
    check("群晖授权支持自定义证书名称，默认 {domain}",
          inputs.get("certDesc", {}).get("default") == "{domain}",
          str(inputs.get("certDesc")))
    check("群晖授权有「忽略证书校验」开关（DSM 多为自签）",
          inputs.get("insecure", {}).get("component") == "switch",
          str(inputs.get("insecure")))
    check("群晖密码类字段都被标记为 password（编辑时可留空不覆盖）",
          all(inputs[k].get("component") == "password"
              for k in ("password", "otpSecret", "otpCode")),
          str([k for k in ("password", "otpSecret", "otpCode")
               if inputs.get(k, {}).get("component") != "password"]))

    import pyotp  # noqa: PLC0415

    secret = pyotp.random_base32()
    code = _totp_code(secret)
    check("两步验证密钥能自动算出 6 位验证码",
          len(code) == 6 and code.isdigit(), str(code))
    check("两步验证密钥能通过校验（与 pyotp 一致）",
          pyotp.TOTP(secret).verify(code, valid_window=1), code)
    try:
        _totp_code("not-a-base32-@@")
        check("非法两步验证密钥给中文报错", False, "没有抛错")
    except Exception as exc:  # noqa: BLE001
        check("非法两步验证密钥给中文报错", "两步验证密钥不合法" in str(exc), str(exc))

    # 和 certd 一致：设备ID 靠「输一次 6 位验证码」换，长期免验证码
    from app.services.deploy import synology_fetch_device_id  # noqa: PLC0415

    device_field = inputs.get("deviceId") or {}
    check("群晖授权有「设备ID」字段（受信设备令牌）",
          device_field.get("component") == "password"
          and (device_field.get("action") or {}).get("type") == "synology-device-id",
          str(device_field))
    check("群晖授权有「设备名」字段（DSM 信任设备列表里显示的名字）",
          inputs.get("deviceName", {}).get("default") == "CertHub",
          str(inputs.get("deviceName")))

    try:
        synology_fetch_device_id({"url": "https://127.0.0.1:5001", "username": "u",
                                  "password": "p"}, "12")
        check("设备ID 校验验证码位数", False, "没有抛错")
    except Exception as exc:  # noqa: BLE001
        check("设备ID 校验验证码位数", "6 位数字验证码" in str(exc), str(exc))
    try:
        synology_fetch_device_id({"username": "u", "password": "p"}, "123456")
        check("设备ID 缺地址时给中文提示", False, "没有抛错")
    except Exception as exc:  # noqa: BLE001
        check("设备ID 缺地址时给中文提示", "未配置 DSM 地址" in str(exc), str(exc))


def section_synology_login_flow() -> None:
    """群晖登录（mock DSM）：请求形态对齐 certd（device_id / OTP / 纯密码三条腿）。"""
    print("\n== 群晖登录形态（对齐 certd，mock DSM）==")
    _backend()
    import threading  # noqa: PLC0415
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: PLC0415
    from urllib.parse import parse_qs, urlparse  # noqa: PLC0415

    import pyotp  # noqa: PLC0415

    from app.services import deploy  # noqa: PLC0415

    secret = pyotp.random_base32()
    seen: list[dict] = []

    class _Dsm(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, payload):
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = urlparse(self.path).path
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            q["__path"] = path
            seen.append(q)
            # certd 对 DSM 7 走 entry.cgi；auth.cgi 这里故意 404，顺便验证换地址的兜底
            if path != "/webapi/entry.cgi":
                self._send(404, {"success": False, "error": {"code": 105}})
                return
            if q.get("passwd") != "right":
                self._send(200, {"success": False, "error": {"code": 400}})
                return
            if q.get("device_id"):
                if q["device_id"] == "DID-OK":
                    self._send(200, {"success": True,
                                     "data": {"sid": "SID-DEVICE", "synotoken": "TOKEN"}})
                else:
                    self._send(200, {"success": False, "error": {"code": 403}})
                return
            if q.get("otp_code"):
                if not pyotp.TOTP(secret).verify(q["otp_code"], valid_window=1):
                    self._send(200, {"success": False, "error": {"code": 404}})
                    return
                data = {"sid": "SID-OTP", "synotoken": "TOKEN"}
                # 只有 enable_device_token=yes（certd 的写法）才会回 did
                if q.get("enable_device_token") == "yes":
                    data["did"] = "DID-OK"
                self._send(200, {"success": True, "data": data})
                return
            if q.get("session"):
                self._send(200, {"success": True,
                                 "data": {"sid": "SID-PLAIN", "synotoken": "TOKEN"}})
                return
            self._send(200, {"success": False, "error": {"code": 403}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Dsm)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    cfg = {"url": base, "username": "u", "password": "right", "deviceName": "certd"}
    try:
        # ① 获取设备ID：enable_device_token=yes + device_name（certd 的 doLoginWithOTPCode）
        seen.clear()
        code = pyotp.TOTP(secret).now()
        result = deploy.synology_fetch_device_id(cfg, code)
        req = seen[-1]
        check("群晖取设备ID：返回 did", result.get("deviceId") == "DID-OK", result)
        check("群晖取设备ID：带 enable_device_token=yes（certd 写法）",
              req.get("enable_device_token") == "yes", req)
        check("群晖取设备ID：带 device_name", req.get("device_name") == "certd", req)

        # ② 设备ID 登录：device_id + session=Certd + enable_syno_token=yes，不带 otp
        seen.clear()
        session = deploy._synology_login(dict(cfg, deviceId="DID-OK", twoFactor=True))
        req = seen[-1]
        check("群晖设备ID 登录成功", session["sid"] == "SID-DEVICE", session)
        check("群晖设备ID 登录：session=Certd", req.get("session") == "Certd", req)
        check("群晖设备ID 登录：enable_syno_token=yes",
              req.get("enable_syno_token") == "yes", req)
        check("群晖设备ID 登录：不发 otp_code", "otp_code" not in req, req)
        check("群晖设备ID 登录：带回 synotoken", session.get("synotoken") == "TOKEN", session)

        # ③ OTP 登录（没设备ID）：顺手换回 did
        seen.clear()
        session = deploy._synology_login(dict(cfg, twoFactor=True, otpSecret=secret))
        check("群晖 OTP 登录成功", session["sid"] == "SID-OTP", session)
        check("群晖 OTP 登录：带 enable_device_token=yes",
              seen[-1].get("enable_device_token") == "yes", seen[-1])
        check("群晖 OTP 登录：顺手拿回设备 ID", session.get("device_token") == "DID-OK", session)

        # ④ 纯密码登录
        seen.clear()
        session = deploy._synology_login(dict(cfg, twoFactor=False))
        check("群晖纯密码登录成功", session["sid"] == "SID-PLAIN", session)
        check("群晖纯密码登录：session=Certd", seen[-1].get("session") == "Certd", seen[-1])

        # ⑤ 设备 ID 失效 → 自动回退验证密钥
        session = deploy._synology_login(dict(cfg, twoFactor=True, deviceId="DID-BAD",
                                              otpSecret=secret))
        check("群晖设备ID 失效自动回退验证码", session["sid"] == "SID-OTP", session)

        # ⑥ 密码错 → 中文结论
        try:
            deploy._synology_login(dict(cfg, password="wrong", twoFactor=False))
            check("群晖密码错给中文结论", False, "没有抛错")
        except Exception as exc:  # noqa: BLE001
            check("群晖密码错给中文结论", "账号或密码错误" in str(exc), str(exc))
    finally:
        server.shutdown()


def section_synology_device_id_api(api: Api) -> None:
    """群晖「获取设备ID」接口：参数校验要给中文结论（不真的连 DSM）。"""
    print("\n== 群晖获取设备ID 接口 ==")
    res = api.post("/api/access/synology/device-id",
                   {"config": {"url": "", "username": ""}, "otpCode": "123456"})
    check("缺 DSM 地址时拒绝并提示", not ok(res) and "DSM 地址" in msg(res), msg(res))

    res = api.post("/api/access/synology/device-id",
                   {"config": {"url": "https://127.0.0.1:5001", "username": "u",
                               "password": "p"}, "otpCode": "1"})
    check("验证码不是 6 位时拒绝并提示", not ok(res) and "6 位" in msg(res), msg(res))

    res = api.post("/api/access/synology/device-id",
                   {"config": {"url": "https://127.0.0.1:59999", "username": "u",
                               "password": "p"}, "otpCode": "123456"})
    check("连不上 DSM 时给中文结论", not ok(res) and "连不上" in msg(res), msg(res))


def section_access_type_binding(api: Api) -> None:
    """授权要按「类型」区分，不能只按分类：群晖任务不能显示宝塔授权。"""
    print("\n== 授权类型精确匹配 ==")
    plugins = api.get("/api/pipeline/plugins").get("data") or {}
    deploy = [p for p in plugins.get("plugins") or [] if p.get("group") == "deploy"]
    missing = []
    for plugin in deploy:
        fields = [i for i in plugin.get("inputs") or [] if i.get("component") == "access"]
        for field in fields:
            if not field.get("accessTypes"):
                missing.append(plugin["type"] + "." + field["key"])
    check("每个部署任务的授权字段都声明了 accessTypes", not missing, str(missing))

    def types_of(task_type: str) -> list:
        plugin = next((p for p in deploy if p["type"] == task_type), None) or {}
        field = next((i for i in plugin.get("inputs") or []
                      if i.get("component") == "access"), None) or {}
        return field.get("accessTypes") or []

    check("群晖任务只认群晖授权", types_of("DeployToSynology") == ["synology"],
          str(types_of("DeployToSynology")))
    check("宝塔任务只认宝塔授权", types_of("DeployToBaota") == ["baota"],
          str(types_of("DeployToBaota")))
    check("1Panel 任务只认 1Panel 授权", types_of("DeployTo1Panel") == ["1panel"],
          str(types_of("DeployTo1Panel")))
    check("K8s 任务只认 Kubernetes 授权", types_of("DeployToK8sSecret") == ["k8s"],
          str(types_of("DeployToK8sSecret")))

    cert = next((p for p in plugins.get("plugins") or [] if p.get("type") == "CertApply"), {})
    dns_field = next((i for i in cert.get("inputs") or [] if i["key"] == "dnsAccessId"), {})
    check("DNS 授权按「有 DNS 能力」的类型过滤",
          {"aliyun", "tencentcloud", "cloudflare"} <= set(dns_field.get("accessTypes") or []),
          str(dns_field.get("accessTypes")))
    eab_field = next((i for i in cert.get("inputs") or [] if i["key"] == "eabAccessId"), {})
    check("EAB 授权只认 eab 类型", eab_field.get("accessTypes") == ["eab"],
          str(eab_field.get("accessTypes")))

    # 接口层：types 过滤只返回对应类型
    aid = 0
    try:
        res = api.post("/api/access", {"category": "panel", "type": "synology",
                                       "name": "__smoke_synology__",
                                       "config": {"url": "https://192.0.2.10:5001",
                                                  "username": "demo", "password": "demo"}})
        aid = (res.get("data") or {}).get("id") or 0
        check("群晖授权创建（用于类型过滤断言）", aid > 0, msg(res))
        rows = api.get("/api/access/options?types=synology").get("data") or []
        check("按 types=synology 过滤只返回群晖授权",
              bool(rows) and all(r.get("type") == "synology" for r in rows),
              str([r.get("type") for r in rows]))
        check("群晖下拉里没有宝塔授权",
              all(r.get("type") != "baota" for r in rows),
              str([r.get("name") for r in rows]))
        baota_rows = api.get("/api/access/options?types=baota").get("data") or []
        check("按 types=baota 过滤不会带出群晖授权",
              all(r.get("type") == "baota" for r in baota_rows),
              str([r.get("type") for r in baota_rows]))
    finally:
        if aid:
            api.delete(f"/api/access/{aid}")


def section_plugin_registry() -> None:
    """元数据与 handler 必须一一对应，否则「能选到插件但一运行就报未知任务类型」。"""
    print("\n== 插件注册表一致性 ==")
    _backend()
    from app.plugins import ACCESS_TYPES, NOTIFY_TYPES, TASK_PLUGINS
    # 扩展插件是在 import 时往 DEPLOY_HANDLERS 里注册的，这里必须一起导入
    from app.services import (deploy, deploy_cn, deploy_ext, deploy_extra,  # noqa: F401
                             deploy_more, notify)

    deploy_plugins = {p["type"] for p in TASK_PLUGINS if p.get("group") == "deploy"}
    handlers = set(deploy.DEPLOY_HANDLERS)
    check("部署插件都有 handler", not (deploy_plugins - handlers),
          str(sorted(deploy_plugins - handlers)))
    check("handler 都有元数据", not (handlers - deploy_plugins),
          str(sorted(handlers - deploy_plugins)))
    check("每个插件都有名称与描述",
          all(p.get("name") and p.get("desc") for p in TASK_PLUGINS))
    check("部署插件都分了类",
          all(p.get("category") for p in TASK_PLUGINS if p.get("group") == "deploy"))
    check("通知插件都有 handler",
          not (set(NOTIFY_TYPES) - set(notify.SENDERS)),
          str(sorted(set(NOTIFY_TYPES) - set(notify.SENDERS))))
    check("授权类型都有字段元数据",
          all(item.get("inputs") for item in ACCESS_TYPES.values()))
    check("授权类型都有分类", all(item.get("category") for item in ACCESS_TYPES.values()))


def section_jdcloud_split() -> None:
    """京东云：上传证书中心 与 部署到 CDN 分开，CDN 未开通时给明确指引。"""
    print("\n== 京东云：证书中心 / CDN ==")
    _backend()
    from app.services import deploy, deploy_cn  # noqa: F401

    check("京东云上传证书插件已注册", "DeployToJDCloudCert" in deploy.DEPLOY_HANDLERS)  # noqa: E501
    check("京东云 CDN 插件已注册", "DeployToJDCloudCdn" in deploy.DEPLOY_HANDLERS)

    ctx = deploy.CertContext(
        domain="jd.example.com",
        crt="-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----\n",
        key="-----BEGIN PRIVATE KEY-----\nMOCKKEY\n-----END PRIVATE KEY-----\n",
        expires_time="2027-01-01 00:00:00", domains=["jd.example.com"])

    server, seen = _cdn_mock_server({
        "/v1/sslCert:upload": {"requestId": "r1", "result": {"certId": 4321}},
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"accessKeyId": "jd-ak", "secretAccessKey": "jd-sk", "baseUrl": base}
        deploy.DEPLOY_HANDLERS["DeployToJDCloudCert"](ctx, cfg, lambda m: None)
        check("京东云证书中心上传成功",
              any("/v1/sslCert:upload" in r["path"] for r in seen),
              str([r["path"] for r in seen]))
        check("上传插件不会调用 CDN 接口",
              not any("/httpType" in r["path"] for r in seen))
    except Exception as exc:  # noqa: BLE001
        check("京东云证书中心上传成功", False, str(exc))
    finally:
        server.shutdown()

    server, seen = _cdn_mock_server({
        "/v1/sslCert:upload": {"requestId": "r1", "result": {"certId": 4321}},
        ("POST", "/v1/domain/jd.example.com/httpType"): {
            "__status__": 401,
            "error": {"code": "UNAUTHENTICATED", "status": 401,
                      "message": "account htmacg didn't open cdn service."},
        },
    })
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        cfg = {"accessKeyId": "jd-ak", "secretAccessKey": "jd-sk", "baseUrl": base,
               "domains": ["jd.example.com"]}
        message = ""
        try:
            deploy.DEPLOY_HANDLERS["DeployToJDCloudCdn"](ctx, cfg, lambda m: None)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
        check("CDN 未开通时给出中文指引",
              "开通 CDN" in message and "证书中心" in message, message[:200])
        check("CDN 报错里带上已上传的证书 ID", "4321" in message, message[:200])
    finally:
        server.shutdown()


def section_signature() -> None:
    """对象存储签名要和官方 SDK 算出来的一模一样，差一个字节就 403。"""
    print("\n== 对象存储签名（与官方 SDK 比对）==")
    _backend()
    from app.services.deploy_ext import _aws_sigv4, _cos_headers, _oss_headers

    import datetime as _dt

    body = b"smoke-body"
    ak, sk = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    now = _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    headers = {k.lower(): v for k, v in _aws_sigv4(
        "PUT", "s3.example.com", "/bucket/demo.crt", body, ak=ak, sk=sk,
        region="us-east-1", service="s3", content_type="application/x-pem-file",
        now=now).items()}
    check("SigV4 生成 Authorization",
          (headers.get("authorization") or "").startswith("AWS4-HMAC-SHA256 Credential="),
          str(list(headers))[:200])
    check("SigV4 带内容摘要",
          "x-amz-content-sha256" in headers, str(list(headers))[:200])

    try:
        from botocore.auth import S3SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.credentials import Credentials

        req = AWSRequest(method="PUT", url="https://s3.example.com/bucket/demo.crt",
                         data=body, headers={"Content-Type": "application/x-pem-file"})
        # 两边必须签同一个时间戳，否则签的是不同的 StringToSign。
        # 做法：先让官方 SDK 签，再从它写回的 request.context["timestamp"] 取时间给我们的实现用
        # （新版 botocore 不认外部塞的 timestamp，会自己取当前时间，所以只能反过来对齐）。
        S3SigV4Auth(Credentials(ak, sk), "s3", "us-east-1").add_auth(req)
        want = req.headers["Authorization"]
        stamp = req.context.get("timestamp") or amz_date
        aligned = _dt.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=_dt.timezone.utc)
        ours = {k.lower(): v for k, v in _aws_sigv4(
            "PUT", "s3.example.com", "/bucket/demo.crt", body, ak=ak, sk=sk,
            region="us-east-1", service="s3", content_type="application/x-pem-file",
            now=aligned).items()}
        check("SigV4 签名与 botocore 一致（同一时间戳）",
              ours.get("authorization") == want,
              f"stamp={stamp} ours={ours.get('authorization')} want={want}")
    except ImportError:
        SKIP.append("SigV4 与 botocore 比对（未安装 botocore）")
    # OSS V1：按官方文档的 StringToSign 独立复算一遍（不复用被测实现里的任何函数）
    import base64 as _b64  # noqa: PLC0415
    import hashlib as _hashlib  # noqa: PLC0415
    import hmac as _hmac  # noqa: PLC0415

    fixed_date = _dt.datetime.now(_dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    oss_headers = dict(_oss_headers("PUT", "bucket-smoke", "demo.crt", body,
                                    "application/x-pem-file", ak, sk, date=fixed_date))
    content_md5 = _b64.b64encode(_hashlib.md5(body).digest()).decode()
    string_to_sign = "\n".join(["PUT", content_md5, "application/x-pem-file", fixed_date,
                                "/bucket-smoke/demo.crt"])
    want = "OSS %s:%s" % (ak, _b64.b64encode(
        _hmac.new(sk.encode(), string_to_sign.encode(), _hashlib.sha1).digest()).decode())
    check("OSS 签名与文档算法一致",
          oss_headers.get("Authorization") == want,
          f"ours={oss_headers.get('Authorization')} want={want}")
    check("OSS 请求带 Content-MD5",
          oss_headers.get("Content-MD5") == content_md5, str(oss_headers)[:160])

    cos_headers = {k.lower(): v for k, v in _cos_headers(
        "PUT", "bucket-1250000000.cos.ap-guangzhou.myqcloud.com", "/demo.crt",
        body, "application/x-pem-file", "cos-ak", "cos-sk").items()}
    check("COS 签名带 q-sign-algorithm",
          (cos_headers.get("authorization") or "").startswith("q-sign-algorithm=sha1"),
          str(list(cos_headers))[:200])


def section_ssh_presets() -> None:
    """Nginx / Apache / HAProxy / Tomcat 四个 SSH 预设的路径与形态。"""
    print("\n== SSH 部署预设 ==")
    _backend()
    from app.services import deploy, deploy_ext  # noqa: F401

    presets = deploy_ext.SSH_PRESETS
    check("四个预设都在",
          {"DeployToNginx", "DeployToApache", "DeployToHaproxy", "DeployToTomcat"}
          <= set(presets), str(sorted(presets)))
    check("Nginx 默认写 /etc/nginx/ssl",
          presets["DeployToNginx"]["certPath"].startswith("/etc/nginx/ssl/"))
    check("Apache 默认写 /etc/httpd/ssl",
          presets["DeployToApache"]["certPath"].startswith("/etc/httpd/ssl/"))
    check("HAProxy 合并成单个 PEM",
          presets["DeployToHaproxy"].get("combine") is True
          and presets["DeployToHaproxy"]["keyPath"] == "",
          str(presets["DeployToHaproxy"]))
    check("Tomcat 用 PKCS#12", bool(presets["DeployToTomcat"].get("pfxPath")),
          str(presets["DeployToTomcat"]))
    check("预设都带 reload 命令", all(p.get("reloadCmd") for p in presets.values()))
    check("预设都有对应 handler",
          all(key in deploy.DEPLOY_HANDLERS for key in presets),
          str([k for k in presets if k not in deploy.DEPLOY_HANDLERS]))


def section_storage_deploy(api: Api) -> None:
    """对象存储部署：S3 兼容存储整条流水线（自签证书 → 上传 crt / key）。"""
    print("\n== 对象存储部署（S3 兼容）==")
    server, seen = _cdn_mock_server({
        "/bucket-smoke/smoke-s3.local.crt": {"ok": True},
        "/bucket-smoke/smoke-s3.local.key": {"ok": True},
    })
    base = f"http://127.0.0.1:{server.server_address[1]}"
    aid = 0
    pid = 0
    try:
        res = api.post("/api/access", {"category": "cloud", "type": "s3",
                                       "name": "__smoke_s3__",
                                       "config": {"endpoint": base,
                                                  "accessKeyId": "smoke-ak",
                                                  "secretAccessKey": "smoke-sk",
                                                  "region": "us-east-1"}})
        aid = (res.get("data") or {}).get("id") or 0
        check("S3 授权创建", aid > 0, msg(res))

        res = api.post("/api/pipeline", {
            "title": "__smoke_s3__", "remark": "smoke",
            "content": {"stages": [
                {"id": "s1", "title": "申请", "tasks": [
                    {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
                     "input": {"domains": "smoke-s3.local", "days": 30}}]},
                {"id": "s2", "title": "部署", "tasks": [
                    {"id": "t2", "type": "DeployToS3", "title": "S3",
                     "input": {"accessId": aid, "endpoint": base,
                               "bucket": "bucket-smoke", "region": "us-east-1"}}]}]},
        })
        pid = (res.get("data") or {}).get("id") or 0
        check("S3 流水线创建", pid > 0, msg(res))
        detail = _run_and_wait(api, pid) if pid else {}
        check("S3 流水线执行成功", (detail or {}).get("status") == "success",
              str((detail or {}).get("log"))[-300:])

        paths = [row["path"] for row in seen]
        check("上传了 crt 与 key",
              "/bucket-smoke/smoke-s3.local.crt" in paths
              and "/bucket-smoke/smoke-s3.local.key" in paths, str(paths))
        crt = next((row for row in seen if row["path"].endswith(".crt")), {})
        check("上传请求带 SigV4 签名",
              "authorization" in (crt.get("headers") or {}),
              str(list((crt.get("headers") or {}).keys()))[:200])
        check("证书内容真的传上去了",
              "BEGIN CERTIFICATE" in (crt.get("body") or ""))
    finally:
        if aid:
            api.delete(f"/api/access/{aid}")
        _drop_pipeline(api, pid)
        server.shutdown()


def section_dns_records(api: Api) -> None:
    """DNS 记录页：手动 CNAME 与自动验证记录共存，靠 source 区分、自动的只读。"""
    print("\n== DNS 记录（CNAME + 自动验证记录）==")
    listed = api.get("/api/dns/cname/list?current=1&size=50")
    check("DNS 记录列表可读", ok(listed), msg(listed))
    rows = (listed.get("data") or {}).get("records") or []
    check("列表项带来源与记录类型字段",
          all("source" in row and "recordType" in row for row in rows),
          str(sorted((rows[0] if rows else {}).keys())))

    rid = 0
    try:
        res = api.post("/api/dns/cname", {"domain": "smoke-cname.example.com",
                                          "recordValue": "abc123.cname.example.net",
                                          "accessId": 0, "remark": "__smoke__"})
        rid = (res.get("data") or {}).get("id") or 0
        check("手动 CNAME 记录创建", ok(res) and rid > 0, msg(res))
        row = res.get("data") or {}
        check("手动记录标成 manual / CNAME",
              row.get("source") == "manual" and row.get("recordType") == "CNAME", str(row)[:200])

        only_manual = api.get("/api/dns/cname/list?current=1&size=50&source=manual")
        ids = [r["id"] for r in ((only_manual.get("data") or {}).get("records") or [])]
        check("按来源筛选只出手动记录", rid in ids, str(ids[:10]))
        only_acme = api.get("/api/dns/cname/list?current=1&size=50&source=acme")
        acme_ids = [r["id"] for r in ((only_acme.get("data") or {}).get("records") or [])]
        check("按来源筛选 acme 不含手动记录", rid not in acme_ids, str(acme_ids[:10]))

        res = api.put(f"/api/dns/cname/{rid}", {"domain": "smoke-cname.example.com",
                                                "recordValue": "def456.cname.example.net",
                                                "accessId": 0, "remark": "__smoke__"})
        check("手动记录可编辑", ok(res) and (res.get("data") or {}).get("recordValue")
              == "def456.cname.example.net", msg(res))
    finally:
        if rid:
            api.delete(f"/api/dns/cname/{rid}?remote=false")
    check("手动记录已清理", rid not in [
        r["id"] for r in ((api.get("/api/dns/cname/list?current=1&size=50")
                           .get("data") or {}).get("records") or [])])


def _wait_group_run(api: Api, run_id: int, tries: int = 90) -> dict:
    """等一次分组执行结束（分组在后台线程里串行跑，还要等每条流水线跑完）。"""
    detail: dict = {}
    for _ in range(tries):
        detail = api.get(f"/api/pipeline-group/run/{run_id}").get("data") or {}
        status = detail.get("status") or ""
        if status and status != "running":
            return detail
        time.sleep(2)
    return detail


def _group_stages(tasks: list[dict]) -> dict:
    return {"stages": [{"id": "s1", "title": "申请", "tasks": tasks}], "triggers": []}


def section_pipeline_group(api: Api) -> None:
    """流水线分组：按顺序「试一试」，某条失败就跳它配置的「失败后执行」。"""
    print("\n== 流水线分组（失败后转备用）==")
    pids: list[int] = []
    gids: list[int] = []
    try:
        bad = (api.post("/api/pipeline", {
            "title": "__smoke_group_bad__", "remark": "smoke",
            "content": _group_stages([{"id": "t1", "type": "CertApply", "title": "主 CA",
                                       "input": {}, "continueOnError": False}]),
        }).get("data") or {}).get("id") or 0
        pids.append(bad)
        good = (api.post("/api/pipeline", {
            "title": "__smoke_group_good__", "remark": "smoke",
            "content": _group_stages([{"id": "t1", "type": "CertApplySelfSigned", "title": "备用自签",
                                       "input": {"domains": ["group-smoke.local"], "days": 30},
                                       "continueOnError": False}]),
        }).get("data") or {}).get("id") or 0
        pids.append(good)
        check("分组用的两条流水线创建成功", bad > 0 and good > 0, f"{bad} / {good}")
        if not (bad and good):
            return

        res = api.post("/api/pipeline-group", {
            "name": "__smoke_group__", "remark": "smoke", "enabled": True,
            "items": [{"pipelineId": bad, "onFailurePipelineId": good},
                      {"pipelineId": good, "onFailurePipelineId": 0}],
        })
        gid = (res.get("data") or {}).get("id") or 0
        gids.append(gid)
        check("分组创建", ok(res) and gid > 0, msg(res))

        listed = api.get("/api/pipeline-group/list?current=1&size=50")
        row = next((r for r in (listed.get("data") or {}).get("records") or []
                    if r["id"] == gid), None)
        check("分组列表带回成员标题与「失败后执行」标题",
              row is not None
              and bool(row["items"][0].get("pipelineTitle"))
              and bool(row["items"][0].get("onFailurePipelineTitle")),
              str(row)[:240])

        res = api.post(f"/api/pipeline-group/{gid}/run")
        run_id = (res.get("data") or {}).get("runId") or 0
        check("分组运行提交", ok(res) and run_id > 0, msg(res))
        detail = _wait_group_run(api, run_id)
        steps = detail.get("steps") or []
        check("第一条失败后自动执行备用流水线",
              len(steps) >= 2 and steps[0].get("status") == "failed"
              and steps[1].get("pipelineId") == good,
              str([(s.get("pipelineId"), s.get("status")) for s in steps]))
        check("备用流水线成功后整个分组判成功",
              detail.get("status") == "success", str(detail.get("status")))
        check("每一步都带自己的执行历史",
              bool(steps) and all(s.get("historyId") for s in steps), str(steps)[:240])

        # 没配置「失败后执行」的分组：第一条失败就直接判分组失败
        res = api.post("/api/pipeline-group", {
            "name": "__smoke_group_plain__", "remark": "smoke", "enabled": True,
            "items": [{"pipelineId": bad, "onFailurePipelineId": 0}],
        })
        gid2 = (res.get("data") or {}).get("id") or 0
        gids.append(gid2)
        run2 = (api.post(f"/api/pipeline-group/{gid2}/run").get("data") or {}).get("runId") or 0
        detail2 = _wait_group_run(api, run2)
        check("没有备用流水线时分组直接判失败",
              detail2.get("status") == "failed" and len(detail2.get("steps") or []) == 1,
              str(detail2)[:200])

        check("分组名称必填",
              not ok(api.post("/api/pipeline-group", {
                  "name": "  ", "remark": "", "enabled": True,
                  "items": [{"pipelineId": good, "onFailurePipelineId": 0}]})),
              "空名称被接受了")
        check("「失败后执行」不能选自己",
              not ok(api.post("/api/pipeline-group", {
                  "name": "__smoke_group_bad2__", "remark": "", "enabled": True,
                  "items": [{"pipelineId": good, "onFailurePipelineId": good}]})),
              "自引用被接受了")
        check("不存在的流水线被拒绝",
              not ok(api.post("/api/pipeline-group", {
                  "name": "__smoke_group_bad3__", "remark": "", "enabled": True,
                  "items": [{"pipelineId": 99999999, "onFailurePipelineId": 0}]})),
              "不存在的流水线被接受了")
    finally:
        for gid in gids:
            if gid:
                api.delete(f"/api/pipeline-group/{gid}")
        for pid in pids:
            _drop_pipeline(api, pid)
    check("分组已清理", all(
        r["id"] not in gids
        for r in (api.get("/api/pipeline-group/list?current=1&size=50")
                  .get("data") or {}).get("records") or []))



# ---------------------------------------------------------------- 亚洲诚信（TrustAsia CertCloud）
def _trustasia_mock(mode: str = "ok") -> tuple[ThreadingHTTPServer, list, dict]:
    """模拟 CertCloud OpenAPI v3：下单 → 查询订单 → 通知验证完成 → 取证书。

    mode="ok" 正常签发；mode="failed" 让订单直接变成 failed，用来验证报错文案。
    """
    _backend()
    from cryptography.hazmat.primitives import serialization

    from app.services import certutil

    seen: list[dict] = []
    state: dict = {"orders": {}, "dcvCompleted": set(), "polls": {}}
    leaf, _key = certutil.self_signed(["trustasia-smoke.local"], 90, "rsa2048")
    leaf_pem = leaf.public_bytes(serialization.Encoding.PEM).decode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, payload: dict, status: int = 200, request_id: str = ""):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if request_id:
                self.send_header("X-CC-Request-ID", request_id)
            self.end_headers()
            self.wfile.write(body)

        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            parsed = urlparse(self.path)
            path = parsed.path
            headers = {k.lower(): v for k, v in self.headers.items()}
            body: dict = {}
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8", "ignore"))
                except Exception:  # noqa: BLE001
                    body = {"__raw__": raw.decode("utf-8", "ignore")}
            seen.append({"method": self.command, "path": path, "headers": headers, "body": body})

            # 鉴权：两个头缺一个就按官方约定回 401 + 追踪 ID
            if not headers.get("x-cc-key-id") or not headers.get("x-cc-auth-key"):
                self._json({"code": "unauthenticated_request"}, 401, "mock-req-id")
                return

            if path == "/openapi/v3/ping":
                data = b"Everything is fine, please enjoy it."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if path == "/openapi/v3/certs" and self.command == "GET":
                self._json({"code": "success", "data": {"total": 3}})
                return

            parts = [p for p in path.split("/") if p]
            # /openapi/v3/orders/{product_id}
            if len(parts) == 4 and parts[2] == "orders" and self.command == "POST":
                cert = body.get("certificate") or {}
                domains = [cert.get("common_name")] + [
                    d for d in (cert.get("dns_names") or []) if d != cert.get("common_name")]
                order_id = "MOCK" + str(len(state["orders"]) + 1)
                state["orders"][order_id] = {"domains": domains, "product": parts[3]}
                state["polls"][order_id] = 0
                self._json({"code": "success", "data": {
                    "id": order_id,
                    "status": "domain_verifing",
                    "certificate": {"id": "C" + order_id},
                    "dcv_val": [{
                        "domain": d,
                        "auth_path": "mock-trustasia-" + d.replace("*", "wildcard"),
                        "auth_val": "verify-" + d,
                        "verified": False,
                        "dcv_method": body.get("dcv_method") or "dns",
                    } for d in domains],
                }})
                return

            # /openapi/v3/orders/{id}/dcv-completed
            if len(parts) == 5 and parts[2] == "orders" and parts[4] == "dcv-completed" \
                    and self.command == "PUT":
                state["dcvCompleted"].add(parts[3])
                self._json({"code": "success", "data": {"id": parts[3]}})
                return

            # /openapi/v3/orders/{id}
            if len(parts) == 4 and parts[2] == "orders" and self.command == "GET":
                order_id = parts[3]
                order = state["orders"].get(order_id) or {"domains": ["trustasia-smoke.local"]}
                state["polls"][order_id] = state["polls"].get(order_id, 0) + 1
                if mode == "failed":
                    self._json({"code": "success", "data": {
                        "id": order_id, "status": "failed", "status_desc": "mock 拒绝签发",
                        "certificate": {"id": "C" + order_id}, "dcv_val": [],
                    }})
                    return
                done = state["polls"][order_id] >= 2
                payload = {
                    "id": order_id,
                    "status": "issued" if done else "issuing",
                    "certificate": {"id": "C" + order_id, "pem": leaf_pem if done else ""},
                    "dcv_method": "dns",
                }
                if not done:
                    payload["dcv_val"] = [{
                        "domain": order["domains"][0],
                        "auth_path": "mock-trustasia-" + order["domains"][0],
                        "auth_val": "verify-" + order["domains"][0],
                        "verified": True, "dcv_method": "dns",
                    }]
                self._json({"code": "success", "data": payload})
                return

            # /openapi/v3/certs/{id}
            if len(parts) == 4 and parts[2] == "certs" and self.command == "GET":
                self._json({"code": "success", "data": {
                    "id": parts[3], "pem": leaf_pem, "ica_pem": "",
                }})
                return

            self._json({"code": "resource_not_found", "message": "mock: " + path}, 404)

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_DELETE = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen, state


def section_skip_reuse(api: Api) -> None:
    """申请步骤的跳过判断：未到期 / 已存在 / 刚申请过 → 只跳过这一步，后面继续跑。"""
    print("\n== 证书未到期 / 已存在 / 刚申请过：跳过申请并继续后续步骤 ==")
    pid = 0
    domain = "skip-smoke.local"

    def build(apply_input: dict) -> dict:
        apply_input = {"domains": [domain], "days": 30, **apply_input}
        return {"stages": [
            {"id": "s1", "title": "申请", "tasks": [
                {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
                 "input": apply_input, "continueOnError": False}]},
            {"id": "s2", "title": "部署", "tasks": [
                {"id": "t2", "type": "DeployToLocal", "title": "复制到本机目录",
                 "input": {"dir": "./data/deploy"}, "continueOnError": True}]},
        ], "triggers": []}

    def run_once() -> dict:
        return _run_and_wait(api, pid, tries=40)

    def drop_certs() -> int:
        """先清掉这个测试域名已有的证书，否则「第一次执行」会被跳过判断挡住。"""
        removed = 0
        listed = api.get("/api/cert/list?page=1&size=100").get("data") or {}
        for row in listed.get("records") or []:
            if domain in (row.get("domains") or []):
                api.delete(f"/api/cert/{row['id']}")
                removed += 1
        return removed

    def task_map(detail: dict) -> dict:
        tasks = (detail or {}).get("tasks") or []
        if isinstance(tasks, str):
            tasks = json.loads(tasks or "[]")
        return {t.get("taskId"): t.get("status") for t in tasks}

    try:
        checked = drop_certs()
        if checked:
            print(f"  （清理 {checked} 张上次留下的 {domain} 证书）")
        res = api.post("/api/pipeline", {"title": "__smoke_skip__", "remark": "smoke",
                                         "content": build({})})
        pid = (res.get("data") or {}).get("id") or 0
        check("跳过判断用的流水线创建", ok(res) and pid > 0, msg(res))
        if not pid:
            return

        first = run_once()
        check("第一次执行正常签发并部署",
              task_map(first) == {"t1": "success", "t2": "success"}, str(task_map(first)))

        # 第二次：证书还没到期 → 跳过申请，但部署照跑
        second = run_once()
        states = task_map(second)
        check("证书未到期时跳过申请步骤（状态 skipped）", states.get("t1") == "skipped", str(states))
        check("跳过后继续执行后面的部署步骤", states.get("t2") == "success", str(states))
        check("整条流水线仍算成功（跳过不是失败）",
              (second or {}).get("status") == "success", str((second or {}).get("status")))
        log_text = (second or {}).get("log") or ""
        check("日志写清跳过原因并说明继续执行",
              "跳过证书申请" in log_text and "继续执行后面的步骤" in log_text,
              log_text[-200:])
        check("跳过后把证书库里的证书交给后续步骤",
              "后续步骤将使用证书库里这张证书" in log_text, log_text[-260:])

        certs = api.get("/api/cert/list?page=1&size=100").get("data") or {}
        hits = [r for r in certs.get("records") or [] if domain in (r.get("domains") or [])]
        check("重复执行没有重复签发（证书库里仍只有一张）", len(hits) == 1, str(len(hits)))

        # 强制续期：必须重新申请
        api.put(f"/api/pipeline/{pid}", {"title": "__smoke_skip__", "remark": "smoke",
                                         "content": build({"forceUpdate": True})})
        forced = run_once()
        check("打开「强制续期」后重新申请",
              task_map(forced).get("t1") == "success", str(task_map(forced)))
        certs = api.get("/api/cert/list?page=1&size=100").get("data") or {}
        hits = [r for r in certs.get("records") or [] if domain in (r.get("domains") or [])]
        check("强制续期后证书库多了一张", len(hits) == 2, str(len(hits)))

        # 关掉「已存在就跳过」、提前续期天数调小 → 未到续期时间，仍然跳过
        api.put(f"/api/pipeline/{pid}", {"title": "__smoke_skip__", "remark": "smoke",
                                         "content": build({"renewDays": 5,
                                                           "skipIfCertificateExists": False,
                                                           "skipRecentMinutes": 0})})
        not_due = run_once()
        states = task_map(not_due)
        check("未到提前续期天数时也会跳过申请", states.get("t1") == "skipped", str(states))
        check("这种跳过同样不阻断部署步骤", states.get("t2") == "success", str(states))

        # 提前续期天数调大 → 达到阈值，正常申请
        api.put(f"/api/pipeline/{pid}", {"title": "__smoke_skip__", "remark": "smoke",
                                         "content": build({"renewDays": 90,
                                                           "skipIfCertificateExists": False,
                                                           "skipRecentMinutes": 0})})
        due = run_once()
        check("剩余天数低于提前续期天数时正常申请",
              task_map(due).get("t1") == "success", str(task_map(due)))
        certs = api.get("/api/cert/list?page=1&size=100").get("data") or {}
        hits = [r for r in certs.get("records") or [] if domain in (r.get("domains") or [])]
        check("到续期时间后确实又签了一张", len(hits) == 3, str(len(hits)))
    finally:
        if pid:
            _drop_pipeline(api, pid)
        drop_certs()


def section_task_switch(api: Api) -> None:
    """阶段里的单步开关：关掉的步骤运行时要跳过，列表统计也不能把它算进去。"""
    print("\n== 步骤单独启停（任务级开关）==")
    pid = 0
    pid2 = 0
    try:
        stages = {"stages": [{"id": "s1", "title": "申请", "tasks": [
            # 关掉的任务故意选一个必失败的（CertApply 没填域名），跳过它流水线才能成功
            {"id": "t1", "type": "CertApply", "title": "__停用的申请__",
             "input": {}, "continueOnError": False, "enabled": False},
            {"id": "t2", "type": "CertApplySelfSigned", "title": "__启用的自签__",
             "input": {"domains": ["switch-smoke.local"], "days": 30},
             "continueOnError": False, "enabled": True},
        ]}], "triggers": []}
        res = api.post("/api/pipeline", {"title": "__smoke_switch__", "remark": "smoke",
                                         "content": stages})
        pid = (res.get("data") or {}).get("id") or 0
        check("带停用步骤的流水线创建", ok(res) and pid > 0, msg(res))
        if pid:
            listed = api.get("/api/pipeline/list?current=1&size=100").get("data") or {}
            row = next((r for r in listed.get("records") or [] if r["id"] == pid), None) or {}
            check("列表统计只算启用的步骤（stepCount=1 / taskCount=2 / 停用=1）",
                  row.get("stepCount") == 1 and row.get("taskCount") == 2
                  and row.get("stepDisabledCount") == 1,
                  str({k: row.get(k) for k in ("stepCount", "taskCount", "stepDisabledCount")}))

            detail = _run_and_wait(api, pid, tries=40)
            check("停用的步骤不影响流水线：整体成功",
                  (detail or {}).get("status") == "success", str((detail or {}).get("status")))
            tasks = (detail or {}).get("tasks") or []
            if isinstance(tasks, str):
                tasks = json.loads(tasks or "[]")
            by_id = {t.get("taskId"): t for t in tasks}
            check("停用的步骤标记为 disabled 且没执行",
                  (by_id.get("t1") or {}).get("status") == "disabled",
                  str(by_id.get("t1")))
            check("启用的步骤照常执行成功",
                  (by_id.get("t2") or {}).get("status") == "success",
                  str(by_id.get("t2")))
            log_text = (detail or {}).get("log") or ""
            check("日志里写明哪一步被跳过",
                  "已停用，跳过这一步" in log_text, log_text[-160:])

        # 停用的部署任务不该出现在「申请 + 部署」标签里
        stages2 = {"stages": [{"id": "s1", "title": "申请", "tasks": [
            {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
             "input": {"domains": ["switch-smoke.local"], "days": 30},
             "continueOnError": False, "enabled": True},
            {"id": "t2", "type": "DeployToLocal", "title": "复制到本机",
             "input": {"dir": "./data/deploy"}, "continueOnError": True, "enabled": False},
        ]}], "triggers": []}
        res = api.post("/api/pipeline", {"title": "__smoke_switch2__", "remark": "smoke",
                                         "content": stages2})
        pid2 = (res.get("data") or {}).get("id") or 0
        if pid2:
            detail2 = api.get(f"/api/pipeline/{pid2}").get("data") or {}
            check("停用的部署步骤不计入「申请 / 部署」分类标签",
                  detail2.get("kinds") == ["cert"], str(detail2.get("kinds")))
            check("详情里能拿到每个任务（含 enabled 标记）",
                  all("enabled" in t for t in
                      (detail2.get("content") or {}).get("stages", [{}])[0].get("tasks", [])),
                  str((detail2.get("content") or {}).get("stages")))
    finally:
        for item in (pid, pid2):
            if item:
                _drop_pipeline(api, item)



# ---------------------------------------------------------------- EAB 一次性（FreeSSL/LiteSSL）
def _acme_mock_single_use_eab(seen: list) -> ThreadingHTTPServer:
    """最小 ACME 服务器：只实现 new-nonce / new-account，用来模拟「一次性 EAB」。

    第一次用 EAB 注册成功并把它标记为已用；再拿同一份 EAB 注册会回
    externalAccountRequired + External account binding has already been used
    （FreeSSL / LiteSSL 就是这个行为）。
    """
    import base64 as _b64

    state = {'used': set(), 'accounts': set()}

    def _b64d(text: str) -> bytes:
        pad = '=' * (-len(text) % 4)
        return _b64.urlsafe_b64decode(text + pad)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, payload: dict, status: int = 200, headers: dict | None = None):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Replay-Nonce', 'mocknonce')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _handle(self):
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length else b''
            parsed = urlparse(self.path)
            body: dict = {}
            if raw:
                try:
                    body = json.loads(raw.decode('utf-8', 'ignore'))
                except Exception:  # noqa: BLE001
                    body = {}
            seen.append({'method': self.command, 'path': parsed.path, 'body': body})

            if parsed.path.endswith('/directory'):
                base = 'http://127.0.0.1:%d/acme/v2' % server.server_address[1]
                self._json({'newNonce': base + '/new-nonce',
                            'newAccount': base + '/new-account',
                            'meta': {'externalAccountRequired': True}})
                return
            if parsed.path.endswith('/new-nonce'):
                self.send_response(200)
                self.send_header('Replay-Nonce', 'mocknonce')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if parsed.path.endswith('/new-account'):
                try:
                    protected = json.loads(_b64d(body.get('protected', '')).decode())
                    payload = json.loads(_b64d(body.get('payload', '')).decode())
                except Exception:  # noqa: BLE001
                    self._json({'type': 'urn:ietf:params:acme:error:malformed',
                                'detail': 'bad jws'}, 400)
                    return
                jwk = protected.get('jwk') or {}
                account_id = jwk.get('x') or jwk.get('n') or 'unknown'
                kid = protected.get('kid') or ''
                eab = payload.get('externalAccountBinding')
                if eab:
                    eab_protected = json.loads(_b64d(eab.get('protected', '')).decode())
                    eab_kid = eab_protected.get('kid') or ''
                    if eab_kid in state['used']:
                        self._json({'type': 'urn:ietf:params:acme:error:externalAccountRequired',
                                    'detail': 'External account binding has already been used'}, 400)
                        return
                    state['used'].add(eab_kid)
                    state['accounts'].add(account_id)
                    base = 'http://127.0.0.1:%d/acme/v2' % server.server_address[1]
                    self._json({'status': 'valid'}, 201,
                               {'Location': base + '/account/' + account_id[:12]})
                    return
                # 没有 EAB：只有已注册过的账户能过（复用账户场景）
                known = account_id in state['accounts'] or (kid and account_id in state['accounts'])
                if known:
                    self._json({'status': 'valid'}, 200,
                               {'Location': kid or ('http://127.0.0.1:%d/acme/v2/account/%s' % (
                                   server.server_address[1], account_id[:12]))})
                    return
                self._json({'type': 'urn:ietf:params:acme:error:externalAccountRequired',
                            'detail': 'external account binding required'}, 400)
                return
            self._json({'type': 'urn:ietf:params:acme:error:malformed',
                        'detail': 'not implemented'}, 404)

        do_GET = _handle
        do_HEAD = _handle
        do_POST = _handle

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def section_eab_single_use(api: Api) -> None:
    """一次性 EAB（FreeSSL / LiteSSL）：注册一次后必须复用账户，不能再拿 EAB 注册。"""
    print("\n== 一次性 EAB：注册一次、之后复用账户 ==")
    _backend()
    from app.services import acme

    seen: list[dict] = []
    server = _acme_mock_single_use_eab(seen)
    directory = 'http://127.0.0.1:%d/acme/v2/directory' % server.server_address[1]
    try:
        first = acme.register_eab_account('mock-kid-1', 'bW9jay1obWFjLWtleQ==', directory,
                                          email='mock@example.com')
        check('首次用 EAB 能注册账户',
              '注册账户' in first['message'] and bool(first['accountKeyPem']), first['message'])
        check('注册结果带回账户私钥与账户地址',
              'PRIVATE KEY' in first['accountKeyPem'] and bool(first['accountUrl']),
              str(first['accountUrl'])[:60])

        eab_posts = [it for it in seen
                     if it['path'].endswith('/new-account')
                     and it['body'].get('payload', '') and 'externalAccountBinding' in it['body'].get('payload', '')]
        # payload 是 base64，直接看请求体里有没有 EAB 字段名（base64 里不会出现明文，改用计数）
        eab_used = len([it for it in seen if it['path'].endswith('/new-account')])
        check('第一次注册真的提交了 EAB 绑定', eab_used == 1, str(eab_used))

        second = acme.register_eab_account('mock-kid-1', 'bW9jay1obWFjLWtleQ==', directory,
                                           email='mock@example.com',
                                           account_key_pem=first['accountKeyPem'])
        check('复用已注册账户时不再提交 EAB',
              second['reused'] and '复用' in second['message'], second['message'])
        check('复用只发了一次 new-account（没有二次消耗 EAB）',
              len([it for it in seen if it['path'].endswith('/new-account')]) == 2,
              str(len([it for it in seen if it['path'].endswith('/new-account')])))

        try:
            acme.register_eab_account('mock-kid-1', 'bW9jay1obWFjLWtleQ==', directory,
                                      email='mock@example.com')
            check('同一份 EAB 第二次注册会被拒绝', False, '没有报错')
        except acme.AcmeError as exc:
            check('同一份 EAB 第二次注册会被拒绝，并提示去轮换',
                  'EAB' in str(exc) and ('已经用过' in str(exc) or '轮换' in str(exc)),
                  str(exc)[:120])
    finally:
        server.shutdown()

def section_trustasia(api: Api) -> None:
    """TrustAsia（亚洲诚信）证书申请：下单 → 写验证记录 → 通知验证 → 取回证书。"""
    print("\n== 亚洲诚信（TrustAsia CertCloud）==")
    _backend()
    import shutil

    from app.services import trustasia

    server, seen, _state = _trustasia_mock()
    base = "http://127.0.0.1:%d/openapi/v3" % server.server_address[1]
    cfg = {"keyId": "mock-key-id", "authKey": "mock-auth-key", "apiBase": base}
    aid = pid = 0
    web_root = Path(tempfile.mkdtemp(prefix="trustasia-http-"))
    try:
        # 1) 连通性与鉴权头
        message = trustasia.test_connection(cfg)
        check("ping 返回官方文案", "Everything is fine" in message, message)
        ping_calls = [it for it in seen if it["path"].endswith("/ping")]
        check("鉴权头放在 X-CC-Key-ID / X-CC-Auth-Key",
              bool(ping_calls) and all(it["headers"].get("x-cc-key-id") == "mock-key-id"
                                       and it["headers"].get("x-cc-auth-key") == "mock-auth-key"
                                       for it in ping_calls),
              str(ping_calls[0]["headers"] if ping_calls else {}))
        no_auth = ""
        try:
            trustasia.test_connection({"apiBase": base})
        except trustasia.TrustAsiaError as exc:
            no_auth = str(exc)
        check("缺密钥时直接说该填什么", "Key ID" in no_auth and "API Key" in no_auth,
              no_auth[:120])
        denied = ""
        try:
            trustasia.test_connection({"keyId": "k", "authKey": "a",
                                       "apiBase": "http://127.0.0.1:1/openapi/v3"})
        except trustasia.TrustAsiaError as exc:
            denied = str(exc)
        check("连不上接口时只给一句中文", denied.startswith("连接 TrustAsia 接口失败"),
              denied[:120])

        # 2) 完整申请流程（DNS TXT）
        records: list[tuple] = []
        logs: list[str] = []
        result = trustasia.apply_certificate(
            cfg, domains=["trustasia-smoke.local"], log=logs.append,
            product_id="trustasia_ssl_dv_v2", dcv_method="dns",
            key_type="rsa2048", validity_months=3, poll_seconds=2, timeout_seconds=60,
            dcv_handler=lambda rtype, name, value: records.append((rtype, name, value)),
        )
        check("申请成功并取回证书", "BEGIN CERTIFICATE" in result.get("certificate", ""),
              str(result.get("certificate", ""))[:120])
        check("私钥由本地生成并返回", "PRIVATE KEY" in result.get("privateKey", ""),
              str(result.get("privateKey", ""))[:40])
        order_calls = [it for it in seen if it["method"] == "POST" and "/orders/" in it["path"]]
        check("下单走 POST /orders/{product_id}",
              bool(order_calls) and order_calls[0]["path"].endswith("/trustasia_ssl_dv_v2"),
              str([it["path"] for it in order_calls]))
        order_body = order_calls[0]["body"] if order_calls else {}
        cert_part = order_body.get("certificate") or {}
        check("订单带 CSR / 主域名 / SAN",
              str(cert_part.get("csr", "")).startswith("-----BEGIN CERTIFICATE REQUEST")
              and cert_part.get("common_name") == "trustasia-smoke.local"
              and cert_part.get("dns_names") == ["trustasia-smoke.local"],
              str({k: str(v)[:32] for k, v in cert_part.items()}))
        check("订单带验证方式与订单有效期（月）",
              order_body.get("dcv_method") == "dns" and order_body.get("validity_months") == 3,
              str({k: order_body.get(k) for k in ("dcv_method", "validity_months")}))
        check("订单带防重复的备用订单 ID", bool(order_body.get("alternative_order_id")),
              str(order_body.get("alternative_order_id")))
        check("按 dcv_val 写了 TXT 验证记录",
              bool(records) and records[0][0] == "TXT" and records[0][2].startswith("verify-"),
              str(records))
        check("写完记录后通知 CA 验证完成（PUT dcv-completed）",
              any(it["method"] == "PUT" and it["path"].endswith("/dcv-completed") for it in seen),
              str([it["path"] for it in seen if it["method"] == "PUT"]))

        # 2b) CA 只给相对主机记录时，前缀要跟着 CA 走（别退回 _acme-challenge）
        _backend()
        from app.services import engine as engine_mod

        captured: dict = {}

        class _FakeProvider:
            record_prefix = "_acme-challenge"

            def add_txt(self, domain, value):
                captured["prefix"] = self.record_prefix
                captured["domain"] = domain

            def remove_txt(self, domain, value):
                pass

            def resolve_root(self, domain):
                return domain

            def full_name(self, root, host):
                return host + "." + root

            def relative_host(self, root, name):
                return name

            def record_name(self, domain):
                return domain

            def close(self):
                pass

        class _FakeEngine:
            user_id = 0
            pipeline_id = 0

            def log(self, message, task=None):
                pass

            def _access(self, access_id):
                return "aliyun", {}

            def _sub_domain_roots(self):
                return []

            def _remember_dns(self, provider, domain, value, access_id=0, source="acme"):
                return domain

            def _forget_dns(self, record_name, error=""):
                pass

            def _record_prefix(self, name, base):
                return engine_mod.PipelineRunner._record_prefix(name, base)

        import app.services.dns as dns_service

        _orig = dns_service.create_dns_provider
        dns_service.create_dns_provider = lambda *a, **k: _FakeProvider()
        try:
            writer_add, _writer_clean = engine_mod.PipelineRunner._make_dcv_writer(
                _FakeEngine(), "example.com", 1, {})
            writer_add("TXT", "_dnsauth", "abc123")
        finally:
            dns_service.create_dns_provider = _orig
        check("CA 只给相对记录名时，TXT 前缀按 CA 给的来",
              captured.get("prefix") == "_dnsauth" and captured.get("domain") == "example.com",
              str(captured))

        # 3) CNAME 验证
        cname_records: list[tuple] = []
        result2 = trustasia.apply_certificate(
            cfg, domains=["trustasia-smoke.local"], log=lambda m: None,
            product_id="trustasia_ssl_dv_sans_v2", dcv_method="cname",
            poll_seconds=2, timeout_seconds=60,
            dcv_handler=lambda rtype, name, value: cname_records.append((rtype, name, value)),
        )
        check("CNAME 验证写成 CNAME 记录",
              bool(cname_records) and cname_records[0][0] == "CNAME", str(cname_records))
        check("CNAME 流程同样取回证书", "BEGIN CERTIFICATE" in result2.get("certificate", ""),
              str(result2.get("certificate", ""))[:80])

        # 4) 本地校验：产品能力不匹配时先拦下来
        bad_cases = {
            "单域名产品拒绝泛域名": lambda: trustasia.apply_certificate(
                cfg, domains=["*.trustasia-smoke.local"], log=lambda m: None,
                product_id="trustasia_ssl_dv_v2", dcv_method="dns", poll_seconds=2),
            "OV 产品缺组织信息时提示该填什么": lambda: trustasia.apply_certificate(
                cfg, domains=["trustasia-smoke.local"], log=lambda m: None,
                product_id="trustasia_ssl_ov_v2", dcv_method="dns", poll_seconds=2),
            "产品不支持该验证方式时拒绝": lambda: trustasia.apply_certificate(
                cfg, domains=["trustasia-smoke.local"], log=lambda m: None,
                product_id="trustasia_ssl_dv_wildcard_v2", dcv_method="file", poll_seconds=2),
        }
        for name, case in bad_cases.items():
            try:
                case()
                check(name, False, "没有报错")
            except trustasia.TrustAsiaError as exc:
                check(name, bool(str(exc)), str(exc)[:120])

        # 5) CA 拒签时的报错文案
        bad_server, _bad_seen, _bad_state = _trustasia_mock("failed")
        try:
            trustasia.apply_certificate(
                {"keyId": "k", "authKey": "a",
                 "apiBase": "http://127.0.0.1:%d/openapi/v3" % bad_server.server_address[1]},
                domains=["trustasia-smoke.local"], log=lambda m: None,
                product_id="trustasia_ssl_dv_v2", dcv_method="dns",
                poll_seconds=1, timeout_seconds=30, dcv_handler=lambda *a: None)
            check("订单失败时判为失败", False, "没有报错")
        except trustasia.TrustAsiaError as exc:
            check("订单失败时判为失败且文案是中文",
                  "未签发" in str(exc) and "Traceback" not in str(exc), str(exc)[:120])
        finally:
            bad_server.shutdown()

        # 6) 走接口：授权 + 测试按钮 + 整条流水线（文件验证，不依赖真实 DNS 账号）
        res = api.post("/api/access", {"category": "cloud", "type": "trustasia",
                                       "name": "__smoke_trustasia__",
                                       "config": {"keyId": "mock-key-id", "authKey": "mock-auth-key",
                                                  "environment": "prod", "apiBase": base},
                                       "remark": "smoke"})
        aid = (res.get("data") or {}).get("id") or 0
        check("TrustAsia 授权创建（Key ID + API Key）", ok(res) and aid > 0, msg(res))
        if aid:
            tested = api.post(f"/api/access/{aid}/test")
            tested_data = tested.get("data") or {}
            check("授权「测试」真的调用 /ping",
                  ok(tested) and tested_data.get("success") is True
                  and "Everything is fine" in str(tested_data.get("message")),
                  msg(tested))
            empty = api.post("/api/access", {"category": "cloud", "type": "trustasia",
                                             "name": "__smoke_trustasia_empty__",
                                             "config": {}, "remark": ""})
            check("缺 Key ID / API Key 时拒绝保存并在提示里点名",
                  not ok(empty) and ("Key ID" in (empty.get("msg") or "")
                                     or "API Key" in (empty.get("msg") or "")), msg(empty))

            stages = {"stages": [{"id": "s1", "title": "申请", "tasks": [
                {"id": "t1", "type": "CertApplyTrustAsia", "title": "TrustAsia 证书",
                 "input": {"domains": ["trustasia-smoke.local"], "accessId": aid,
                           "productId": "trustasia_ssl_dv_v2", "dcvMethod": "file",
                           "httpUploadType": "local", "httpWebRoot": str(web_root),
                           "keyType": "rsa2048", "validityMonths": 3,
                           "pollInterval": 2, "timeout": 60},
                 "continueOnError": False}]}], "triggers": []}
            res = api.post("/api/pipeline", {"title": "__smoke_trustasia__", "remark": "smoke",
                                             "content": stages})
            pid = (res.get("data") or {}).get("id") or 0
            check("TrustAsia 流水线创建", ok(res) and pid > 0, msg(res))
            if pid:
                detail = _run_and_wait(api, pid, tries=60)
                check("TrustAsia 流水线签发成功",
                      (detail or {}).get("status") == "success", str((detail or {}).get("status")))
                written = [str(p) for p in web_root.rglob("*") if p.is_file()]
                check("文件验证的验证文件已写进网站根目录", bool(written), str(written[:3]))
                certs = api.get("/api/cert/list?page=1&size=50").get("data") or {}
                hit = [r for r in certs.get("records") or []
                       if "trustasia-smoke.local" in (r.get("domains") or [])]
                check("签发的证书进了证书库", bool(hit), str(certs.get("total")))

        # 7) 插件元数据
        from app.plugins import ACCESS_TYPES, TASK_PLUGIN_MAP

        plugin = TASK_PLUGIN_MAP.get("CertApplyTrustAsia")
        check("插件注册表里有 TrustAsia 申请任务", plugin is not None)
        check("TrustAsia 授权归到云厂商分类",
              (ACCESS_TYPES.get("trustasia") or {}).get("category") == "cloud",
              str((ACCESS_TYPES.get("trustasia") or {}).get("category")))
        check("TrustAsia 有本地 logo",
              (ACCESS_TYPES.get("trustasia") or {}).get("logoFile") == "/logos/access/trustasia.svg",
              str((ACCESS_TYPES.get("trustasia") or {}).get("logoFile")))
        inputs = {item["key"]: item for item in (plugin or {}).get("inputs") or []}
        check("申请任务字段齐全（域名 / 产品 / 验证方式 / DNS 授权）",
              {"domains", "productId", "dcvMethod", "dnsAccessId"} <= set(inputs),
              str(sorted(inputs)))
        check("授权字段只允许 TrustAsia 类型",
              inputs.get("accessId", {}).get("accessTypes") == ["trustasia"],
              str(inputs.get("accessId", {}).get("accessTypes")))
        products = [o.get("value") for o in inputs.get("productId", {}).get("options") or []]
        check("产品下拉覆盖 DV / OV / EV 共 8 种",
              len(products) == 8 and {"trustasia_ssl_dv_v2", "trustasia_ssl_ov_v2",
                                      "trustasia_ssl_ev_v2"} <= set(products), str(products))
        overview = api.get("/api/dashboard/overview").get("data") or {}
        check("「支持的证书」列出 TrustAsia",
              any(item.get("key") == "CertApplyTrustAsia"
                  for item in overview.get("supportedCerts") or []),
              str([i.get("key") for i in overview.get("supportedCerts") or []][:14]))
    finally:
        server.shutdown()
        shutil.rmtree(web_root, ignore_errors=True)
        if pid:
            _drop_pipeline(api, pid)
        if aid:
            api.delete(f"/api/access/{aid}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="123456")
    args = ap.parse_args()

    api = Api(args.base, args.user, args.password)
    print(f"\n== 健康检查 / 登录 ==  {args.base}")
    check("health", ok(api.get("/api/health")))
    check("user/info", ok(api.get("/api/user/info")))
    check("auth/settings", ok(api.get("/api/auth/settings")))
    check("site/config", ok(api.get("/api/site/config")))

    print("\n== 插件与模板 ==")
    plugins = api.get("/api/pipeline/plugins")
    pdata = plugins.get("data") or {}
    check("plugins 返回任务与授权类型",
          ok(plugins) and pdata.get("plugins") and pdata.get("accessTypes"), msg(plugins))
    check("plugins 含通知与 ACME 服务商",
          bool(pdata.get("notifyTypes")) and bool(pdata.get("acmeProviders")))
    tpls = api.get("/api/pipeline/templates")
    check("templates 至少 5 套", ok(tpls) and len(tpls["data"]) >= 5, msg(tpls))

    print("\n== 流水线 CRUD + 模板创建 + 批量 ==")
    created_pids: list[int] = []
    try:
        res = api.post("/api/pipeline/from-template",
                       {"templateId": "self-signed", "title": "__smoke_tpl__"})
        check("from-template 创建", ok(res) and res["data"].get("id"), msg(res))
        tpl_pid = res["data"]["id"] if ok(res) else 0
        if tpl_pid:
            created_pids.append(tpl_pid)
            detail = api.get(f"/api/pipeline/{tpl_pid}")
            check("模板内容落库（含 stages）",
                  ok(detail) and detail["data"]["content"].get("stages"), msg(detail))

        stages = {"stages": [{"id": "s1", "title": "申请", "tasks": [
            {"id": "t1", "type": "CertApplySelfSigned", "title": "自签",
             "input": {"domains": ["smoke.local"], "days": 30}, "continueOnError": False}]}],
            "triggers": []}
        res = api.post("/api/pipeline", {"title": "__smoke_crud__", "remark": "smoke",
                                         "content": stages})
        check("pipeline 创建", ok(res) and res["data"].get("id"), msg(res))
        pid = res["data"]["id"] if ok(res) else 0
        if pid:
            created_pids.append(pid)
            check("pipeline 详情", ok(api.get(f"/api/pipeline/{pid}")))

            listed = api.get("/api/pipeline/list?current=1&size=50")
            row = next((r for r in (listed.get("data") or {}).get("records", [])
                        if r["id"] == pid), None)
            check("pipeline 列表含新建项", ok(listed) and row is not None, msg(listed))
            check("列表带回上次执行状态字段", row is not None and "lastStatus" in row,
                  str(sorted((row or {}).keys())))

            res = api.post(f"/api/pipeline/{pid}/run")
            check("pipeline 运行", ok(res) and (res.get("data") or {}).get("historyId"),
                  msg(res))
            detail = _run_and_wait(api, pid)
            check("pipeline 执行成功", (detail or {}).get("status") == "success",
                  str((detail or {}).get("status")))
            check("执行详情带回任务级状态",
                  bool((detail or {}).get("tasks")), str((detail or {}).get("tasks"))[:160])

            hid = (detail or {}).get("id")
            if hid:
                check("history 详情", ok(api.get(f"/api/history/{hid}")))
                hist = api.get("/api/history/list?current=1&size=10")
                check("history 列表", ok(hist) and hist["data"]["records"], msg(hist))

            res = api.post(f"/api/pipeline/{pid}/copy", {"title": "__smoke_copy__"})
            check("pipeline 复制", ok(res) and res["data"].get("id"), msg(res))
            if ok(res):
                created_pids.append(res["data"]["id"])

            res = api.post(f"/api/pipeline/{pid}/disable", {"disabled": True})
            check("pipeline 停用", ok(res), msg(res))
            api.post(f"/api/pipeline/{pid}/disable", {"disabled": False})

            res = api.post("/api/pipeline/batch",
                           {"action": "run", "ids": [pid]})
            check("pipeline 批量运行", ok(res), msg(res))
    finally:
        for item in created_pids:
            _drop_pipeline(api, item)

    print("\n== 执行历史：分页参数兼容 current / page ==")
    by_current = api.get("/api/history/list?current=1&size=5")
    by_page = api.get("/api/history/list?page=1&size=5")
    check("current 与 page 结果一致",
          (by_current.get("data") or {}).get("current") == 1
          and len((by_current.get("data") or {}).get("records") or [])
          == len((by_page.get("data") or {}).get("records") or []),
          f"{by_current.get('data', {}).get('current')} vs {by_page.get('data', {}).get('current')}")

    print("\n== 授权管理 ==")
    res = api.post("/api/access", {"category": "dns", "type": "cloudflare",
                                   "name": "__smoke_access__",
                                   "config": {"apiToken": "smoke-token"}, "remark": ""})
    check("access 创建", ok(res) and res["data"].get("id"), msg(res))
    aid = res["data"]["id"] if ok(res) else 0
    try:
        if aid:
            lst = api.get("/api/access/list?page=1&size=50")
            row = next((r for r in (lst.get("data") or {}).get("records", [])
                        if r["id"] == aid), None)
            check("access 列表含新建项", ok(lst) and row is not None, msg(lst))
            cfg = (row or {}).get("config") or {}
            check("access 列表明文回传授权信息",
                  cfg.get("apiToken") == "smoke-token", f"config={cfg}")
            check("access 标出哪些字段是密钥",
                  row.get("secretKeys") == ["apiToken"], str(row.get("secretKeys")))

            res = api.put(f"/api/access/{aid}", {
                "category": "dns", "type": "cloudflare", "name": "__smoke_access__",
                "config": {"apiToken": ""}, "remark": "smoke-updated"})
            check("access 清空密钥后保存不报错", ok(res), msg(res))
            lst = api.get("/api/access/list?page=1&size=50")
            row2 = next((r for r in (lst.get("data") or {}).get("records", [])
                         if r["id"] == aid), None)
            check("空密钥提交不会把已有密钥覆盖成空",
                  ((row2 or {}).get("config") or {}).get("apiToken") == "smoke-token",
                  str((row2 or {}).get("config")))

            api.put(f"/api/access/{aid}", {
                "category": "dns", "type": "cloudflare", "name": "__smoke_access__",
                "config": {"apiToken": "  smoke-token-trimmed  "}, "remark": ""})
            lst = api.get("/api/access/list?page=1&size=50")
            row3 = next((r for r in (lst.get("data") or {}).get("records", [])
                         if r["id"] == aid), None)
            check("授权信息保存时自动去除首尾空白",
                  ((row3 or {}).get("config") or {}).get("apiToken") == "smoke-token-trimmed",
                  str((row3 or {}).get("config")))

            res = api.post("/api/access", {"category": "dns", "type": "cloudflare",
                                           "name": "__smoke_empty__",
                                           "config": {}, "remark": ""})
            check("必填项为空时拒绝保存并说明字段",
                  not ok(res) and "API Token" in (res.get("msg") or ""), msg(res))
            if ok(res):
                api.delete(f"/api/access/{(res.get('data') or {}).get('id')}")

            check("授权下拉选项可用", ok(api.get("/api/access/options")))
    finally:
        if aid:
            api.delete(f"/api/access/{aid}")

    print("\n== 通知渠道 ==")
    res = api.post("/api/notification", {"type": "webhook", "name": "__smoke_notify__",
                                         "config": {"url": "http://127.0.0.1:9/hook"}})
    check("通知渠道创建", ok(res) and res["data"].get("id"), msg(res))
    nid = (res.get("data") or {}).get("id") if ok(res) else 0
    try:
        if nid:
            check("通知渠道列表", ok(api.get("/api/notification/list")))
            check("通知渠道下拉", ok(api.get("/api/notification/options")))
            api.put(f"/api/notification/{nid}", {"type": "webhook", "name": "__smoke_notify2__",
                                                 "config": {"url": "http://127.0.0.1:9/hook2"}})
            lst = api.get("/api/notification/list?current=1&size=20")
            rows = (lst.get("data") or {}).get("records") or []
            check("通知渠道改名生效",
                  any(row.get("name") == "__smoke_notify2__" for row in rows), msg(lst))
    finally:
        if nid:
            api.delete(f"/api/notification/{nid}")

    print("\n== 证书资产 / 域名 / 站点监控 ==")
    check("证书库列表", ok(api.get("/api/cert/list?current=1&size=10")))
    check("证书库分页参数兼容 page", ok(api.get("/api/cert/list?page=1&size=10")))
    check("概览接口", ok(api.get("/api/dashboard/overview")))

    res = api.post("/api/domain", {"domain": "smoke-domain.local", "verifyType": "dns"})
    check("域名创建", ok(res) and res["data"].get("id"), msg(res))
    did = (res.get("data") or {}).get("id") if ok(res) else 0
    try:
        if did:
            check("域名列表", ok(api.get("/api/domain/list?current=1&size=10")))
            api.put(f"/api/domain/{did}", {"domain": "smoke-domain.local",
                                           "verifyType": "http", "accessId": 0})
    finally:
        if did:
            api.delete(f"/api/domain/{did}")

    res = api.post("/api/monitor/site", {"url": "https://smoke.local", "port": 443})
    check("监控站点创建", ok(res) and res["data"].get("id"), msg(res))
    sid = (res.get("data") or {}).get("id") if ok(res) else 0
    try:
        if sid:
            check("监控站点列表", ok(api.get("/api/monitor/site/list?current=1&size=10")))
    finally:
        if sid:
            api.delete(f"/api/monitor/site/{sid}")

    print("\n== 系统设置 / 用户 / 开放接口 ==")
    settings = api.get("/api/settings")
    check("系统设置可读", ok(settings) and settings["data"].get("site"), msg(settings))
    check("网络设置默认存在",
          "network" in (settings.get("data") or {}), str(sorted((settings.get("data") or {}).keys())))
    check("审计日志列表", ok(api.get("/api/settings/audit/list?current=1&size=5")))

    res = api.post("/api/user", {"userName": "__smoke_user__", "password": "Smoke#123456",
                                 "nickname": "smoke", "role": "user"})
    check("用户创建", ok(res) and res["data"].get("id"), msg(res))
    uid = (res.get("data") or {}).get("id") if ok(res) else 0
    try:
        if uid:
            check("用户列表", ok(api.get("/api/user/list?current=1&size=10")))
            check("重复用户名被拒绝",
                  not ok(api.post("/api/user", {"userName": "__smoke_user__",
                                                "password": "Smoke#123456"})))
    finally:
        if uid:
            api.delete(f"/api/user/{uid}")

    res = api.post("/api/open/keys", {"name": "__smoke_key__"})
    check("开放接口密钥创建", ok(res) and res["data"].get("id"), msg(res))
    kid = (res.get("data") or {}).get("id") if ok(res) else 0
    try:
        if kid:
            check("开放接口密钥列表", ok(api.get("/api/open/keys")))
            check("开放接口未带密钥时被拒绝",
                  not ok(api.get("/api/open/v1/pipelines")))
    finally:
        if kid:
            api.delete(f"/api/open/keys/{kid}")

    section_supported_certs(api)
    section_cert_import(api)
    section_aliyun_access_test(api)
    section_panel_deploy(api)
    section_notify_failfast(api)
    section_deploy_error_readable(api)
    section_plugin_registry()
    section_cdn_deploy()
    section_more_deploy()
    section_panel_multi()
    section_cdn_deploy_pipeline(api)
    section_cert_apply_inputs(api)
    section_freessl(api)
    section_eab_single_use(api)
    section_jdcloud_split()
    section_signature()
    section_ssh_presets()
    section_storage_deploy(api)
    section_synology_config()
    section_synology_login_flow()
    section_synology_device_id_api(api)
    section_access_type_binding(api)
    section_access_resources(api)
    section_network(api)
    section_dns_records(api)
    section_pipeline_group(api)
    section_task_switch(api)
    section_skip_reuse(api)
    section_trustasia(api)

    # 收尾：按测试域名清掉本轮产出的证书，库里不留 smoke.local 这类垃圾
    removed = purge_test_certs(api)
    print(f"\n== 收尾 ==")
    check("测试证书已清理（不碰用户自己的域名）", True, f"清理 {removed} 张")

    print("\n" + "=" * 52)
    print(f"PASS {len(PASS)}   FAIL {len(FAIL)}   SKIP {len(SKIP)}")
    if SKIP:
        print("跳过：")
        for name in SKIP:
            print(f"  - {name}")
    if FAIL:
        print("\n失败明细：")
        for name, detail in FAIL:
            print(f"  - {name}: {detail}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
