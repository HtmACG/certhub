"""
ACME v2 客户端（RFC 8555）
=========================
不依赖 certbot，自行实现 JWS 签名、订单、挑战、证书下载全流程。

支持：
- RSA / ECDSA 账户密钥
- http-01 / dns-01 挑战
- EAB（External Account Binding），适配 ZeroSSL、Google Trust Services
- badNonce 自动重试
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Callable

import httpx

from . import net
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from ..config import settings
from .certutil import build_csr, generate_key, key_to_pem


class AcmeError(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


#: CA 返回的英文错误 → 一句「该点哪里」的中文提示。
#: 用户看到的执行日志里只留中文，原始英文塞进 exc.detail（不进日志），排障时再看。
#: 域名验证失败时的中文结论（挑战对象里的 error.type 决定）
_CHALLENGE_HINTS = [
    ("incorrectresponse", "CA 在 DNS TXT 记录里没找到本次的校验值：记录可能还没生效、"
                          "或同名记录被覆盖。泛域名与主域名一起申请时，"
                          "_acme-challenge 下的两条 TXT 必须同时存在；也可以调大 DNS 等待时间"),
    ("nxdomain", "域名在公共 DNS 里查不到（NXDOMAIN）：请确认域名已备案解析、拼写正确"),
    ("dns", "CA 查询域名 DNS 失败：请确认域名解析正常、CAA 记录允许该 CA"),
    ("caa", "域名的 CAA 记录不允许该 CA 签发：请调整 DNS 里的 CAA 记录"),
    ("connection", "CA 访问验证地址失败：HTTP 验证时多为端口未开 / 防火墙拦截 / 站点未就绪"),
    ("tlshandshake", "TLS 握手失败：HTTP 验证走 443 端口时，站点证书或协议配置有问题"),
    ("unauthorized", "CA 判定该域名未通过授权：请检查域名归属与解析权限"),
    ("rejectedidentifier", "CA 不接受该域名"),
]


def describe_challenge_error(challenges: list) -> str:
    """把挑战失败翻成一句中文，附带 CA 的原始错误类型便于检索。"""
    for chal in challenges or []:
        error = chal.get("error") or {}
        if not error:
            continue
        err_type = str(error.get("type") or "")
        short = err_type.rsplit(":", 1)[-1].lower()
        detail = str(error.get("detail") or "").strip()
        for key, hint in _CHALLENGE_HINTS:
            if key == short or key in detail.lower():
                return f"{hint}（CA 返回：{short or err_type}）"
        return f"{detail or '验证未通过'}（CA 返回：{short or err_type}）"
    return "CA 未给出具体原因，请查看执行日志与 CA 后台记录"


def friendly_problem(problem: dict) -> tuple[str, str]:
    """把 ACME problem document 翻成中文结论，返回 (中文, 原始英文)。"""
    err_type = str(problem.get("type") or "")
    raw = str(problem.get("detail") or problem.get("title") or "").strip()
    low = raw.lower()
    short = err_type.rsplit(":", 1)[-1].lower()

    if "unknown external account binding" in low or "eab key" in low and "unknown" in low:
        return (
            "EAB 凭据无效或已过期：Google 的 EAB key 创建后 7 天失效。"
            "请到 CA 控制台重新生成 Key ID / HMAC Key，然后在「授权管理 → 证书签发」里"
            "更新这条 EAB 凭据（流水线不用改），再运行一次",
            raw or err_type,
        )
    # FreeSSL（LiteSSL / TrustAsia）在 EAB 的 Key ID 对不上时回这句英文
    if "bound account does not exist" in low or "account does not exist" in low and "bound" in low:
        return (
            "EAB 凭据对不上：Key ID / HMAC Key 填错了，或这条凭据已在 FreeSSL 控制台被删除。"
            "请到 FreeSSL「证书自动化 → ACME 账户管理」重新取一份 EAB，"
            "然后在「授权管理 → 证书签发」里更新这条凭据",
            raw or err_type,
        )
    # FreeSSL / LiteSSL 的一次性 EAB：注册过一次就作废
    if "already been used" in low or "already used" in low and "binding" in low:
        return (
            "这条 EAB 已经用过了：这个 CA 的 EAB 只能注册一个 ACME 账户。"
            "请到 CA 控制台「轮换 EAB / 新增凭证」拿一份新的，在「授权管理 → 证书签发」里更新后再运行。"
            "（本系统首次注册成功时会把账户私钥写回任务，之后续期直接复用，不会再消耗 EAB）",
            raw or err_type,
        )
    if short == "externalaccountrequired" or "external account binding is required" in low:
        return (
            "该 CA 要求外部账户绑定（EAB）：请到「授权管理 → 证书签发」新建一条 EAB 凭据，"
            "然后在证书申请任务的「EAB 凭据」里选择它",
            raw or err_type,
        )
    if "invalid or unrecognized host" in low:
        return (
            "CA 不认这次请求里的主机地址：常见于 ACME 账户地址（kid）被写成了反向代理域名，"
            "或账户是直连时注册、后来改成走代理。请把任务里的「账户 URL」清空后重新运行一次"
            "（会重新注册账户，账号私钥保留），再把网络的接入方式固定下来",
            raw or err_type,
        )
    if short == "malformed" and ("host" in low or "dns" in low):
        return (f"CA 认为请求内容不合法：{raw or '请检查域名与账户地址'}", raw or err_type)
    if short == "ratelimited":
        return (
            f"触发 CA 的申请频率限制（rateLimited）：{raw or '同一域名短期内重复申请过多'}。"
            "请等待一段时间再试，或换用其它 CA",
            raw or err_type,
        )
    if short in ("dnstxt", "dns") or "incorrect txt" in low or "dns problem" in low:
        return (
            f"DNS 验证失败：{raw or 'TXT 记录未生效或值不正确'}。"
            "请确认 DNS 授权有解析权限、域名托管在该账号下，并确认记录已生效",
            raw or err_type,
        )
    if short == "unauthorized" or "unauthorized" in low:
        return (f"CA 拒绝了该请求（unauthorized）：{raw or '请检查账号状态与域名归属'}", raw or err_type)
    if short == "rejectedidentifier" or "policy" in short:
        return (f"CA 不接受该域名：{raw or '域名不在其允许范围内（如公共后缀、内网域名）'}", raw or err_type)
    if short == "caa" or "caa" in low:
        return (f"域名的 CAA 记录不允许该 CA 签发：{raw or '请调整 DNS 里的 CAA 记录'}", raw or err_type)
    if short == "accountdoesnotexist":
        return ("ACME 账户在 CA 侧不存在（可能被删除）：把任务里的「账户 URL / 账号私钥」清空后重试", raw or err_type)
    return (raw or "ACME 请求失败", raw or err_type)


#: EAB 凭据允许的字符：base64 / base64url 字母表 + 填充
_EAB_B64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/-_=")
#: 从粘贴内容里捞 base64 片段时的最短长度（Google 的 b64MacKey 都是 40+ 位，取 16 足够）
_EAB_MIN_SEGMENT = 16


#: 两个字段的标签写法：Key ID / kid / HMAC Key
_EAB_KID_LABEL = r'(?:eab\s*)?(?:key[\s_-]*id|kid)'
_EAB_HMAC_LABEL = r'(?:eab\s*)?hmac[\s_-]*key'


def _eab_field_value(text: str, want: str) -> str:
    """从「Key ID: xxx，HMAC Key: yyy」这种整段粘贴里抠出指定字段的值。

    找不到标签就返回空串（调用方会把整段当值处理）。切到下一个标签 /
    逗号 / 分号 / 换行为止，避免把另一个字段的值当成本字段的。
    """
    label = _EAB_KID_LABEL if want == 'kid' else _EAB_HMAC_LABEL
    matched = re.search(r"(?is)" + label + r"\s*[:：=]\s*", text)
    if not matched:
        return ''
    rest = text[matched.end():]
    stop = re.search(r"(?is)(?:" + _EAB_KID_LABEL + r"|" + _EAB_HMAC_LABEL + r")\s*[:：=]|[,;，；\n]", rest)
    if stop:
        rest = rest[:stop.start()]
    return rest.strip()


def _looks_base64(text: str) -> bool:
    return bool(text) and all(ch in _EAB_B64_CHARS for ch in text)


def normalize_eab_value(value: str, label: str = 'EAB 凭据') -> str:
    """把用户填的 EAB 值规整成能直接用的串，脏了就抛一句中文。

    踩过的坑：从 CA 控制台复制时把「HMAC Key：」甚至整段中文说明一起粘进来，
    一路传到 base64 解码才炸，报错是 `string argument should contain only ASCII characters`，
    完全看不出是哪个字段、该怎么改。这里统一清洗 + 给出明确指引。
    """
    want = 'kid' if 'KEY ID' in label.upper() else 'hmac'
    text = str(value or '')
    if not text.strip():
        return ''
    # 整段粘贴时按标签各取各的（「Key ID: xxx，HMAC Key: yyy」），没标签就整段当值
    text = _eab_field_value(text, want) or text.strip()
    # 换行 / 空格 / 全角空格 / 零宽字符都去掉：base64 串里混进这些同样解码失败
    text = re.sub(r"[\s\u200b-\u200f\ufeff]+", "", text).replace("＝", "=")
    if _looks_base64(text):
        return text

    # 里面混了解释文字：尝试从中捞一段 base64（长度够就用它，省得让用户手抠）
    segments = re.findall(r"[A-Za-z0-9+/_\-]{%d,}={0,2}" % _EAB_MIN_SEGMENT, text)
    if segments:
        return max(segments, key=len)

    bad = [ch for ch in text if ord(ch) > 127]
    if bad:
        # 按原顺序取前几个，用户一眼就能认出自己粘的是哪段文字
        sample = ''.join(bad[:6])
        raise AcmeError(
            f'{label} 里有中文 / 全角字符（例如「{sample}」），不是 CA 给的那串字符：'
            f'请回到 CA 控制台只复制「{label}」后面的值（A-Z a-z 0-9 + / =），不要连同说明文字一起粘贴')
    raise AcmeError(
        f'{label} 格式不对：只接受 base64 字符（A-Z a-z 0-9 + / =），当前值里有其它符号。'
        '请重新复制一次；如果是从网页截图手抄的，注意别把 O/0、l/1 抄错')


def normalize_eab_pair(kid: str, hmac_key: str) -> tuple[str, str]:
    """Key ID 与 HMAC Key 一起清洗（Key ID 不要求是 base64，只要求是 ASCII）。"""
    kid_clean = normalize_eab_value(kid, 'EAB Key ID')
    if kid_clean and any(ord(ch) > 127 for ch in kid_clean):
        raise AcmeError(
            'EAB Key ID 里有中文 / 全角字符，不是 CA 给的那串字符：'
            '请回到 CA 控制台只复制 Key ID 后面的值')
    hmac_clean = normalize_eab_value(hmac_key, 'EAB HMAC Key')
    return kid_clean, hmac_clean

def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _int_bytes(value: int) -> bytes:
    length = (value.bit_length() + 7) // 8
    return value.to_bytes(length, "big")


class AcmeClient:
    def __init__(self, directory_url: str, account_key_pem: str | None = None,
                 log: Callable[[str], None] | None = None,
                 url_mapping: dict[str, str] | None = None):
        self.directory_url = directory_url
        self.log = log or (lambda msg: None)
        # CA 域名 → 反代域名（只替换传输地址，ACME 协议要求 JWS 里保留原始 URL）：
        # 只替换实际传输地址，JWS 里的 url 仍是 ACME 原始地址，协议要求两者一致
        self.url_mapping: dict[str, str] = dict(url_mapping or {})
        self.mapping_enabled = bool(self.url_mapping)
        self.account_key_pem = account_key_pem or key_to_pem(generate_key("ec256"))
        self.account_key = serialization.load_pem_private_key(
            self.account_key_pem.encode(), password=None
        )
        self.directory: dict = {}
        self._kid: str | None = None
        self.nonce: str | None = None
        # 海外 CA 的目录/签名接口按域名决定是否走代理（见 services/net.py）
        self.http = net.client(timeout=settings.ACME_HTTP_TIMEOUT, follow_redirects=True)

    @property
    def kid(self) -> str | None:
        return self._kid

    @kid.setter
    def kid(self, value: str | None) -> None:
        """账户地址只能是 CA 的真实域名：反代域名在这里被还原掉。"""
        self._kid = self._origin_url(value or "") or None

    # ------------------------------------------------------------ 底层 HTTP
    def close(self):
        self.http.close()

    def enable_reverse_proxy(self, mapping: dict[str, str] | None = None) -> None:
        """启用反代域名映射；传空 dict 表示关闭。"""
        if mapping:
            self.url_mapping.update({k: v for k, v in mapping.items() if k and v})
        self.mapping_enabled = bool(self.url_mapping)
        for source, target in self.url_mapping.items():
            self.log(f"反向代理：{source} → {target}")

    def _origin_url(self, url: str) -> str:
        """把反代域名还原成 CA 的真实域名。

        反向代理只能改「传输地址」：ACME 的 JWS 里 url 头、以及账户地址（kid）
        必须还是 CA 自己的域名。反代如果连 Location 响应头一起改了，
        拿到的 kid 就变成反代域名，后续所有请求都会被 CA 判成
        「malformed / Invalid or unrecognized host.」——真实踩坑。
        """
        if not url or not isinstance(url, str):
            return url
        for source, target in self.url_mapping.items():
            if source and target and target in url:
                return url.replace(target, source)
        return url

    def _origin_tree(self, data):
        """递归把响应体里的反代域名换回 CA 域名（有的反代连 body 一起改）。"""
        if isinstance(data, dict):
            return {k: self._origin_tree(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._origin_tree(item) for item in data]
        if isinstance(data, str) and data.startswith("http") and self.url_mapping:
            return self._origin_url(data)
        return data

    def _transport_url(self, url: str) -> str:
        """把 CA 域名换成反代域名（只影响传输地址）。"""
        if not self.mapping_enabled:
            return url
        for source, target in self.url_mapping.items():
            if source and target and source in url:
                return url.replace(source, target)
        return url

    def test_direct(self) -> tuple[bool, str]:
        """直连测试 ACME 目录：先试直连，连不上再自动切到反代域名。"""
        try:
            resp = self.http.get(self.directory_url, timeout=net.PROBE_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {str(exc)[:160]}"
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}"
        return True, ""

    def _load_directory(self):
        if self.directory:
            return
        resp = self.http.get(self._transport_url(self.directory_url))
        if resp.status_code != 200:
            raise AcmeError(f"无法访问 ACME 目录：{self.directory_url}", resp.text[:500])
        self.directory = resp.json()

    def _get_nonce(self) -> str:
        if self.nonce:
            nonce, self.nonce = self.nonce, None
            return nonce
        self._load_directory()
        resp = self.http.head(self._transport_url(self.directory["newNonce"]))
        nonce = resp.headers.get("Replay-Nonce")
        if not nonce:
            raise AcmeError("获取 ACME nonce 失败")
        return nonce

    # ------------------------------------------------------------ JWS
    def _jwk(self) -> dict:
        pub = self.account_key.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            return {"e": b64u(_int_bytes(pub.public_numbers().e)),
                    "kty": "RSA", "n": b64u(_int_bytes(pub.public_numbers().n))}
        if isinstance(pub, ec.EllipticCurvePublicKey):
            crv = "P-256" if isinstance(pub.curve, ec.SECP256R1) else "P-384"
            size = 32 if crv == "P-256" else 48
            return {
                "crv": crv, "kty": "EC",
                "x": b64u(pub.public_numbers().x.to_bytes(size, "big")),
                "y": b64u(pub.public_numbers().y.to_bytes(size, "big")),
            }
        raise AcmeError("不支持的账户密钥类型")

    def thumbprint(self) -> str:
        jwk = self._jwk()
        canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode()
        return b64u(hashlib.sha256(canonical).digest())

    def _sign(self, data: bytes) -> tuple[str, bytes]:
        pub = self.account_key.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            sig = self.account_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
            return "RS256", sig
        if isinstance(pub, ec.EllipticCurvePublicKey):
            if isinstance(pub.curve, ec.SECP384R1):
                der = self.account_key.sign(data, ec.ECDSA(hashes.SHA384()))
                alg, size = "ES384", 48
            else:
                der = self.account_key.sign(data, ec.ECDSA(hashes.SHA256()))
                alg, size = "ES256", 32
            r, s = decode_dss_signature(der)
            return alg, r.to_bytes(size, "big") + s.to_bytes(size, "big")
        raise AcmeError("不支持的账户密钥类型")

    def _alg(self) -> str:
        pub = self.account_key.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            return "RS256"
        if isinstance(pub, ec.EllipticCurvePublicKey):
            return "ES384" if isinstance(pub.curve, ec.SECP384R1) else "ES256"
        raise AcmeError("不支持的账户密钥类型")

    def _jws(self, url: str, payload: dict | None, use_jwk: bool = False) -> dict:
        protected = {"alg": self._alg(), "nonce": self._get_nonce(), "url": url}
        if use_jwk or not self.kid:
            protected["jwk"] = self._jwk()
        else:
            protected["kid"] = self.kid
        protected_b64 = b64u(json.dumps(protected, separators=(",", ":")).encode())
        payload_b64 = "" if payload is None else b64u(json.dumps(payload).encode())
        _alg, sig = self._sign(f"{protected_b64}.{payload_b64}".encode())
        return {"protected": protected_b64, "payload": payload_b64, "signature": b64u(sig)}

    def _post(self, url: str, payload: dict | None, use_jwk: bool = False) -> httpx.Response:
        # 目录必须先加载：调用方（如 new_order）要先用 self.directory["newOrder"] 取地址，
        # 如果账号已注册（有 kid）而没走 register()，这里不兜底就会 KeyError。
        self._load_directory()
        last_error = None
        for _ in range(4):
            body = self._jws(url, payload, use_jwk=use_jwk)
            # 签名用原始 url（JWS 里的 url 头必须是 CA 的真实地址），
            # 实际发出去才换成反代域名
            resp = self.http.post(self._transport_url(url), json=body,
                                  headers={"Content-Type": "application/jose+json"})
            nonce = resp.headers.get("Replay-Nonce")
            if nonce:
                self.nonce = nonce
            if resp.status_code < 400:
                return resp
            try:
                problem = resp.json()
            except Exception:
                problem = {"detail": resp.text[:500]}
            err_type = problem.get("type", "")
            message, raw = friendly_problem(problem)
            last_error = AcmeError(message, raw + "\n" + json.dumps(problem, ensure_ascii=False))
            if err_type.endswith(":badNonce"):
                continue
            raise last_error
        raise last_error or AcmeError("ACME 请求失败")

    # ------------------------------------------------------------ 账户
    def register(self, email: str, eab_kid: str = "", eab_hmac_key: str = "") -> str:
        self._load_directory()
        payload: dict = {"termsOfServiceAgreed": True,
                         "contact": [f"mailto:{email}"] if email else []}
        if eab_kid and eab_hmac_key:
            payload["externalAccountBinding"] = self._eab(eab_kid, eab_hmac_key)
        resp = self._post(self.directory["newAccount"], payload, use_jwk=True)
        location = resp.headers.get("Location") or ""
        if location and self._origin_url(location) != location:
            self.log("ACME 账户地址已还原为 CA 原始域名（反向代理只改传输地址）")
        self.kid = location
        if not self.kid:
            raise AcmeError("注册 ACME 账户失败：未返回账户地址")
        self.log(f"ACME 账户就绪：{self.kid}")
        return self.kid

    def _eab(self, kid: str, hmac_key_b64: str) -> dict:
        import hmac as _hmac

        # 清洗用户粘进来的值：带标签、带换行、夹中文说明都在这挡住，
        # 不让它一路走到 base64 解码抛 UnicodeEncodeError（那个报错完全看不懂）
        kid, hmac_key_b64 = normalize_eab_pair(kid, hmac_key_b64)
        url = self.directory["newAccount"]
        protected = {"alg": "HS256", "kid": kid, "url": url}
        protected_b64 = b64u(json.dumps(protected, separators=(",", ":")).encode())
        payload_b64 = b64u(json.dumps(self._jwk(), separators=(",", ":")).encode())
        try:
            key = b64u_decode(hmac_key_b64)
        except Exception as exc:  # noqa: BLE001 - 兜底：base64 报错不能裸奔给用户
            raise AcmeError(
                "EAB HMAC Key 无法按 Base64 解码：请只填 CA 控制台给的那串字符"
                "（A-Z a-z 0-9 + / =），不要带中文说明或整段文字") from exc
        sig = _hmac.new(key, f"{protected_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
        return {"protected": protected_b64, "payload": payload_b64, "signature": b64u(sig)}

    # ------------------------------------------------------------ 订单
    def new_order(self, domains: list[str], profile: str = "") -> dict:
        # 目录要先加载：下面的 self.directory["newOrder"] 在 _post 之前求值
        self._load_directory()
        payload: dict = {"identifiers": [{"type": "dns", "value": d} for d in domains]}
        # ACME Profiles（Let's Encrypt 的 tlsserver / shortlived 等）：
        # 只有 CA 在 meta.profiles 里声明过才发，否则会被判 malformed
        if profile:
            supported = (self.directory.get("meta") or {}).get("profiles") or []
            if profile in supported:
                payload["profile"] = profile
                self.log(f"使用证书配置（profile）：{profile}")
            else:
                self.log(f"CA 未提供 profile「{profile}」，按默认配置签发")
        resp = self._post(self.directory["newOrder"], payload)
        order = self._origin_tree(resp.json())
        order["_url"] = self._origin_url(resp.headers.get("Location") or "")
        return order

    def get(self, url: str) -> dict:
        return self._origin_tree(self._post(self._origin_url(url), None).json())

    def answer_http_challenge(self, url: str, key_auth: str) -> None:
        self._post(self._origin_url(url), {"keyAuthorization": key_auth})

    def answer_dns_challenge(self, url: str) -> None:
        self._post(self._origin_url(url), {})

    def poll(self, url: str, timeout: int = 180, interval: int = 3,
             should_stop=None) -> dict:
        """轮询授权状态。

        should_stop 是可选的「是否已被取消」回调——签发一次可能要等几十秒，
        不检查的话用户点了停止也得等这一轮跑完。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if should_stop:
                should_stop()
            obj = self.get(url)
            status = obj.get("status")
            if status in ("valid", "invalid", "deactivated", "expired", "revoked"):
                return obj
            time.sleep(interval)
        raise AcmeError("等待 ACME 验证超时")

    def finalize(self, order: dict, csr_der: bytes) -> dict:
        resp = self._post(self._origin_url(order["finalize"]), {"csr": b64u(csr_der)})
        return self._origin_tree(resp.json())

    def download_certificate(self, url: str, preferred_chain: str = "") -> str:
        """下载证书。

        preferred_chain 走 ACME 的 Link: rel="alternate" 机制：
        Let's Encrypt 同时提供 ISRG Root X1 / X2 两条链，Google 提供
        GTS Root R1 / GlobalSign，部分老设备只认其中一条。
        不填就用 CA 的默认链。
        """
        resp = self._post(self._origin_url(url), None)
        pem = resp.text
        if not preferred_chain:
            return pem

        alternates = self._parse_alternate_links(resp.headers.get("Link") or "")
        if not alternates:
            self.log(f"CA 未提供备用证书链，使用默认链（期望「{preferred_chain}」）")
            return pem

        for alt_url in alternates:
            try:
                alt = self._post(self._origin_url(alt_url), None)
            except AcmeError as exc:
                self.log(f"备用链下载失败（跳过）：{exc}")
                continue
            if preferred_chain.lower() in (alt.text or "").lower():
                self.log(f"已切换到证书链：{preferred_chain}")
                return alt.text
        self.log(f"没找到包含「{preferred_chain}」的备用链，使用默认链")
        return pem

    @staticmethod
    def _parse_alternate_links(header: str) -> list[str]:
        """从 Link 头里挑出 rel="alternate" 的地址。"""
        urls: list[str] = []
        for part in (header or "").split(","):
            segment = part.strip()
            if 'rel="alternate"' not in segment:
                continue
            start = segment.find("<")
            end = segment.find(">", start + 1)
            if start >= 0 and end > start:
                urls.append(segment[start + 1:end])
        return urls

    def revoke(self, cert_pem: str, reason: int = 4) -> None:
        from cryptography import x509

        der = x509.load_pem_x509_certificate(cert_pem.encode()).public_bytes(
            serialization.Encoding.DER
        )
        self._post(self.directory["revokeCert"], {"certificate": b64u(der), "reason": reason})


# ---------------------------------------------------------------- 高层封装

def register_eab_account(kid: str, hmac_key: str, directory: str, email: str = '',
                         account_key_pem: str = '',
                         log: Callable[[str], None] | None = None) -> dict:
    """用 EAB 注册 ACME 账户；已经注册过就复用，不再消耗（可能一次性的）EAB。

    为什么要拆出来：FreeSSL / LiteSSL 的 EAB 是**一次性**的，注册成功一次就作废
    （CA 回 External account binding has already been used）。所以：
      · 首次注册成功后，账户私钥与账户 URL 必须存下来（存进 EAB 授权里）；
      · 之后再「测试」或跑流水线，直接用存下来的账户，不再发 EAB；
      · 否则点一次「测试」就把用户的 EAB 烧掉了，流水线必然失败。

    返回 {message, accountKeyPem, accountUrl, reused}。
    """
    kid, hmac_key = normalize_eab_pair(kid, hmac_key)
    if not kid or not hmac_key:
        raise AcmeError('EAB 凭据不完整：请填写 Key ID 与 HMAC Key')
    log = log or (lambda msg: None)
    reused = bool(account_key_pem)
    client = AcmeClient(directory, account_key_pem or None, log=log)
    try:
        reachable, reason = client.test_direct()
        if not reachable:
            host = net.host_of(directory)
            mapped = net.reverse_proxy_for(directory)
            if not mapped:
                raise AcmeError(
                    f'连不上 {host}（{reason}）：请先在「系统设置 → 网络代理」里配置代理后重试')
            client.enable_reverse_proxy({host: mapped})
        contact = (email or '').strip() or 'eab-test@certhub.local'
        if reused:
            client.register(contact)
            message = 'EAB 对应账户可用（复用已注册账户，未再次消耗 EAB）'
        else:
            client.register(contact, kid, hmac_key)
            message = 'EAB 凭据可用（已在 CA 侧注册账户，账户私钥已保存，后续复用不再消耗 EAB）'
        return {'message': message, 'accountKeyPem': client.account_key_pem,
                'accountUrl': client.kid or '', 'reused': reused}
    finally:
        client.close()

def verify_eab(kid: str, hmac_key: str, directory: str, email: str = "",
               log: Callable[[str], None] | None = None) -> str:
    """用一条 EAB 凭据去 CA 注册一个临时账户，验证凭据是否还有效。

    Google 的 EAB key 创建后 7 天失效，等流水线跑到一半才报错太晚；
    「授权管理」里的「测试」按钮调的就是这里，点一下就知道要不要换 Key。
    注册出的临时账户不落库、不影响正式账户。
    """
    return register_eab_account(kid, hmac_key, directory, email=email, log=log)["message"]


def get_zerossl_eab(email: str) -> tuple[str, str]:
    """ZeroSSL 允许通过邮箱自动获取 EAB 凭据"""
    resp = net.post(
        "https://api.zerossl.com/acme/eab-credentials-email",
        data={"email": email}, timeout=30,
    )
    data = resp.json()
    if not data.get("success"):
        raise AcmeError("获取 ZeroSSL EAB 凭据失败，请检查邮箱", json.dumps(data, ensure_ascii=False))
    return data["eab_kid"], data["eab_hmac_key"]
