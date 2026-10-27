"""数据库初始化（SQLAlchemy 2.x）"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {}
if settings.DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.DB_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)


if settings.DB_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：请求级数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#: 老表补列：create_all 只会建缺失的表，不会给已存在的表加列。
#: 新增字段统一登记在这里，启动时幂等地 ALTER TABLE 补上（SQLite 也支持 ADD COLUMN）。
_COLUMN_PATCHES: dict[str, list[tuple[str, str]]] = {
    "cert_cname_record": [
        ("record_type", "VARCHAR(10) DEFAULT 'CNAME'"),
        ("source", "VARCHAR(20) DEFAULT 'manual'"),
        ("pipeline_id", "INTEGER DEFAULT 0"),
        ("pipeline_title", "VARCHAR(255) DEFAULT ''"),
        ("write_count", "INTEGER DEFAULT 0"),
        ("cleaned_time", "DATETIME"),
    ],
}


def _patch_columns() -> None:
    """给已存在的老表补新列（幂等）。失败不阻断启动，只打一行日志。"""
    from sqlalchemy import inspect as sa_inspect, text

    try:
        inspector = sa_inspect(engine)
        with engine.begin() as conn:
            for table, columns in _COLUMN_PATCHES.items():
                if not inspector.has_table(table):
                    continue
                existing = {col["name"] for col in inspector.get_columns(table)}
                for name, ddl in columns:
                    if name in existing:
                        continue
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    except Exception as exc:  # noqa: BLE001 - 补列失败不该让服务起不来
        print(f"[db] 补列失败（忽略）：{exc}")


def init_db():
    from . import models  # noqa: F401  注册所有模型

    Base.metadata.create_all(bind=engine)
    _patch_columns()
