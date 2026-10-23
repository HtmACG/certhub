"""
CertHub - 全局配置
所有可配置项均可通过环境变量覆盖，方便 Docker / 源码部署。
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                               # certd-lite/

DATA_DIR = Path(os.getenv("CERTD_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CERT_DIR = DATA_DIR / "certs"
CERT_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret_key() -> str:
    """密钥优先从环境变量读取，其次读取 data/secret.key，最后生成并落盘。"""
    env_key = os.getenv("CERTD_SECRET_KEY")
    if env_key:
        return env_key
    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(48)
    key_file.write_text(key, encoding="utf-8")
    # 这把 key 同时用于签 JWT 和加密库里的凭据，POSIX 下收紧到仅属主可读
    if os.name != "nt":
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key


class Settings:
    # ---- 基础 ----
    APP_NAME = os.getenv("CERTD_APP_NAME", "CertHub")
    VERSION = "1.0.0"
    SECRET_KEY = _load_secret_key()
    TOKEN_EXPIRE_MINUTES = int(os.getenv("CERTD_TOKEN_EXPIRE_MINUTES", "1440"))
    REFRESH_EXPIRE_MINUTES = int(os.getenv("CERTD_REFRESH_EXPIRE_MINUTES", "10080"))

    # ---- 数据库 ----
    DB_URL = os.getenv("CERTD_DB_URL", f"sqlite:///{DATA_DIR / 'certd.db'}")

    # ---- 服务 ----
    HOST = os.getenv("CERTD_HOST", "0.0.0.0")
    PORT = int(os.getenv("CERTD_PORT", "8000"))
    CORS_ORIGINS = os.getenv("CERTD_CORS_ORIGINS", "*").split(",")

    # ---- 默认管理员（仅首次初始化时创建）----
    ADMIN_USERNAME = os.getenv("CERTD_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("CERTD_ADMIN_PASSWORD", "123456")

    # ---- 时区 ----
    TIMEZONE = os.getenv("CERTD_TZ", "Asia/Shanghai")

    # ---- 流水线 ----
    PIPELINE_MAX_CONCURRENCY = int(os.getenv("CERTD_PIPELINE_CONCURRENCY", "3"))
    ACME_HTTP_TIMEOUT = int(os.getenv("CERTD_ACME_TIMEOUT", "60"))
    DNS_PROPAGATION_WAIT = int(os.getenv("CERTD_DNS_WAIT", "10"))


settings = Settings()
