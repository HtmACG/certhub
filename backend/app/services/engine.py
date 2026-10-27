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
               deploy_more, dns_log, logbus, net, notify)
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


# CA 的名字、ACME 目录地址、要不要 EAB，**只有 plugins.ACME_PROVIDERS 一份**。
# 以前这里手抄了一份 _CA_NAMES + 目录字典，新增 CA（例如 FreeSSL / LiteSSL）时漏改，
# 表现就是「选了新 CA 却报『自定义 ACME 需要填写目录地址』」——别再抄第二份。
def _ca_meta(provider: str) -> dict:
    from ..plugins import ACME_PROVIDERS

    return ACME_PROVIDERS.get(str(provider or "").strip()) or {}


def _ca_name(provider: str) -> str:
    """展示用名字：CA 注册表里的中文名，查不到就退回原名。"""
    return str(_ca_meta(provider).get("name") or provider)


def _ca_directory(provider: str, cfg: dict | None = None) -> str:
    """ACME 目录地址：任务里手填的优先（自定义 ACME），否则用 CA 注册表里的内置地址。"""
    custom = str((cfg or {}).get("directory") or "").strip()
    if custom:
        return custom
    return str(_ca_meta(provider).get("directory") or "").strip()


def _ca_needs_eab(provider: str) -> bool:
    """这个 CA 注册 ACME 账户是否必须带 EAB（Google / ZeroSSL / FreeSSL 等）。"""
    return bool(_ca_meta(provider).get("eab"))


class SkipPipeline(Exception):
    """整条流水线无需执行（历史上用于「证书未到期」，现在改由 TaskSkipped 单步跳过）"""


class TaskSkipped(Exception):
    """当前步骤无需执行，跳过它、继续执行后面的步骤。

    典型场景：证书还没到期 / 证书库里已经有同域名的有效证书 / 刚刚申请过。
    以前这种情况抛 SkipPipeline 会把整条流水线中止，部署与通知也跟着不跑了；
    现在只跳过这一步，后面的部署、通知照常执行（重新下发同一张证书没有坏处）。
    """


class PipelineCancelled(Exception):
    """用户手动停止"""


# 这些属于「业务性失败」：错误文案本身就是给用户看的，
# 不需要把 Python 堆栈一起塞进执行日志。
_EXPECTED_ERRORS = (PipelineError, deploy.DeployError, AcmeError, notify.NotifyError,
                    PipelineCancelled)
# 各云厂商客户端用自己的异常类，按类名放行，避免循环 import
_EXPECTED_NAMES = {"VolcError", "DnsError", "AliyunError", "AliyunCasError", "TencentSslError",
                   "TrustAsiaError"}

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
                 content: dict, trigger_type: str = "manual",
                 only_stage_id: str | None = None):
        self.history_id = history_id
        self.pipeline_id = pipeline_id
        self.user_id = user_id
        self.content = content
        self.trigger_type = trigger_type
        # 只单独运行某一个阶段（阶段卡片上的「执行」按钮）；为空时跑整条流水线
        self.only_stage_id = str(only_stage_id) if only_stage_id else None
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

    # ---------- DNS 记录登记簿 ----------
    def _pipeline_title(self) -> str:
        """流水线标题（登记 DNS 记录时一起存，页面上能看出是哪条流水线写的）。"""
        if getattr(self, "_title_cache", None) is None:
            db = SessionLocal()
            try:
                row = db.get(Pipeline, self.pipeline_id)
                self._title_cache = (row.title if row else "") or ""
            finally:
                db.close()
        return self._title_cache

    @staticmethod
    def _full_record_name(provider, domain: str) -> str:
        """provider 真正写下去的完整记录名（含 record_prefix 与子域名托管）。

        留痕要跟实际写入一致，否则用户在页面上看到的记录名和 DNS 后台对不上。
        """
        try:
            from .dns import BaseDnsProvider

            main = provider.resolve_root(domain)
            host = provider.record_name(domain)
            return BaseDnsProvider.full_name(main, host)
        except Exception:  # noqa: BLE001 - 算不出来就退化到 ACME 默认规则
            return certutil.acme_record_name(domain)

    def _remember_dns(self, provider, domain: str, value: str, access_id=0,
                      source: str = "acme") -> str:
        """登记一条刚写入对端 DNS 的记录，返回记录名（供清理时对账）。"""
        record_name = self._full_record_name(provider, domain)
        dns_log.remember(
            self.user_id,
            record_name=record_name,
            record_value=value,
            record_type="TXT",
            source=source,
            access_id=int(access_id or 0),
            pipeline_id=self.pipeline_id,
            pipeline_title=self._pipeline_title(),
            roots=self._sub_domain_roots(),
        )
        return record_name

    def _forget_dns(self, record_name: str, error: str = "") -> None:
        """把记录标成已清理（对端记录已经删掉的留痕）。"""
        if not record_name:
            return
        dns_log.forget(self.user_id, record_name=record_name, record_type="TXT",
                       error=error)

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

    def _cert_ctx_from_row(self, row) -> None:
        """把证书库里的一行放进 _cert_ctx，供后续部署 / 通知步骤使用。"""
        domains = [d for d in (row.domains or "").split(",") if d]
        try:
            key = decrypt_json(row.key_pem)
        except Exception:
            key = ""
        if not isinstance(key, str):
            key = str(key)
        self._cert_ctx = deploy.CertContext(
            domain=domains[0] if domains else (row.domains or ""),
            crt=row.cert_pem or "",
            key=key,
            expires_time=row.not_after.strftime("%Y-%m-%d %H:%M:%S")
            if row.not_after else "",
            domains=domains,
        )

    def _prepare_latest_cert_ctx(self) -> None:
        """单跑部署 / 通知阶段时，从证书库取该流水线的最新证书作为上下文。

        部署任务需要证书内容，但单独运行时前面没有「证书申请」任务产出
        ``_cert_ctx``；这里直接把最近一次入库的证书拿来，不必为了重跑部署
        再申请一遍证书。库里没有证书时什么都不做，部署任务会按原逻辑报错。
        """
        db = SessionLocal()
        try:
            row = (db.query(Certificate)
                   .filter(Certificate.pipeline_id == self.pipeline_id,
                           Certificate.user_id == self.user_id)
                   .order_by(Certificate.id.desc()).first())
            if not row:
                return
            self._cert_ctx_from_row(row)
        finally:
            db.close()

    # ---------- 申请前的跳过判断 ----------
    def _find_valid_cert(self, domains: list[str]):
        """证书库里找一份「域名集合完全一致、且还没过期」的证书（本账号下，最新优先）。

        跳过判断要用它：「已存在」和「刚申请过」都靠这份查询，
        返回 None 表示库里没有能复用的证书。
        """
        wanted = set(domains)
        db = SessionLocal()
        try:
            rows = (db.query(Certificate)
                    .filter(Certificate.user_id == self.user_id,
                            Certificate.not_after.isnot(None))
                    .order_by(Certificate.id.desc()).limit(200).all())
            now = dt.datetime.now()
            for row in rows:
                got = {d for d in (row.domains or "").split(",") if d}
                if got != wanted:
                    continue
                if row.not_after and row.not_after > now:
                    return row
            return None
        finally:
            db.close()

    def _precheck_apply(self, task: dict, cfg: dict, domains: list[str]) -> None:
        """申请前先看能不能直接跳过（跳过 = 不打断流水线，后续步骤继续跑）。

        三条判据，命中任意一条就跳过这一步：
          1. 本流水线已有的证书还没到期（剩余天数 > 提前续期天数）；
          2. 证书库里已经有同域名的有效证书（可在任务里关掉）；
          3. 同一套域名刚刚申请过（默认 10 分钟内，防止重复运行 / 多环境同时触发）。
        跳过时会把那张证书放进 _cert_ctx，后面的部署 / 通知步骤直接用。
        """
        domains = [d for d in domains if d]
        if not domains:
            return
        force = bool(cfg.get("forceUpdate"))
        skip_if_exists = str(cfg.get("skipIfCertificateExists", True)).lower() not in (
            "false", "0")
        recent_minutes = max(0, int(cfg.get("skipRecentMinutes") or 0))
        renew_days = max(1, int(cfg.get("renewDays") or 20))

        row = self._find_valid_cert(domains)
        left = 0
        total = 0
        if row is not None:
            left = (row.not_after - dt.datetime.now()).days
            total = ((row.not_after - row.not_before).days
                     if row.not_before else 0)
            # 证书本身就比「提前续期天数」还短时（例如 90 天的 LE 配了 100 天阈值），
            # 按原值判断会变成「每次运行都续期」，按 certd 的做法减半，最少 2 天。
            if total and total < 10 and total < renew_days:
                adjusted = max(2, total // 2)
                self.log(f"当前更新天数为 {renew_days} 天，证书总天数只有 {total} 天，"
                         f"为避免每次运行都续期，更新天数自动减半为 {adjusted} 天", task)
                renew_days = adjusted

        def skip(reason: str) -> None:
            self.log(f"跳过证书申请：{reason}；继续执行后面的步骤", task)
            if row is not None:
                self._cert_ctx_from_row(row)
                self.log("后续步骤将使用证书库里这张证书"
                         + (f"（到期 {row.not_after:%Y-%m-%d %H:%M}）" if row.not_after else ""),
                         task)
            raise TaskSkipped(reason)

        if force:
            self.log("已开启「强制续期」，忽略跳过判断，直接申请", task)
            return
        if row is None:
            return

        # 3) 刚刚申请过：同一套域名在 skipRecentMinutes 内已经签出过
        if recent_minutes and row.not_before:
            gap = (dt.datetime.now() - row.not_before).total_seconds() / 60
            if 0 <= gap <= recent_minutes:
                skip(f"这套域名 {int(gap)} 分钟前刚申请过证书"
                     f"（阈值 {recent_minutes} 分钟）")
            return

        # 2) 证书库里已经有同域名的有效证书（不限于本流水线）
        if skip_if_exists:
            skip(f"证书库里已有同域名的有效证书（剩余 {left} 天）")

        # 1) 本流水线自己的证书还没到期
        if left > renew_days:
            skip(f"证书剩余 {left} 天有效期，还没到续期时间（提前续期天数 {renew_days} 天）")
        self.log(f"证书剩余 {left} 天，已达到续期天数（{renew_days} 天），开始申请新证书", task)

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

    def _clean_eab(self, kid: str, hmac: str) -> tuple[str, str]:
        """清洗 EAB 凭据：带标签、带换行、夹中文说明的值先规整，脏到没法用时给中文结论。

        真实踩过：用户把「HMAC Key：…」连同中文说明一起粘进来，一路到 base64 解码才炸，
        日志里只有 string argument should contain only ASCII characters + 一堆堆栈。
        """
        from .acme import AcmeError, normalize_eab_pair

        try:
            clean_kid, clean_hmac = normalize_eab_pair(kid, hmac)
        except AcmeError as exc:
            raise PipelineError(str(exc)) from exc
        if (clean_kid, clean_hmac) != (kid, hmac):
            self.log("EAB 凭据里有多余字符（换行 / 标签 / 说明文字），已自动清理后使用")
        return clean_kid, clean_hmac

    def _eab_credentials(self, cfg: dict) -> dict:
        """取 EAB 凭据 + 可能已存在的 ACME 账户（存在 EAB 授权里）。

        EAB 是 CA 发给你的注册凭据，性质跟 AK/SK 一样，统一放「授权管理 → 证书签发」里，
        换一次只改授权，不用去逐条流水线里改任务。
        同时兼容老流水线：任务里直接写着 eabKid / eabHmacKey 的照旧能用。

        **FreeSSL / LiteSSL 的 EAB 只能注册一个账户**，所以第一次注册成功后必须把
        账户私钥与账户 URL 存回这条授权：之后所有流水线、以及「测试」按钮都复用它，
        不再消耗 EAB（否则点一次测试就把用户的 EAB 烧了）。
        """
        kid = str(cfg.get("eabKid") or "").strip()
        hmac = str(cfg.get("eabHmacKey") or "").strip()
        access_id = cfg.get("eabAccessId")
        if not access_id:
            clean_kid, clean_hmac = self._clean_eab(kid, hmac)
            return {"kid": clean_kid, "hmac": clean_hmac, "accessId": 0,
                    "accountKeyPem": "", "accountUrl": ""}

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
        clean_kid, clean_hmac = self._clean_eab(kid, hmac)
        return {"kid": clean_kid, "hmac": clean_hmac, "accessId": int(access_id),
                "accountKeyPem": str(conf.get("acmeAccountKey") or "").strip(),
                "accountUrl": str(conf.get("accountUrl") or "").strip()}

    def _store_eab_account(self, access_id: int, key_pem: str, account_url: str) -> None:
        """把注册出来的 ACME 账户写回 EAB 授权，后续复用（一次性 EAB 不能再注册）。"""
        if not access_id or not key_pem:
            return
        db = SessionLocal()
        try:
            row = db.get(Access, int(access_id))
            if not row or row.user_id != self.user_id:
                return
            conf = decrypt_json(row.config) or {}
            if str(conf.get("acmeAccountKey") or "").strip() == key_pem:
                return
            conf["acmeAccountKey"] = key_pem
            conf["accountUrl"] = account_url
            row.config = encrypt_json(conf)
            db.commit()
            self.log("已把注册出来的 ACME 账户存回 EAB 授权，之后不再消耗 EAB")
        except Exception as exc:  # noqa: BLE001 - 写回失败不影响本次申请
            self.log(f"把 ACME 账户写回 EAB 授权失败（不影响本次申请）：{exc}")
        finally:
            db.close()
    def _acme_account(self, provider: str, cfg: dict) -> dict:
        """ACME 账户：邮箱填在任务上，EAB 从「证书签发」授权里选，账号私钥自动生成并写回任务。

        「账户 URL 已存在」= 这个账户注册过了：**不再提交 EAB**，
        否则一次性的 EAB（FreeSSL / LiteSSL：External account binding has already been used）
        会被判「已经用过」而失败。
        """
        email = (cfg.get("email") or "").strip()
        if not email:
            raise PipelineError("请填写「联系邮箱」：ACME 账户注册与证书到期提醒都用它")
        bundle = self._eab_credentials(cfg)
        eab_kid, eab_hmac = bundle["kid"], bundle["hmac"]
        ca_name = _ca_name(provider)
        if _ca_needs_eab(provider) and not (eab_kid and eab_hmac):
            raise PipelineError(
                f"{ca_name} 注册 ACME 账户必须有 EAB 凭据：请先到「授权管理 → 证书签发」"
                "新建一条 EAB 凭据（Key ID + HMAC Key），再回到本任务的「EAB 凭据」里选择它。"
                "EAB 凭据过期或被删除后会注册失败，重新生成并更新那条授权即可")
        if provider == "zerossl" and not eab_kid:
            self.log("自动获取 ZeroSSL EAB 凭据 ...")
            eab_kid, eab_hmac = get_zerossl_eab(email)
        if eab_kid:
            self.log(f"EAB 凭据已就绪（Key ID {eab_kid[:8]}…）")

        # 账户可能已经注册过：先看任务里存的，再看 EAB 授权里存的
        key_pem = (cfg.get("acmeAccountKey") or "").strip() or bundle.get("accountKeyPem") or None
        account_url = (cfg.get("accountUrl") or "").strip() or bundle.get("accountUrl") or None
        if account_url:
            source = "任务" if (cfg.get("acmeAccountKey") or cfg.get("accountUrl")) else "EAB 授权"
            self.log(f"复用已注册的 ACME 账户（来自{source}），本次不再消耗 EAB")
        return {"keyPem": key_pem, "kid": account_url, "eabKid": eab_kid,
                "eabHmacKey": eab_hmac, "email": email,
                "eabAccessId": bundle.get("accessId") or 0}


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
        # 申请前先判断能不能跳过（未到期 / 已存在 / 刚申请过）
        self._precheck_apply(task, cfg, domains)

        provider = cfg.get("provider") or "letsencrypt"
        directory = _ca_directory(provider, cfg)
        if not directory:
            if provider == "custom":
                raise PipelineError(
                    "「自定义 ACME」需要填写 ACME 目录地址"
                    "（例如 https://acme.ssl.com/sslcom-dv-rsa）")
            raise PipelineError(
                f"「{_ca_name(provider)}」没有内置的 ACME 目录地址：请重新选择证书颁发机构；"
                "如果接的是自建 CA，请把 CA 选成「自定义 ACME」并填写目录地址")

        account = self._acme_account(provider, cfg)
        email = account.get("email") or ""
        self.log(f"证书颁发机构：{_ca_name(provider)}（{directory}）")
        self.log(f"ACME 账户：{email}")
        client = AcmeClient(directory, account.get("keyPem"), log=self.log)
        # 账号私钥先生成并写回任务：注册失败（比如 EAB 过期）时不会每次重试都换一把新 key
        if not account.get("keyPem"):
            self._persist_task_input(task, "acmeAccountKey", client.account_key_pem)
        self._setup_ca_network(client, directory, cfg)
        try:
            client.kid = account.get("kid") or None
            try:
                if account.get("kid"):
                    # 账户已注册：只确认账户还在，不再提交 EAB（一次性的 EAB 不能重复用）
                    client.register(email)
                else:
                    client.register(email, account.get("eabKid", ""), account.get("eabHmacKey", ""))
            except AcmeError as exc:
                # 存的账户地址在 CA 侧没了（换了 CA / 账户被删）：换一把新账户私钥重注册一次
                if not account.get("kid") or "账户在 CA 侧不存在" not in str(exc):
                    raise
                self.log(f"{exc}；改用 EAB 重新注册账户", task)
                client = AcmeClient(directory, None, log=self.log)
                self._setup_ca_network(client, directory, cfg)
                client.register(email, account.get("eabKid", ""), account.get("eabHmacKey", ""))
                account = dict(account, kid="")
            # 首次注册：账号私钥与账户 URL 写回任务，后续申请直接复用
            self._persist_task_input(task, "acmeAccountKey", client.account_key_pem)
            self._persist_task_input(task, "accountUrl", client.kid or "")
            if account.get("eabAccessId") and not account.get("kid"):
                # 同时写回 EAB 授权：同一份 EAB 被其它流水线复用时也不会再注册一次
                self._store_eab_account(account["eabAccessId"], client.account_key_pem,
                                        client.kid or "")

            self.log(f"创建订单：{', '.join(domains)}")
            order = client.new_order(domains, profile=(cfg.get("certProfile") or "").strip())

            challenge_type = cfg.get("challengeType") or "dns"
            dns_provider = None
            dns_records: list[tuple[str, str, str]] = []
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
                        # 顺手登记到「DNS 记录」页：验证记录写完就删，不留痕的话
                        # 用户根本看不出这个域名到底走没走过 DNS 记录
                        record_name = self._remember_dns(
                            dns_provider, ident, txt_value, cfg.get("dnsAccessId"), "acme")
                        dns_records.append((ident, txt_value, record_name))
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
                    for ident, value, record_name in dns_records:
                        try:
                            dns_provider.remove_txt(ident, value)
                            self.log(f"已清理 DNS 记录：{certutil.acme_record_name(ident)}")
                            self._forget_dns(record_name)
                        except Exception as exc:
                            self.log(f"清理 DNS 记录失败（可手动删除）：{exc}")
                            self._forget_dns(record_name, str(exc))
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
        where = self._write_http_file(cfg, f"/.well-known/acme-challenge/{token}", key_auth)
        self.log(f"验证文件已写入：{where}")

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
                         "CertApplyAliyun", "CertApplyTencent", "CertApplyTrustAsia"):
            if task_type == "CertApplyTrustAsia":
                return self._apply_trustasia(task, cfg)
            if task_type in ("CertApplyVolcengine", "CertApplyAliyun", "CertApplyTencent"):
                vendor = task_type[len("CertApply"):].lower()
                return self._apply_cloud_free(task, cfg, vendor)
            if task_type == "CertApplySelfSigned":
                domains = certutil.split_domains(cfg.get("domains"))
                self._precheck_apply(task, cfg, domains)
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
            # 登记到「DNS 记录」页（source=cloud，和 ACME 的验证记录分开标记）
            record_name = self._remember_dns(provider, base, value, dns_access_id, "cloud")
            records.append((provider, base, value, record_name))
            self.log(f"已添加 DNS 验证记录 {name}", task)

        def cleanup() -> None:
            for provider, rec_base, value, record_name in records:
                try:
                    provider.remove_txt(rec_base, value)
                    self._forget_dns(record_name)
                except Exception as exc:  # noqa: BLE001
                    self.log(f"清理 DNS 验证记录失败（可手动删除）：{exc}", task)
                    self._forget_dns(record_name, str(exc))
                finally:
                    try:
                        provider.close()
                    except Exception:  # noqa: BLE001
                        pass
            if records:
                self.log("已清理 DNS 验证记录", task)

        return add, cleanup

    def _make_dcv_writer(self, domain: str, dns_access_id, task: dict):
        """返回 (写验证记录, 清理)：TXT 与 CNAME 都支持。

        和 _make_dns_writer 的区别：TrustAsia 这类 CA 既可能发 TXT（DNS 验证），
        也可能发 CNAME（CNAME 验证），所以记录类型由 CA 决定，不能写死 TXT。
        记录一律交给 DNS 授权去加，跑完再删，避免污染解析。
        """
        from . import dns as dns_service

        dns_type, dns_conf = self._access(dns_access_id)
        base = domain.lstrip("*.")
        providers: list = []
        records: list[tuple] = []  # (provider, kind, root, host, value, record_name)

        def provider():
            if not providers:
                item = dns_service.create_dns_provider(
                    dns_type, dns_conf, log=self.log, root_map=self._sub_domain_roots())
                providers.append(item)
            return providers[0]

        def add(record_type: str, name: str, value: str) -> None:
            record_type = str(record_type or "TXT").upper()
            item = provider()
            prefix = self._record_prefix(name, base)
            if not prefix and name and "." not in str(name).strip("."):
                # 有的 CA 只给相对主机记录（例如 _dnsauth），那就直接拿它当前缀，
                # 否则会退回默认的 _acme-challenge，记录写错地方验证必然不过
                prefix = str(name).strip(".")
            if record_type == "TXT":
                if prefix:
                    item.record_prefix = prefix
                item.add_txt(base, value)
                record_name = self._remember_dns(item, base, value, dns_access_id, "cloud")
                records.append((item, "txt", base, "", value, record_name))
                self.log(f"已添加 DNS 验证记录 {name or base} TXT", task)
                return
            if record_type == "CNAME":
                root = item.resolve_root(base)
                host = item.relative_host(root, name) if name else "@"
                item.add_record(root, host, "CNAME", value)
                records.append((item, "cname", root, host, value, item.full_name(root, host)))
                self.log(f"已添加 DNS 验证记录 {name or host} CNAME → {value}", task)
                return
            raise PipelineError(
                f"该 CA 要求的验证记录是 {record_type}，目前只支持 TXT / CNAME。"
                f"请手动添加：{name} {record_type} {value}，然后重新运行流水线")

        def cleanup() -> None:
            cleared: set[int] = set()
            for item, kind, root, host, value, record_name in records:
                try:
                    if kind == "txt":
                        item.remove_txt(root, value)
                    else:
                        item.delete_record(root, host, "CNAME", value)
                except Exception as exc:  # noqa: BLE001 - 清理失败不能影响主流程
                    self.log(f"清理 DNS 验证记录失败（可手动删除）：{exc}", task)
                if kind == "txt":
                    self._forget_dns(record_name)
                if id(item) not in cleared:
                    cleared.add(id(item))
            for item in providers:
                try:
                    item.close()
                except Exception:  # noqa: BLE001
                    pass
            if records:
                self.log("已清理 DNS 验证记录", task)

        return add, cleanup

    def _write_http_file(self, cfg: dict, rel_path: str, content: str) -> str:
        """把验证文件写到网站根目录（本地目录或通过主机授权 SFTP），返回落盘路径。

        ACME 的 http-01 和 TrustAsia 的 file 验证都用它：CA 只关心
        「这个路径下能不能取到这段内容」，落盘位置由任务里的 httpWebRoot 决定。
        """
        web_root = (cfg.get("httpWebRoot") or "/var/www/html").rstrip("/")
        rel = str(rel_path or "").strip()
        if not rel:
            raise PipelineError("CA 没有返回验证文件路径，无法自动完成文件验证")
        if not rel.startswith("/"):
            rel = "/" + rel
        if (cfg.get("httpUploadType") or "local") == "ssh":
            if not cfg.get("httpAccessId"):
                raise PipelineError("HTTP 验证上传到主机需要选择主机授权")
            _, aconf = self._access(cfg["httpAccessId"])
            client = deploy._ssh_client(aconf)
            try:
                sftp = client.open_sftp()
                deploy._sftp_write(sftp, web_root + rel, content.encode())
                sftp.close()
            finally:
                client.close()
            return web_root + rel
        path = Path(web_root + rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _apply_trustasia(self, task: dict, cfg: dict) -> dict:
        """TrustAsia（亚洲诚信）CertCloud：下单 → 自动写验证记录 → 等签发 → 入库。

        和火山引擎 / 阿里云 / 腾讯云的区别：TrustAsia 支持多域名与泛域名，
        验证方式可选 DNS(TXT) / CNAME / 文件，所以单独一条流程，不复用单域名免费证书那条。
        """
        from . import trustasia

        domains = certutil.split_domains(cfg.get("domains"))
        if not domains:
            raise PipelineError("请填写证书域名")
        self._precheck_apply(task, cfg, domains)
        product_id = str(cfg.get("productId") or "trustasia_ssl_dv_v2").strip()
        dcv_method = str(cfg.get("dcvMethod") or "dns").strip()
        acc_type, aconf = self._access(cfg.get("accessId"))
        if acc_type != "trustasia":
            raise PipelineError("「TrustAsia 授权」选错了：请到授权管理里选 TrustAsia 亚洲诚信")
        if dcv_method in ("dns", "dns-persist", "cname") and not cfg.get("dnsAccessId"):
            raise PipelineError("选择 DNS / CNAME 验证时要指定 DNS 授权（用于自动写验证记录）")
        if dcv_method == "file" and (cfg.get("httpUploadType") or "local") == "ssh" \
                and not cfg.get("httpAccessId"):
            raise PipelineError("文件验证上传到主机时需要选择主机授权")

        # 凭据在授权里，产品 / 组织 / 轮询参数在任务里：合成一份配置给客户端
        merged = dict(aconf or {})
        for key, value in (cfg or {}).items():
            if value not in (None, ""):
                merged[key] = value

        poll_seconds = int(cfg.get("pollInterval") or 10)
        timeout_seconds = int(cfg.get("timeout") or 1800)
        key_type = str(cfg.get("keyType") or "rsa2048")

        def log(message: str) -> None:
            self.log(message, task)

        if dcv_method in ("dns", "dns-persist", "cname"):
            add_record, cleanup = self._make_dcv_writer(domains[0], cfg.get("dnsAccessId"), task)
            file_writer = None
        else:
            add_record, cleanup = None, lambda: None
            file_writer = None
            if dcv_method == "file":
                file_writer = lambda path, content: log(  # noqa: E731
                    "验证文件已写入：" + self._write_http_file(cfg, path, content))

        log(f"校验 TrustAsia 授权 ...")
        try:
            log(trustasia.test_connection(merged))
        except Exception as exc:  # noqa: BLE001 - 预检失败不致命，继续尝试下单
            log(f"授权预检未通过（继续尝试申请）：{exc}")

        try:
            result = trustasia.apply_certificate(
                merged, domains=domains, log=log, product_id=product_id,
                dcv_method=dcv_method, key_type=key_type,
                validity_months=int(cfg.get("validityMonths") or 3),
                poll_seconds=poll_seconds, timeout_seconds=timeout_seconds,
                dcv_handler=add_record, file_handler=file_writer,
                user_external_id=str(cfg.get("userExternalId") or ""),
            )
        finally:
            cleanup()

        crt = (result.get("certificate") or "").strip()
        key_pem = (result.get("privateKey") or "").strip()
        if not crt or not key_pem:
            raise PipelineError(
                "TrustAsia 已签发，但接口未返回证书或私钥内容。"
                "请到 CertCloud 控制台下载后，用「证书库 → 导入证书」手动入库。")

        cert_id, info = self._save_cert(domains, crt, key_pem)
        expires = info.not_after.strftime("%Y-%m-%d %H:%M:%S")
        self._notify_cert_success(task, cfg, domains, info)
        self._cert_ctx = deploy.CertContext(
            domain=domains[0], crt=crt, key=key_pem,
            expires_time=expires, domains=info.domains or domains,
        )
        self.log(f"证书已保存，ID={cert_id}，到期时间 {expires}", task)
        return {"cert.crt": crt, "cert.key": key_pem, "cert.domain": domains[0],
                "cert.issuer": info.issuer, "cert.expiresTime": expires, "cert.id": cert_id}

    def _apply_cloud_free(self, task: dict, cfg: dict, vendor: str) -> dict:
        """云厂商免费证书：申请 → 自动写 DNS 验证 → 轮询签发 → 入库。

        火山引擎 / 阿里云 / 腾讯云 的流程完全一致，只是 API 客户端不同，
        所以合成一个实现，按 vendor 分派。
        """
        from . import aliyun_cas, tencent_ssl, volcengine

        domains = certutil.split_domains(cfg.get("domains"))
        if not domains:
            raise PipelineError("请填写证书域名")
        self._precheck_apply(task, cfg, domains)
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
            if self.only_stage_id:
                # 阶段卡片上的「单独执行」：只保留这一个阶段，其余阶段跳过
                stages = [s for s in stages
                          if str(s.get("id") or "") == self.only_stage_id]
                if not stages:
                    raise PipelineError("阶段不存在或已被删除")
                only_stage = stages[0]
                # 阶段卡片上的开关：关掉的阶段整段跳过，单独运行也不该破例
                if only_stage.get("enabled") is False:
                    raise PipelineError("该阶段已停用，请先启用再单独运行")
                self.log(f"单独运行阶段：{only_stage.get('title') or '未命名'}")
                # 该阶段没有申请任务时，部署 / 通知需要的证书上下文从证书库取
                has_apply = any(
                    str(t.get("type") or "").startswith("CertApply")
                    and t.get("enabled") is not False
                    and t.get("linked") is not False
                    for t in only_stage.get("tasks") or [])
                if not has_apply:
                    self._prepare_latest_cert_ctx()
                    if getattr(self, "_cert_ctx", None):
                        self.log("已载入证书库中该流水线的最新证书")
                    else:
                        self.log("证书库中没有该流水线的证书，部署任务可能无法执行")
            # 拍平成一条执行序列：「失败后跳转」靠改游标实现，跨阶段也能跳。
            # 顺序仍然是 stages → tasks 的展开顺序，和画布上看到的连线一致。
            flat: list[tuple[str, dict]] = []
            for stage in stages:
                stage_title = stage.get("title") or "未命名"
                # 阶段开关（stage.enabled === false）：整段跳过，里面的任务一个都不进执行序列。
                # 和任务级 enabled 的差别只是粒度 —— 临时不想发证书时不用逐个关任务。
                if stage.get("enabled") is False:
                    self.log(f"===== 阶段：{stage_title}（已停用，整段跳过）=====")
                    continue
                for task in stage.get("tasks") or []:
                    flat.append((stage_title, task))
            index_of: dict[str, int] = {}
            for i, (_, task) in enumerate(flat):
                tid = str(task.get("id") or "")
                if tid:
                    index_of[tid] = i

            # 所有阶段都被关掉（或都没有任务）：直接跳过整条流水线。
            # 不拦的话会一路走到「流水线执行完成」，用户以为它跑过了。
            if not flat:
                raise SkipPipeline("所有阶段都已停用或没有任务，没有需要执行的步骤")

            cursor = 0
            last_stage_title = None
            while cursor < len(flat):
                stage_title, task = flat[cursor]
                self._check_cancelled()
                if stage_title != last_stage_title:
                    self.log(f"===== 阶段：{stage_title} =====")
                    last_stage_title = stage_title
                # 任务卡片上的开关：关掉的步骤整段跳过，不发请求、不算失败
                if task.get("enabled") is False:
                    title = task.get("title") or task.get("type")
                    self.log(f"「{title}」已停用，跳过这一步", task)
                    self.tasks_state.append({
                        "taskId": task.get("id"), "title": title,
                        "stage": stage_title, "type": task.get("type"),
                        "status": "disabled", "message": "已停用，已跳过",
                        "duration": 0,
                    })
                    self.bus.publish_tasks(
                        json.dumps(self.tasks_state, ensure_ascii=False))
                    cursor += 1
                    continue
                # 画布上没连线的步骤：不在执行链里，直接跳过（连上之后才会跑）
                if task.get("linked") is False:
                    title = task.get("title") or task.get("type")
                    self.log(f"「{title}」还没有连线，跳过这一步", task)
                    self.tasks_state.append({
                        "taskId": task.get("id"), "title": title,
                        "stage": stage_title, "type": task.get("type"),
                        "status": "unlinked", "message": "未连线，已跳过",
                        "duration": 0,
                    })
                    self.bus.publish_tasks(
                        json.dumps(self.tasks_state, ensure_ascii=False))
                    cursor += 1
                    continue
                state = {"taskId": task.get("id"),
                         "title": task.get("title") or task.get("type"),
                         "stage": stage_title, "type": task.get("type"),
                         "status": "running", "message": "", "duration": 0}
                self.tasks_state.append(state)
                self.bus.publish_tasks(json.dumps(self.tasks_state, ensure_ascii=False))
                t0 = time.time()
                # 失败后跳转：命中就改游标，跳过中间的任务；否则按原逻辑中断
                jump_to = None
                try:
                    outputs = self._run_task(task)
                    _flatten("", outputs or {}, self.variables)
                    state["status"] = "success"
                    state["message"] = "执行成功"
                    self.log("执行成功", task)
                except TaskSkipped as exc:
                    # 只跳过这一步：不算失败，后面的部署 / 通知继续执行
                    state["status"] = "skipped"
                    state["message"] = str(exc)
                    self.log(f"已跳过这一步：{exc}", task)
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
                    target_id = str(task.get("onErrorTaskId") or "")
                    target_at = index_of.get(target_id)
                    if target_id and target_at is not None and target_at > cursor:
                        target_title = (flat[target_at][1].get("title")
                                        or flat[target_at][1].get("type") or "目标任务")
                        state["message"] = f"{exc}（已跳转到「{target_title}」）"
                        jump_to = target_at
                        self.log(f"已配置「失败后跳转」，转到「{target_title}」继续执行", task)
                    elif task.get("continueOnError"):
                        self.log("已忽略该错误，继续执行后续任务", task)
                    else:
                        raise
                finally:
                    state["duration"] = round(time.time() - t0, 2)
                    self._flush(force=True)
                    self.bus.publish_tasks(
                        json.dumps(self.tasks_state, ensure_ascii=False))
                cursor = jump_to if jump_to is not None else cursor + 1
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
                 history_id: int | None = None,
                 only_stage_id: str | None = None) -> int:
    """同步执行（供后台线程调用），返回 history_id。

    history_id 由调用方预先创建时，前端可以在提交后立刻拿到 id 去订阅实时日志，
    不用轮询列表猜「哪条是新记录」。

    only_stage_id 非空时只跑这一个阶段（阶段卡片上的单独执行）。
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
    runner = PipelineRunner(history_id, pipeline_id, uid, content, trigger_type,
                            only_stage_id=only_stage_id)
    runner.run()
    prune_history(pipeline_id)
    return history_id


def run_pipeline_async(pipeline_id: int, trigger_type: str = "manual",
                       user_id: int | None = None,
                       only_stage_id: str | None = None) -> int:
    """提交到线程池执行，立刻返回 history_id。

    历史记录在提交前就建好，前端拿到 id 就能订阅 SSE——
    否则要等任务真正跑起来才知道该订阅哪一条。

    only_stage_id 非空时只跑这一个阶段（阶段卡片上的单独执行）。
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
            run_pipeline(pipeline_id, trigger_type, user_id, history_id=history_id,
                         only_stage_id=only_stage_id)
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
