"""
流水线执行引擎
==============
content 结构：
{
  "stages": [
    {"id": "s1", "title": "申请证书", "tasks": [
        {"id": "t1", "type": "CertApply", "title": "证书申请", "input": {...},
         "continueOnError": false}
    ]}
  ],
  "triggers": [{"id": "tr1", "type": "timer", "cron": "0 3 * * *", "enabled": true}]
}

执行规则：
- 阶段之间串行，阶段内任务串行；
- 任务失败默认中断整条流水线，continueOnError=true 时继续；
- 任务输出写入变量表，后续任务可用 {{ cert.domain }} 引用。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from ..config import CERT_DIR, settings
from ..db import SessionLocal
from ..models import Access, Certificate, History, Notification, Pipeline, Setting, SubDomain, User
from ..security import decrypt_json, encrypt_json
# deploy_ext / deploy_cn / deploy_extra 负责往 deploy.DEPLOY_HANDLERS 注册扩展插件，
# 只被导入不直接使用
from . import (certutil, deploy, deploy_cn, deploy_ext, deploy_extra,  # noqa: F401
               deploy_more, logbus, net, notify)
from .acme import AcmeClient, AcmeError, describe_challenge_error, get_zerossl_eab
from .dns import create_dns_provider, wait_dns_propagation

_executor = ThreadPoolExecutor(max_workers=settings.PIPELINE_MAX_CONCURRENCY,
                               thread_name_prefix="pipeline")
_running: dict[int, bool] = {}
_running_lock = threading.Lock()

# 停止请求按 history_id 记录：流水线可以重跑，用 history_id 才能精确停到「这一次」
_cancel: set[int] = set()
_cancel_lock = threading.Lock()


def request_stop(history_id: int) -> None:
    with _cancel_lock:
        _cancel.add(history_id)


class PipelineError(Exception):
    pass


#: 这些 CA 的 ACME 账户必须用 EAB（External Account Binding）注册
_EAB_REQUIRED = {"google"}
#: 展示用名字
_CA_NAMES = {
    "letsencrypt": "Let's Encrypt",
    "zerossl": "ZeroSSL",
    "google": "Google Trust Services",
    "buypass": "Buypass",
    "custom": "自定义 ACME",
}


class SkipPipeline(Exception):
    """无需执行（例如证书未到续期时间）"""


class PipelineCancelled(Exception):
    """用户手动停止"""


# 这些属于「业务性失败」：错误文案本身就是给用户看的，
# 不需要把 Python 堆栈一起塞进执行日志。
_EXPECTED_ERRORS = (PipelineError, deploy.DeployError, AcmeError, notify.NotifyError,
                    PipelineCancelled)
# 各云厂商客户端用自己的异常类，按类名放行，避免循环 import
_EXPECTED_NAMES = {"VolcError", "DnsError", "AliyunError", "AliyunCasError", "TencentSslError"}

# 网络层异常：连不上 CA / DNS 接口时，堆栈对用户毫无意义，只给一句能照着做的提示
_NETWORK_MODULES = {"httpx", "httpcore", "socket", "ssl", "anyio"}
_NETWORK_HINT = ("连不上外部接口（证书颁发机构 / DNS 服务）。请检查服务器网络、"
                 "DNS 解析与代理设置后重试；海外 CA 需要在「系统设置 → 网络代理」里配置代理。")


def _is_network_error(exc: BaseException) -> bool:
    return (type(exc).__module__ or "").split(".")[0] in _NETWORK_MODULES


def _is_noise_error(exc: BaseException) -> bool:
    """业务性/网络性异常：日志里只留中文说明，不打堆栈。"""
    return _is_network_error(exc) or type(exc).__name__ in _EXPECTED_NAMES


# ---------------------------------------------------------------- 设置读写

def get_setting(key: str, default=None):
    db = SessionLocal()
    try:
        row = db.get(Setting, key)
        if not row or not row.value:
            return default
        try:
            return json.loads(row.value)
        except Exception:
            return row.value
    finally:
        db.close()


def set_setting(key: str, value) -> None:
    db = SessionLocal()
    try:
        row = db.get(Setting, key)
        payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if row:
            row.value = payload
        else:
            db.add(Setting(key=key, value=payload))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- 变量

_VAR_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def resolve(value: Any, variables: dict) -> Any:
    """递归替换 {{ var }} 占位符"""
    if isinstance(value, str):
        def repl(match):
            path = match.group(1).split(".")
            cur: Any = variables
            for p in path:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    return match.group(0)
            return "" if cur is None else str(cur)

        return _VAR_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [resolve(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, variables) for k, v in value.items()}
    return value


def _flatten(prefix: str, data: dict, out: dict):
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten(key, v, out)
        else:
            out[key] = v


# ---------------------------------------------------------------- 运行器

class PipelineRunner:
    def __init__(self, history_id: int, pipeline_id: int, user_id: int,
                 content: dict, trigger_type: str = "manual"):
        self.history_id = history_id
        self.pipeline_id = pipeline_id
        self.user_id = user_id
        self.content = content
        self.trigger_type = trigger_type
        self.variables: dict[str, Any] = {}
        self.logs: list[str] = []
        self.tasks_state: list[dict] = []
        self._last_flush = 0.0
        self.bus = logbus.open_channel(history_id)

    # ---------- 日志 ----------
    def log(self, message: str, task: dict | None = None):
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        prefix = f"[{task.get('title')}] " if task else ""
        line = f"[{stamp}] {prefix}{message}"
        self.logs.append(line)
        # 先推给 SSE 订阅者，再落库（落库有 1 秒节流，实时性靠这一行）
        self.bus.publish(line)
        self._flush(force=False)

    def _flush(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_flush < 1.0:
            return
        self._last_flush = now
        db = SessionLocal()
        try:
            h = db.get(History, self.history_id)
            if h:
                h.log = "\n".join(self.logs[-4000:])
                h.tasks = json.dumps(self.tasks_state, ensure_ascii=False)
                db.commit()
        finally:
            db.close()

    # ---------- 数据库辅助 ----------
    def _setup_ca_network(self, client: AcmeClient, directory: str, cfg: dict) -> None:
        """CA 的网络接入方式：先试直连，不行再走反代域名。

        优先级：任务里填的自定义反代 → 勾选「使用代理」 → 直连探测失败后自动用反代。
        顺带把系统设置里的 HTTP/HTTPS 代理状态打进日志，免得用户以为没生效。
        """
        if net.enabled():
            self.log(f"网络代理：{net.describe_proxy(directory)}（系统设置 → 网络设置）")

        override = str(cfg.get("reverseProxy") or "").strip()
        use_proxy = bool(cfg.get("useProxy"))
        host = net.host_of(directory)
        mapped = net.reverse_proxy_for(directory, override)

        if override:
            if mapped:
                client.enable_reverse_proxy({host: mapped})
                self.log(f"使用自定义反向代理：{host} → {mapped}")
            return

        if use_proxy:
            if mapped:
                client.enable_reverse_proxy({host: mapped})
                self.log(f"已开启「使用代理访问 CA」：{host} → {mapped}")
            else:
                self.log("已开启「使用代理访问 CA」，但这个 CA 没有可用的反代域名，将直连")
            return

        reachable, reason = client.test_direct()
        if reachable:
            self.log(f"直连 {host} 正常")
            return
        if mapped:
            client.enable_reverse_proxy({host: mapped})
            self.log(f"直连 {host} 失败（{reason}），自动改用反向代理：{mapped}")
        else:
            self.log(f"直连 {host} 失败（{reason}），且这个 CA 没有可用的反代域名；"
                     "可在「系统设置 → 网络设置」配置 HTTP/HTTPS 代理")

    #: 展开部署任务时「自动匹配」的目标字段与资源类型
    _AUTO_MATCH: dict[str, tuple[str, str]] = {
        "DeployToBaota": ("siteName", "sites"),
        "DeployTo1Panel": ("websiteId", "sites"),
        "DeployToAliyunCdn": ("domain", "cdnDomains"),
        "DeployToTencentCdn": ("domain", "cdnDomains"),
        "DeployToCtyunCdn": ("domains", "cdnDomains"),
        "DeployToJDCloudCdn": ("domains", "cdnDomains"),
        "DeployToDogeCdn": ("domains", "cdnDomains"),
        "DeployToKuocaiCdn": ("domains", "cdnDomains"),
        "DeployToUpyun": ("domains", "cdnDomains"),
    }

    def _auto_match_resource(self, task_type: str, config: dict, domain: str,
                             task: dict) -> None:
        """自动匹配对端资源：选好授权后按证书域名去对端找出对应的站点/加速域名。

        和 certd 一样：任务上默认勾「自动匹配」，命中就把站点/域名填进去；
        没命中直接报错并告诉用户关掉自动匹配手动选，而不是让部署接口报一个看不懂的错。
        """
        spec = self._AUTO_MATCH.get(task_type)
        if not spec or not config.get("autoMatch"):
            return
        field, kind = spec
        if config.get(field):
            return
        access_id = config.get("accessId")
        if not access_id:
            return
        from . import resources

        access_type, aconf = self._access(access_id)
        items, error = resources.resolve(access_type, aconf, kind)
        if error:
            raise PipelineError(f"自动匹配失败：{error}")
        if not items:
            raise PipelineError("自动匹配失败：该授权下没有可用资源，可关掉自动匹配手动选择")

        plain = domain.lstrip("*.").lower()
        chosen = None
        for item in items:
            texts = [str(item.get("value") or ""), str(item.get("extra") or ""),
                     str(item.get("label") or "")]
            for text in texts:
                for part in text.replace("，", ",").split(","):
                    part = part.strip().lower()
                    if not part:
                        continue
                    if part == plain or part.endswith("." + plain) or plain.endswith("." + part):
                        chosen = item
                        break
                if chosen:
                    break
            if chosen:
                break
        if not chosen:
            raise PipelineError(
                f"自动匹配失败：{access_type} 授权下没有与「{domain}」匹配的资源，"
                "可关掉「自动匹配」手动选择")
        if isinstance(config.get(field), list):
            config[field] = [str(chosen["value"])]
        else:
            config[field] = chosen["value"]
        self.log(f"自动匹配：{domain} → {chosen.get('label') or chosen.get('value')}", task)

    def _sub_domain_roots(self) -> list[str]:
        """当前用户登记的子域名托管列表。

        免费二级域名是独立 zone，DNS 记录必须写到它自己名下，
        否则会写到上级域名，CA 校验永远查不到。
        """
        db = SessionLocal()
        try:
            rows = (db.query(SubDomain)
                    .filter(SubDomain.user_id == self.user_id,
                            SubDomain.disabled.is_(False))
                    .all())
            return [row.domain for row in rows]
        finally:
            db.close()

    def _access(self, access_id) -> tuple[str, dict]:
        if not access_id:
            raise PipelineError("未选择授权")
        db = SessionLocal()
        try:
            row = db.get(Access, int(access_id))
            if not row or row.user_id != self.user_id:
                raise PipelineError("授权不存在或无权限")
            return row.type, decrypt_json(row.config)
        finally:
            db.close()

    def _save_cert(self, domains: list[str], crt: str, key: str):
        info = certutil.parse_cert(crt)
        db = SessionLocal()
        try:
            row = Certificate(
                user_id=self.user_id, pipeline_id=self.pipeline_id,
                domains=",".join(info.domains or domains),
                cert_pem=crt, key_pem=encrypt_json(key),
                issuer=info.issuer, not_before=info.not_before, not_after=info.not_after,
                status="valid",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            cert_id = row.id
        finally:
            db.close()

        folder = CERT_DIR / str(self.user_id)
        folder.mkdir(parents=True, exist_ok=True)
        base = domains[0].replace("*", "wildcard").replace("/", "_")
        (folder / f"{base}.crt").write_text(crt, encoding="utf-8")
        (folder / f"{base}.key").write_text(key, encoding="utf-8")
        self.log(f"证书已保存，ID={cert_id}，到期时间 {info.not_after:%Y-%m-%d %H:%M}")
        return cert_id, info

    # ---------- 证书申请 ----------
    def _persist_task_input(self, task: dict, key: str, value: str) -> None:
        """把首次注册出来的 ACME 账号私钥写回流水线里这条任务。

        没有「ACME 账户」这一层授权：邮箱填在任务上、EAB 从「证书签发」授权里选，
        账号私钥第一次注册后跟着流水线一起存下来，续期时直接复用。
        """
        task_id = str(task.get("id") or "")
        if not value or not task_id:
            return
        db = SessionLocal()
        try:
            row = db.get(Pipeline, self.pipeline_id)
            if not row:
                return
            content = json.loads(row.content or "{}")
            for stage in content.get("stages") or []:
                for item in stage.get("tasks") or []:
                    if str(item.get("id") or "") != task_id:
                        continue
                    item.setdefault("input", {})[key] = value
                    row.content = json.dumps(content, ensure_ascii=False)
                    db.commit()
                    return
        finally:
            db.close()

    def _eab_credentials(self, cfg: dict) -> tuple[str, str]:
        """取 EAB 凭据：优先用任务里选中的 EAB 授权（eabAccessId）。

        EAB 是 CA 发给你的注册凭据，性质跟 AK/SK 一样，统一放「授权管理 → 证书签发」里，
        换一次只改授权，不用去逐条流水线里改任务。
        同时兼容老流水线：任务里直接写着 eabKid / eabHmacKey 的照旧能用。
        """
        kid = str(cfg.get("eabKid") or "").strip()
        hmac = str(cfg.get("eabHmacKey") or "").strip()
        access_id = cfg.get("eabAccessId")
        if not access_id:
            return kid, hmac

        access_type, conf = self._access(access_id)
        if access_type != "eab":
            from ..plugins import ACCESS_TYPES

            name = ACCESS_TYPES.get(access_type, {}).get("name", access_type)
            raise PipelineError(
                f"「EAB 凭据」选中的是一条「{name}」授权，不是 EAB 凭据。"
                "请到「授权管理 → 证书签发」新建一条 EAB 凭据，再重新选择")
        kid = str(conf.get("kid") or conf.get("eabKid") or "").strip()
        hmac = str(conf.get("hmacKey") or conf.get("eabHmacKey") or "").strip()
        if not (kid and hmac):
            raise PipelineError(
                "选中的 EAB 凭据缺少 Key ID 或 HMAC Key：请到「授权管理 → 证书签发」补全后重试")
        return kid, hmac

    def _acme_account(self, provider: str, cfg: dict) -> dict:
        """ACME 账户：邮箱填在任务上，EAB 从「证书签发」授权里选，账号私钥自动生成并写回任务。"""
        email = (cfg.get("email") or "").strip()
        if not email:
            raise PipelineError("请填写「联系邮箱」：ACME 账户注册与证书到期提醒都用它")
        eab_kid, eab_hmac = self._eab_credentials(cfg)
        ca_name = _CA_NAMES.get(provider, provider)
        if provider in _EAB_REQUIRED and not (eab_kid and eab_hmac):
            raise PipelineError(
                f"{ca_name} 注册 ACME 账户必须有 EAB 凭据：请先到「授权管理 → 证书签发」"
                "新建一条 EAB 凭据（Key ID + HMAC Key），再回到本任务的「EAB 凭据」里选择它。"
                f"{ca_name} 的 EAB key 创建后 7 天失效，过期需要重新生成并更新这条授权")
        if provider == "zerossl" and not eab_kid:
            self.log("自动获取 ZeroSSL EAB 凭据 ...")
            eab_kid, eab_hmac = get_zerossl_eab(email)
        if eab_kid:
            self.log(f"EAB 凭据已就绪（Key ID {eab_kid[:8]}…）")
        return {"keyPem": (cfg.get("acmeAccountKey") or "").strip() or None,
                "kid": (cfg.get("accountUrl") or "").strip() or None,
                "eabKid": eab_kid, "eabHmacKey": eab_hmac, "email": email}

    def _apply_cert_with_retry(self, task: dict, cfg: dict):
        """证书申请失败自动重试。

        ACME 申请失败有相当一部分是瞬时的（CA 侧 5xx、DNS 未生效、挑战超时），
        重试一次往往就过了。retry 次数由任务参数 certApplyRetryCount 控制，
        默认 0（不重试），避免把确定性的失败（域名被墙、授权错）也拖成十几分钟。
        """
        retries = max(0, int(cfg.get("certApplyRetryCount") or 0))
        attempt = 0
        while True:
            try:
                return self._apply_cert(task, cfg)
            except (PipelineError, AcmeError) as exc:
                if attempt >= retries:
                    raise
                attempt += 1
                self.log(f"证书申请失败（{exc}），{30} 秒后第 {attempt} 次重试 ...")
                deadline = time.time() + 30
                while time.time() < deadline:
                    self._check_cancelled()
                    time.sleep(min(2.0, max(0.2, deadline - time.time())))

    def _apply_cert(self, task: dict, cfg: dict):
        domains = certutil.split_domains(cfg.get("domains"))
        if not domains:
            raise PipelineError("请填写证书域名")
        renew_days = int(cfg.get("renewDays") or 20)
        force = bool(cfg.get("forceUpdate"))

        # 是否需要续期
        if not force:
            db = SessionLocal()
            try:
                latest = (db.query(Certificate)
                          .filter(Certificate.pipeline_id == self.pipeline_id,
                                  Certificate.user_id == self.user_id)
                          .order_by(Certificate.id.desc()).first())
            finally:
                db.close()
            if latest and latest.not_after:
                left = (latest.not_after - dt.datetime.now()).days
                total = ((latest.not_after - latest.not_before).days
                         if latest.not_before else 0)
                # 证书本身就比"更新天数"短（例如 90 天的 LE 配了 100 天阈值）时，
                # 按原值判断会变成"每次运行都续期"。这里对齐 certd 的做法：
                # 总天数太短就把更新天数减半，最少 2 天。
                if total and total < 10 and total < renew_days:
                    adjusted = max(2, total // 2)
                    self.log(f"当前更新天数为 {renew_days} 天，证书总天数只有 {total} 天，"
                             f"为避免每次运行都续期，更新天数自动减半为 {adjusted} 天"
                             f"（更新天数 = 到期前多少天续期，可在任务配置里调整）")
                    renew_days = adjusted
                same = set(latest.domains.split(",")) == set(domains)
                if same and left > renew_days:
                    self.log(f"证书有效期剩余 {left} 天，还未到续期时间"
                             f"（更新天数 {renew_days} 天，还剩 {left - renew_days} 天后才会更新）")
                    raise SkipPipeline(f"证书剩余 {left} 天有效期，未到续期时间（阈值 {renew_days} 天）")
                if same:
                    self.log(f"证书剩余 {left} 天，已达到更新天数 {renew_days} 天，开始申请新证书")

        provider = cfg.get("provider") or "letsencrypt"
        directory = (cfg.get("directory") or "").strip() or {
            "letsencrypt": "https://acme-v02.api.letsencrypt.org/directory",
            "zerossl": "https://acme.zerossl.com/v2/DV90",
            "google": "https://dv.acme-v02.api.pki.goog/directory",
            "buypass": "https://api.buypass.com/acme/directory",
        }.get(provider, "")
        if not directory:
            raise PipelineError(
                "「自定义 ACME」需要填写 ACME 目录地址（例如 https://acme.ssl.com/sslcom-dv-rsa）")

        account = self._acme_account(provider, cfg)
        email = account.get("email") or ""
        self.log(f"证书颁发机构：{_CA_NAMES.get(provider, provider)}（{directory}）")
        self.log(f"ACME 账户：{email}")
        client = AcmeClient(directory, account.get("keyPem"), log=self.log)
        # 账号私钥先生成并写回任务：注册失败（比如 EAB 过期）时不会每次重试都换一把新 key
        if not account.get("keyPem"):
            self._persist_task_input(task, "acmeAccountKey", client.account_key_pem)
        self._setup_ca_network(client, directory, cfg)
        try:
            client.kid = account.get("kid") or None
            client.register(email, account.get("eabKid", ""), account.get("eabHmacKey", ""))
            # 首次注册：账号私钥与账户 URL 写回任务，后续申请直接复用
            self._persist_task_input(task, "acmeAccountKey", client.account_key_pem)
            self._persist_task_input(task, "accountUrl", client.kid or "")

            self.log(f"创建订单：{', '.join(domains)}")
            order = client.new_order(domains, profile=(cfg.get("certProfile") or "").strip())

            challenge_type = cfg.get("challengeType") or "dns"
            dns_provider = None
            dns_records: list[tuple[str, str]] = []
            sub_roots = self._sub_domain_roots()
            if challenge_type == "dns":
                if not cfg.get("dnsAccessId"):
                    raise PipelineError("DNS 验证需要选择 DNS 授权")
                atype, aconf = self._access(cfg["dnsAccessId"])
                dns_provider = create_dns_provider(atype, aconf, log=self.log,
                                                   root_map=sub_roots)

            try:
                # 分三步走，不能「一个域名走到底」：
                #   1) 先把所有域名的验证物料都提交掉（DNS 记录一次全写好，
                #      验证文件一次全写/上传完）；
                #   2) 等它们都生效；
                #   3) 再逐个通知 CA 验证。
                # 为什么必须这样：泛域名与它的主域名共用 _acme-challenge.<主域名> 这一条记录，
                # 若按「加一条→验一条」逐个来，第二个域名的值会把第一个覆盖掉，
                # CA 校验时永远找不到本次的值（incorrectResponse）——真实踩坑。
                pending: list[dict] = []
                for authz_url in order.get("authorizations", []):
                    authz = client.get(authz_url)
                    ident = authz.get("identifier", {}).get("value")
                    if authz.get("status") == "valid":
                        self.log(f"{ident} 已通过验证，跳过")
                        continue
                    challenges = authz.get("challenges", [])
                    if challenge_type == "dns":
                        chal = next((c for c in challenges if c["type"] == "dns-01"), None)
                        if not chal:
                            raise PipelineError(f"{ident} 未提供 dns-01 验证方式")
                        key_auth = f"{chal['token']}.{client.thumbprint()}"
                        import base64 as _b64
                        import hashlib as _hl

                        txt_value = _b64.urlsafe_b64encode(
                            _hl.sha256(key_auth.encode()).digest()
                        ).rstrip(b"=").decode()
                        self.log(f"添加 DNS 记录：{certutil.acme_record_name(ident)} = {txt_value}")
                        dns_provider.add_txt(ident, txt_value)
                        dns_records.append((ident, txt_value))
                        pending.append({"ident": ident, "authz_url": authz_url,
                                        "chal_url": chal["url"], "txt_value": txt_value,
                                        "key_auth": key_auth})
                    else:
                        chal = next((c for c in challenges if c["type"] == "http-01"), None)
                        if not chal:
                            raise PipelineError(f"{ident} 未提供 http-01 验证方式")
                        key_auth = f"{chal['token']}.{client.thumbprint()}"
                        self._write_http_challenge(cfg, chal["token"], key_auth)
                        pending.append({"ident": ident, "authz_url": authz_url,
                                        "chal_url": chal["url"], "txt_value": "",
                                        "key_auth": key_auth})

                # 等 DNS 记录生效（按权威 NS 判定，避开上游解析器的缓存）
                # waitDnsDiffuseTime：先固定等一会儿再查（部分解析商刷新生效较慢）
                # maxCheckRetryCount：查不到时的重试倍数
                # skipLocalVerify：跳过本地校验，直接交给 CA（能让申请更快，但失败率略高）
                if cfg.get("skipLocalVerify"):
                    self.log("已跳过本地 DNS 校验，直接通知 CA 验证")
                else:
                    diffuse = int(cfg.get("waitDnsDiffuseTime") or 0)
                    if diffuse > 0:
                        self.log(f"等待 DNS 记录生效（{diffuse} 秒）...")
                        deadline = time.time() + diffuse
                        while time.time() < deadline:
                            self._check_cancelled()
                            time.sleep(min(2.0, max(0.2, deadline - time.time())))
                    retry = max(1, int(cfg.get("maxCheckRetryCount") or 3))
                    base_wait = max(settings.DNS_PROPAGATION_WAIT, 10)
                    for item in pending:
                        if not item["txt_value"]:
                            continue
                        wait_dns_propagation(item["ident"], item["txt_value"], log=self.log,
                                             timeout=base_wait * retry,
                                             roots=sub_roots)

                # 全部就绪后再通知 CA
                for item in pending:
                    ident = item["ident"]
                    if challenge_type == "dns":
                        client.answer_dns_challenge(item["chal_url"])
                    else:
                        client.answer_http_challenge(item["chal_url"], item["key_auth"])
                    self.log(f"等待 {ident} 验证结果 ...")
                    result = client.poll(item["authz_url"], should_stop=self._check_cancelled)
                    if result.get("status") != "valid":
                        error = describe_challenge_error(result.get("challenges", []))
                        raise PipelineError(f"{ident} 验证失败：{error}")
                    self.log(f"{ident} 验证通过")
            finally:
                if dns_provider:
                    for ident, value in dns_records:
                        try:
                            dns_provider.remove_txt(ident, value)
                            self.log(f"已清理 DNS 记录：{certutil.acme_record_name(ident)}")
                        except Exception as exc:
                            self.log(f"清理 DNS 记录失败（可手动删除）：{exc}")
                    dns_provider.close()

            self.log("生成证书密钥与 CSR ...")
            key = certutil.generate_key(cfg.get("keyType") or "ec256")
            csr = certutil.build_csr(key, domains)
            order_url = order.get("_url") or ""
            order = client.finalize(order, csr)
            # finalize 后轮询订单直到 valid
            deadline = time.time() + 180
            while time.time() < deadline:
                current = client.get(order_url) if order_url else order
                if current.get("status") == "valid":
                    order = current
                    break
                if current.get("status") == "invalid":
                    raise PipelineError(f"订单状态异常：{json.dumps(current, ensure_ascii=False)[:500]}")
                time.sleep(3)
            cert_url = order.get("certificate")
            if not cert_url:
                raise PipelineError("证书签发失败：未获取到证书地址")
            crt = client.download_certificate(cert_url,
                                              preferred_chain=(cfg.get("preferredChain") or "").strip())
            if "BEGIN CERTIFICATE" not in crt:
                raise PipelineError(f"证书下载异常：{crt[:200]}")
        finally:
            client.close()

        key_pem = certutil.key_to_pem(key)
        cert_id, info = self._save_cert(domains, crt, key_pem)
        pfx = None
        try:
            pfx = certutil.cert_pem_to_pfx(crt, key_pem, cfg.get("pfxPassword") or "",
                                           pfx_args=cfg.get("pfxArgs") or "")
        except Exception as exc:
            self.log(f"生成 PFX 失败（不影响主流程）：{exc}")

        self._notify_cert_success(task, cfg, domains, info)
        ctx = deploy.CertContext(
            domain=domains[0], crt=crt, key=key_pem, pfx=pfx,
            expires_time=info.not_after.strftime("%Y-%m-%d %H:%M:%S"),
            domains=info.domains or domains,
        )
        self._cert_ctx = ctx
        outputs = {
            "cert.crt": crt, "cert.key": key_pem,
            "cert.domain": ctx.domain,
            "cert.issuer": info.issuer,
            "cert.expiresTime": ctx.expires_time,
            "cert.id": cert_id,
        }
        return outputs

    def _write_http_challenge(self, cfg: dict, token: str, key_auth: str):
        web_root = (cfg.get("httpWebRoot") or "/var/www/html").rstrip("/")
        rel = f"/.well-known/acme-challenge/{token}"
        if (cfg.get("httpUploadType") or "local") == "ssh":
            if not cfg.get("httpAccessId"):
                raise PipelineError("HTTP 验证上传到主机需要选择主机授权")
            _, aconf = self._access(cfg["httpAccessId"])
            client = deploy._ssh_client(aconf)
            try:
                sftp = client.open_sftp()
                deploy._sftp_write(sftp, web_root + rel, key_auth.encode())
                sftp.close()
                self.log(f"验证文件已上传：{web_root}{rel}")
            finally:
                client.close()
        else:
            path = Path(web_root + rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key_auth, encoding="utf-8")
            self.log(f"验证文件已写入：{path}")

    # ---------- 任务分发 ----------
    def _merge_access(self, cfg: dict, task: dict) -> dict:
        """把任务里选中的授权配置展开进任务入参。

        部署类任务只在 content 里存 accessId，真正的地址、账号、密钥都在授权里；
        以前直接把任务入参丢给部署函数，导致所有「选授权」的部署任务都报
        「未配置 XX 地址」。这里以授权配置为底稿、任务入参覆盖它，
        空值不覆盖，这样任务级开关（如 asDefault）仍然生效。
        """
        access_id = cfg.get("accessId")
        if not access_id:
            return cfg
        acc_type, aconf = self._access(access_id)
        merged = dict(aconf or {})
        merged.update({k: v for k, v in cfg.items() if v not in (None, "")})
        self.log(f"使用授权：#{access_id}（{acc_type}）", task)
        return merged

    def _check_access_types(self, task: dict, cfg: dict) -> None:
        """校验任务选的授权类型是否对得上（群晖任务不能拿宝塔授权）。

        元数据里每个 access 字段声明了 accessTypes，前端下拉只列这些类型；
        这里是最后一道闸：老数据 / 手填 / 复制来的流水线都可能带着不匹配的授权，
        当场报一句人话，比让部署 handler 抛个看不懂的错强。
        """
        from ..plugins import ACCESS_TYPES, TASK_PLUGIN_MAP

        plugin = TASK_PLUGIN_MAP.get(str(task.get("type") or ""))
        if not plugin:
            return
        for field in plugin.get("inputs") or []:
            allowed = field.get("accessTypes")
            if field.get("component") != "access" or not allowed:
                continue
            access_id = cfg.get(field["key"])
            if not access_id:
                continue
            access_type, _conf = self._access(access_id)
            if access_type in allowed:
                continue
            want = "/".join(ACCESS_TYPES.get(t, {}).get("name", t) for t in allowed)
            got = ACCESS_TYPES.get(access_type, {}).get("name", access_type)
            raise PipelineError(
                f"「{field.get('title') or field['key']}」选错了授权：这个任务需要「{want}」类型的授权，"
                f"当前选的是「{got}」。到授权管理里换一条，或在任务里重新选择")

    def _run_task(self, task: dict) -> dict:
        task_type = task.get("type")
        cfg = resolve(task.get("input") or {}, self.variables)
        self.log(f"开始执行：{task_type}", task)
        self._check_access_types(task, cfg)

        if task_type in ("CertApply", "CertApplySelfSigned", "CertApplyVolcengine",
                         "CertApplyAliyun", "CertApplyTencent"):
            if task_type in ("CertApplyVolcengine", "CertApplyAliyun", "CertApplyTencent"):
                vendor = task_type[len("CertApply"):].lower()
                return self._apply_cloud_free(task, cfg, vendor)
            if task_type == "CertApplySelfSigned":
                domains = certutil.split_domains(cfg.get("domains"))
                cert, key = certutil.self_signed(domains, int(cfg.get("days") or 365),
                                                 cfg.get("keyType") or "ec256")
                from cryptography.hazmat.primitives import serialization

                crt = cert.public_bytes(serialization.Encoding.PEM).decode()
                key_pem = certutil.key_to_pem(key)
                cert_id, info = self._save_cert(domains, crt, key_pem)
                self._notify_cert_success(task, cfg, domains, info)
                self._cert_ctx = deploy.CertContext(
                    domain=domains[0], crt=crt, key=key_pem,
                    expires_time=info.not_after.strftime("%Y-%m-%d %H:%M:%S"),
                    domains=domains,
                )
                return {"cert.crt": crt, "cert.key": key_pem, "cert.domain": domains[0],
                        "cert.issuer": "Self-Signed",
                        "cert.expiresTime": self._cert_ctx.expires_time, "cert.id": cert_id}
            return self._apply_cert_with_retry(task, cfg)

        ctx = getattr(self, "_cert_ctx", None)
        if task_type in deploy.DEPLOY_HANDLERS:
            if not ctx:
                raise PipelineError("没有可部署的证书，请先执行证书申请任务")
            config = self._merge_access(cfg, task)
            self._auto_match_resource(task_type, config, ctx.domain, task)
            handler = deploy.DEPLOY_HANDLERS[task_type]
            handler(ctx, config, lambda m: self.log(m, task))
            return {}

        if task_type == "Notify":
            self._send_notify(task, cfg)
            return {}

        raise PipelineError(f"未知任务类型：{task_type}")

    @staticmethod
    def _record_prefix(name: str, base: str) -> str:
        """把 CA 给的完整记录名拆成「前缀 + 主域名」，复用现有 DNS 适配器。"""
        lowered, low_base = name.lower().rstrip("."), base.lower()
        if lowered == low_base:
            return "@"
        if lowered.endswith("." + low_base):
            return name[: -(len(base) + 1)]
        # 记录不在本域名下，交给服务商按原样尝试
        return ""

    def _make_dns_writer(self, domain: str, dns_access_id, task: dict):
        """返回 (写验证记录, 清理)。

        云厂商免费证书的域名验证记录由 CA 决定（火山引擎 / 阿里云 / 腾讯云都是 TXT），
        这里统一交给 DNS 授权去加，跑完再删，避免污染解析。
        """
        from . import dns as dns_service

        dns_type, dns_conf = self._access(dns_access_id)
        base = domain.lstrip("*.")
        records: list[tuple] = []

        def add(name: str, value: str, record_type: str = "TXT") -> None:
            if str(record_type).upper() != "TXT":
                raise PipelineError(
                    f"该 CA 要求的验证记录是 {record_type}，当前 DNS 适配器只支持 TXT。"
                    f"请手动添加：{name} {record_type} {value}，然后重新运行流水线"
                )
            provider = dns_service.create_dns_provider(
                dns_type, dns_conf, log=self.log, root_map=self._sub_domain_roots())
            prefix = self._record_prefix(name, base)
            if prefix:
                provider.record_prefix = prefix
            provider.add_txt(base, value)
            records.append((provider, base, value))
            self.log(f"已添加 DNS 验证记录 {name}", task)

        def cleanup() -> None:
            for provider, rec_base, value in records:
                try:
                    provider.remove_txt(rec_base, value)
                except Exception as exc:  # noqa: BLE001
                    self.log(f"清理 DNS 验证记录失败（可手动删除）：{exc}", task)
                finally:
                    try:
                        provider.close()
                    except Exception:  # noqa: BLE001
                        pass
            if records:
                self.log("已清理 DNS 验证记录", task)

        return add, cleanup

    def _apply_cloud_free(self, task: dict, cfg: dict, vendor: str) -> dict:
        """云厂商免费证书：申请 → 自动写 DNS 验证 → 轮询签发 → 入库。

        火山引擎 / 阿里云 / 腾讯云 的流程完全一致，只是 API 客户端不同，
        所以合成一个实现，按 vendor 分派。
        """
        from . import aliyun_cas, tencent_ssl, volcengine

        domains = certutil.split_domains(cfg.get("domains"))
        if not domains:
            raise PipelineError("请填写证书域名")
        if len(domains) > 1:
            self.log(f"免费证书为单域名 DV，本次仅申请第一个域名：{domains[0]}", task)
        domain = domains[0]

        acc_type, aconf = self._access(cfg.get("accessId"))
        poll_seconds = int(cfg.get("pollInterval") or 10)
        timeout_seconds = int(cfg.get("timeout") or 900)
        add_record, cleanup = self._make_dns_writer(domain, cfg.get("dnsAccessId"), task)

        def log(msg: str) -> None:
            self.log(msg, task)

        # 预检失败不算致命：有些 AK 只是缺「列证书」这类读权限，
        # 真正的申请接口可能仍然可用，所以打完日志继续走。
        checks = {
            "volcengine": lambda: volcengine.test_connection(aconf),
            "aliyun": lambda: aliyun_cas.test_connection(aconf),
            "tencent": lambda: tencent_ssl.test_connection(aconf),
        }
        self.log(f"校验 {acc_type} 授权 ...", task)
        try:
            self.log(checks[vendor]() if vendor in checks else "跳过预检", task)
        except Exception as exc:  # noqa: BLE001
            self.log(f"授权预检未通过（继续尝试申请）：{exc}", task)

        try:
            if vendor == "volcengine":
                result = volcengine.apply_free_certificate(
                    aconf, domain, log,
                    key_type=cfg.get("keyType") or "RSA",
                    poll_seconds=poll_seconds, timeout_seconds=timeout_seconds,
                    dcv_handler=lambda name, value: add_record(name, value, "TXT"),
                    plan=cfg.get("plan") or "",
                    org_id=cfg.get("organizationId") or "",
                )
                issuer = "Volcengine"
            elif vendor == "aliyun":
                result = aliyun_cas.apply_certificate(
                    aconf, [domain], log,
                    product_code=cfg.get("productCode") or "digicert-free-1-free",
                    email=cfg.get("email") or "",
                    poll_seconds=poll_seconds, timeout_seconds=timeout_seconds,
                    dcv_handler=lambda rec_type, name, value:
                        add_record(name, value, rec_type),
                )
                issuer = "Aliyun"
            elif vendor == "tencent":
                result = tencent_ssl.apply_free_certificate(
                    aconf, domain, log,
                    key_type=cfg.get("keyType") or "RSA",
                    poll_seconds=poll_seconds, timeout_seconds=timeout_seconds,
                    dcv_handler=lambda name, value: add_record(name, value, "TXT"),
                )
                issuer = "Tencent"
            else:
                raise PipelineError(f"未知的云厂商：{vendor}")
        finally:
            cleanup()

        crt = (result.get("certificate") or "").strip()
        key_pem = (result.get("privateKey") or "").strip()
        if not crt or not key_pem:
            raise PipelineError(
                f"{issuer} 已签发，但接口未返回证书或私钥内容。"
                "请到云控制台下载后，用「证书库 → 导入证书」手动入库。"
            )

        cert_id, info = self._save_cert(domains, crt, key_pem)
        expires = info.not_after.strftime("%Y-%m-%d %H:%M:%S")
        self._cert_ctx = deploy.CertContext(
            domain=domain, crt=crt, key=key_pem,
            expires_time=expires, domains=domains,
        )
        self.log(f"证书已保存，ID={cert_id}，到期时间 {expires}", task)
        return {"cert.crt": crt, "cert.key": key_pem, "cert.domain": domain,
                "cert.issuer": issuer, "cert.expiresTime": expires, "cert.id": cert_id}

    def _notify_cert_success(self, task: dict, cfg: dict, domains: list[str], info) -> None:
        """证书申请成功后就发一条通知（不用再单独加「发送通知」任务）。

        对齐 certd 的行为：用任务里指定的渠道，没指定就用默认渠道；
        没配任何渠道时什么都不做（不报错），避免"没配通知就申请失败"。
        通知失败只记日志，绝不影响证书申请本身。
        """
        if str(cfg.get("notifyOnSuccess", True)).lower() in ("false", "0"):
            return

        db = SessionLocal()
        try:
            row = None
            if cfg.get("notificationId"):
                row = db.get(Notification, int(cfg["notificationId"]))
            if not row:
                row = (db.query(Notification)
                       .filter(Notification.user_id == self.user_id,
                               Notification.is_default.is_(True),
                               Notification.enabled.is_(True))
                       .first())
            if not row:
                self.log("证书已申请成功（未配置通知渠道，跳过成功通知）", task)
                return
            ntype, nconf, nname = row.type, decrypt_json(row.config), row.name
        except Exception as exc:  # noqa: BLE001
            self.log(f"读取通知渠道失败（跳过成功通知）：{exc}", task)
            return
        finally:
            db.close()

        left_days = ""
        if info is not None and getattr(info, "not_after", None):
            left_days = f"，剩余 {(info.not_after - dt.datetime.now()).days} 天"
        title = f"证书申请成功【{self.content.get('title') or '证书流水线'}】"
        lines = [
            f"<b>流水线</b>：{self.content.get('title') or ''}",
            f"<b>域名</b>：{', '.join(domains)}",
        ]
        if info is not None and getattr(info, "not_after", None):
            lines.append(f"<b>有效期至</b>：{info.not_after:%Y-%m-%d %H:%M}"
                         + (f"（剩余 {(info.not_after - dt.datetime.now()).days} 天）" if left_days else ""))
        if info is not None and getattr(info, "issuer", ""):
            lines.append(f"<b>签发机构</b>：{info.issuer}")
        content = "<br>".join(lines)

        try:
            notify.send(ntype, nconf, title, content)
            self.log(f"证书申请成功通知已发送：{nname}", task)
        except Exception as exc:  # noqa: BLE001
            self.log(f"证书申请成功通知发送失败（不影响证书）：{exc}", task)

    def _send_notify(self, task: dict, cfg: dict):
        db = SessionLocal()
        try:
            row = None
            if cfg.get("notificationId"):
                row = db.get(Notification, int(cfg["notificationId"]))
            if not row:
                row = (db.query(Notification)
                       .filter(Notification.user_id == self.user_id,
                               Notification.is_default.is_(True),
                               Notification.enabled.is_(True))
                       .first())
            if not row:
                raise PipelineError("没有可用的通知渠道，请先在「通知管理」中配置")
            ntype, nconf = row.type, decrypt_json(row.config)
            name = row.name
        finally:
            db.close()

        title = cfg.get("title") or "证书任务执行结果"
        ctx = getattr(self, "_cert_ctx", None)
        lines = [
            f"<b>流水线</b>：{self.content.get('title', '')}",
            f"<b>状态</b>：成功",
        ]
        if ctx:
            lines.append(f"<b>域名</b>：{ctx.domain}")
            lines.append(f"<b>到期时间</b>：{ctx.expires_time}")
        content = "<br>".join(lines)
        notify.send(ntype, nconf, title, content)
        self.log(f"通知已发送：{name}", task)

    # ---------- 主流程 ----------
    def _check_cancelled(self):
        """任务之间、以及 ACME 轮询的每一轮都会调用这里。"""
        with _cancel_lock:
            if self.history_id in _cancel:
                _cancel.discard(self.history_id)
                raise PipelineCancelled("已手动停止")

    def run(self) -> str:
        started = time.time()
        status = "success"
        try:
            stages = self.content.get("stages") or []
            if not stages:
                raise PipelineError("流水线没有任何阶段")
            for stage in stages:
                self._check_cancelled()
                stage_title = stage.get("title") or "未命名"
                self.log(f"===== 阶段：{stage_title} =====")
                for task in stage.get("tasks") or []:
                    self._check_cancelled()
                    state = {"taskId": task.get("id"),
                             "title": task.get("title") or task.get("type"),
                             "stage": stage_title, "type": task.get("type"),
                             "status": "running", "message": "", "duration": 0}
                    self.tasks_state.append(state)
                    self.bus.publish_tasks(json.dumps(self.tasks_state, ensure_ascii=False))
                    t0 = time.time()
                    try:
                        outputs = self._run_task(task)
                        _flatten("", outputs or {}, self.variables)
                        state["status"] = "success"
                        state["message"] = "执行成功"
                        self.log("执行成功", task)
                    except SkipPipeline as exc:
                        state["status"] = "skipped"
                        state["message"] = str(exc)
                        self.log(str(exc), task)
                        raise
                    except PipelineCancelled:
                        state["status"] = "cancelled"
                        state["message"] = "已手动停止"
                        raise
                    except Exception as exc:
                        state["status"] = "failed"
                        state["message"] = str(exc)
                        self.log(f"执行失败：{exc}", task)
                        if _is_network_error(exc):
                            self.log(_NETWORK_HINT, task)
                        if not (isinstance(exc, _EXPECTED_ERRORS)
                                or _is_noise_error(exc)):
                            self.log(traceback.format_exc(limit=3), task)
                        if task.get("continueOnError"):
                            self.log("已忽略该错误，继续执行后续任务", task)
                        else:
                            raise
                    finally:
                        state["duration"] = round(time.time() - t0, 2)
                        self._flush(force=True)
                        self.bus.publish_tasks(
                            json.dumps(self.tasks_state, ensure_ascii=False))
            self.log(f"流水线执行完成，耗时 {round(time.time() - started, 1)} 秒")
        except SkipPipeline as exc:
            status = "success"
            self.log(f"跳过执行：{exc}")
        except PipelineCancelled:
            status = "cancelled"
            self.log("已手动停止执行")
        except Exception as exc:
            status = "failed"
            self.log(f"流水线执行失败：{exc}")
        finally:
            self._flush(force=True)
            self.bus.publish_tasks(json.dumps(self.tasks_state, ensure_ascii=False))
            self.bus.set_status(status)
            self.bus.close()
            db = SessionLocal()
            try:
                h = db.get(History, self.history_id)
                if h:
                    h.status = status
                    h.end_time = dt.datetime.now()
                    h.tasks = json.dumps(self.tasks_state, ensure_ascii=False)
                p = db.get(Pipeline, self.pipeline_id)
                if p:
                    p.last_history_time = dt.datetime.now()
                    p.status = status
                    ctx = getattr(self, "_cert_ctx", None)
                    if ctx and status == "success":
                        try:
                            p.valid_time = dt.datetime.strptime(ctx.expires_time, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pass
                db.commit()
            finally:
                db.close()
            with _running_lock:
                _running.pop(self.pipeline_id, None)
        return status


# ---------------------------------------------------------------- 对外入口

def start_history(pipeline: Pipeline, trigger_type: str, user_id: int) -> int:
    db = SessionLocal()
    try:
        h = History(
            user_id=user_id, pipeline_id=pipeline.id,
            pipeline_title=pipeline.title, pipeline=pipeline.content,
            status="running", trigger_type=trigger_type,
            start_time=dt.datetime.now(),
        )
        db.add(h)
        db.commit()
        db.refresh(h)
        return h.id
    finally:
        db.close()


def run_pipeline(pipeline_id: int, trigger_type: str = "manual", user_id: int | None = None,
                 history_id: int | None = None) -> int:
    """同步执行（供后台线程调用），返回 history_id。

    history_id 由调用方预先创建时，前端可以在提交后立刻拿到 id 去订阅实时日志，
    不用轮询列表猜「哪条是新记录」。
    """
    db = SessionLocal()
    try:
        pipeline = db.get(Pipeline, pipeline_id)
        if not pipeline:
            raise PipelineError("流水线不存在")
        content = json.loads(pipeline.content or "{}")
        content.setdefault("title", pipeline.title)
        uid = user_id or pipeline.user_id
    finally:
        db.close()

    if not history_id:
        history_id = start_history(pipeline, trigger_type, uid)
    runner = PipelineRunner(history_id, pipeline_id, uid, content, trigger_type)
    runner.run()
    prune_history(pipeline_id)
    return history_id


def run_pipeline_async(pipeline_id: int, trigger_type: str = "manual",
                       user_id: int | None = None) -> int:
    """提交到线程池执行，立刻返回 history_id。

    历史记录在提交前就建好，前端拿到 id 就能订阅 SSE——
    否则要等任务真正跑起来才知道该订阅哪一条。
    """
    with _running_lock:
        if _running.get(pipeline_id):
            raise PipelineError("该流水线正在运行中")
        _running[pipeline_id] = True

    db = SessionLocal()
    try:
        pipeline = db.get(Pipeline, pipeline_id)
        if not pipeline:
            with _running_lock:
                _running.pop(pipeline_id, None)
            raise PipelineError("流水线不存在")
        uid = user_id or pipeline.user_id
        history_id = start_history(pipeline, trigger_type, uid)
    except PipelineError:
        raise
    except Exception:
        with _running_lock:
            _running.pop(pipeline_id, None)
        raise
    finally:
        db.close()

    def _job():
        try:
            run_pipeline(pipeline_id, trigger_type, user_id, history_id=history_id)
        except Exception:
            with _running_lock:
                _running.pop(pipeline_id, None)
            traceback.print_exc()

    _executor.submit(_job)
    return history_id


def is_running(pipeline_id: int) -> bool:
    return bool(_running.get(pipeline_id))


def prune_history(pipeline_id: int):
    db = SessionLocal()
    try:
        p = db.get(Pipeline, pipeline_id)
        keep = max(int(p.keep_history_count or 20), 1) if p else 20
        rows = (db.query(History)
                .filter(History.pipeline_id == pipeline_id)
                .order_by(History.id.desc()).all())
        for row in rows[keep:]:
            db.delete(row)
        db.commit()
    finally:
        db.close()


def cleanup_stale_runs() -> int:
    """启动时把上次进程残留的「运行中」记录收尾。

    执行状态（`_running`、logbus 频道）全在进程内存里，进程一挂就没了；
    数据库里那条 `running` 会永远停在运行中，前端一直转圈等一个不会来的 end。
    启动时统一标成 failed，并补一句说明，用户看到的是「中断」而不是「卡住」。
    """
    db = SessionLocal()
    try:
        rows = db.query(History).filter(History.status == "running").all()
        for h in rows:
            h.status = "failed"
            h.end_time = dt.datetime.now()
            h.log = (h.log or "") + "\n[启动检查] 服务重启，本次执行已中断"
        pipelines = db.query(Pipeline).filter(Pipeline.status == "running").all()
        for p in pipelines:
            p.status = "failed"
        db.commit()
        return len(rows)
    finally:
        db.close()
