"""密码哈希、JWT、加密存储工具"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
from typing import Any

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings

# ---------------------------------------------------------------- 密码


def hash_password(password: str) -> str:
    """scrypt 哈希，格式 scrypt$N$r$p$salt$hash"""
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    dk = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        n, r, p, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, hashed: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = hashed.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(hash_b64)),
        )
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


# ---------------------------------------------------------------- JWT


def create_token(user_id: int, username: str, role: str, minutes: int | None = None, typ: str = "access") -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes or settings.TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "role": role, "typ": typ, "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None


# ---------------------------------------------------------------- 对称加密（敏感配置）

_AEAD_KEY = hashlib.sha256(settings.SECRET_KEY.encode()).digest()


def encrypt_text(plain: str) -> str:
    if plain is None:
        return ""
    iv = os.urandom(12)
    ct = AESGCM(_AEAD_KEY).encrypt(iv, plain.encode("utf-8"), None)
    return "v1:" + base64.urlsafe_b64encode(iv + ct).decode()


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    if not token.startswith("v1:"):
        return token
    raw = base64.urlsafe_b64decode(token[3:].encode())
    return AESGCM(_AEAD_KEY).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def encrypt_json(data: Any) -> str:
    return encrypt_text(json.dumps(data, ensure_ascii=False))


def decrypt_json(token: str) -> Any:
    text = decrypt_text(token)
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


SENSITIVE_KEYS = (
    "password", "secret", "token", "key", "accessKeySecret", "secretKey",
    "apiKey", "privateKey", "apiToken", "webhook", "access_key_secret",
)

#: 打码占位符。前端提交这个值时表示「没改」，后端还原旧值。
MASK = "******"


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    # secretId / accessKeyId 这类是标识符不是密钥，按名字猜会把它们也打码，
    # 用户就看不到自己的账号 ID 了；真正的密钥字段在插件元数据里声明成 password 组件。
    if lowered in ("secretid", "accesskeyid", "accesskey", "keyid"):
        return False
    return any(token in lowered for token in ("password", "secret", "token",
                                              "privatekey", "apikey"))


def mask_config(data: dict, secret_keys: list[str] | None = None) -> dict:
    """返回给前端时对敏感字段打码。

    secret_keys 非空时按它打码（来源是插件元数据里 component == "password" 的字段），
    这样「哪些字段算敏感」由声明决定，而不是靠字段名猜；
    没传时才退回按名字判断。
    """
    result = {}
    for k, v in (data or {}).items():
        if isinstance(v, dict):
            result[k] = mask_config(v, secret_keys)
            continue
        if secret_keys is not None:
            is_secret = k in secret_keys
        else:
            is_secret = isinstance(v, str) and _looks_secret(k)
        if is_secret:
            result[k] = MASK if v else ""
        else:
            result[k] = v
    return result


def merge_secret(old: dict, new: dict, secret_keys: list[str] | None = None) -> dict:
    """把「没改」的敏感字段还原成库里的旧值。

    「没改」有两种表现：提交了打码占位符 ******，或者干脆留空（编辑时密码框本来就是空的）。
    以前只处理 ******，用户把密码框清空再保存就会把密钥写成空字符串——
    授权看起来「保存成功」，实际所有凭据都没了，表现出来就是「保存不了/保存后不能用了」。
    """
    result = dict(new or {})
    for k, v in result.items():
        if isinstance(v, dict):
            result[k] = merge_secret(old.get(k, {}) or {}, v, secret_keys)
            continue
        is_secret = (k in secret_keys) if secret_keys is not None else _looks_secret(k)
        if not is_secret:
            continue
        if v == MASK or v is None or (isinstance(v, str) and not v.strip()):
            result[k] = (old or {}).get(k, "")
    return result


# ---------------------------------------------------------------- 密码强度

#: 密码强度要求：8 位起、不能是纯数字、不能与用户名相同
MIN_PASSWORD_LENGTH = 8


def validate_password(password: str, username: str = "") -> str:
    """校验新密码，返回中文错误（空字符串表示通过）。

    之前全平台只要求 6 位且不校验弱口令，默认管理员密码还是 123456，
    这里统一收紧：改密、建用户、管理员重置都走这个函数。
    """
    value = (password or "").strip()
    if len(value) < MIN_PASSWORD_LENGTH:
        return f"密码长度至少 {MIN_PASSWORD_LENGTH} 位"
    if username and value.lower() == str(username).strip().lower():
        return "密码不能与用户名相同"
    if value.isdigit():
        return "密码不能是纯数字，请混合字母或符号"
    return ""

