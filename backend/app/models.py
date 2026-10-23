"""数据模型定义"""
import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> dt.datetime:
    return dt.datetime.now()


class TimestampMixin:
    create_time: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)


class User(Base, TimestampMixin):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(128), default="")
    nickname: Mapped[str | None] = mapped_column(String(64), default="")
    # admin / user
    role: Mapped[str] = mapped_column(String(20), default="user")
    status: Mapped[int] = mapped_column(Integer, default=1)  # 1 启用 0 禁用
    totp_secret: Mapped[str | None] = mapped_column(String(64), default="")
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    login_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Pipeline(Base, TimestampMixin):
    __tablename__ = "pi_pipeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="{}")
    remark: Mapped[str | None] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # cert_apply / cert_upload / custom
    type: Mapped[str] = mapped_column(String(20), default="cert_apply")
    keep_history_count: Mapped[int] = mapped_column(Integer, default=20)
    last_history_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    valid_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class History(Base, TimestampMixin):
    __tablename__ = "pi_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    pipeline_id: Mapped[int] = mapped_column(Integer, index=True)
    pipeline_title: Mapped[str] = mapped_column(String(128), default="")
    # 运行时的流水线快照
    pipeline: Mapped[str] = mapped_column(Text, default="{}")
    # running / success / failed / canceled
    status: Mapped[str] = mapped_column(String(20), default="running")
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
    # 任务执行结果快照 [{taskId,title,status,message,duration}]
    tasks: Mapped[str] = mapped_column(Text, default="[]")
    log: Mapped[str] = mapped_column(Text, default="")
    start_time: Mapped[dt.datetime | None] = mapped_column(DateTime, default=now)
    end_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Access(Base, TimestampMixin):
    __tablename__ = "sys_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    # dns / host / cloud / panel
    category: Mapped[str] = mapped_column(String(20), default="dns")
    type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[str] = mapped_column(Text, default="{}")  # 加密存储
    remark: Mapped[str | None] = mapped_column(String(255), default="")


class Certificate(Base, TimestampMixin):
    __tablename__ = "mon_cert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    pipeline_id: Mapped[int | None] = mapped_column(Integer, default=0)
    domains: Mapped[str] = mapped_column(Text, default="")
    cert_pem: Mapped[str] = mapped_column(Text, default="")
    key_pem: Mapped[str] = mapped_column(Text, default="")  # 加密存储
    issuer: Mapped[str | None] = mapped_column(String(255), default="")
    not_before: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    not_after: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="valid")  # valid / expired


class Domain(Base, TimestampMixin):
    __tablename__ = "cert_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    # dns / http / cname
    verify_type: Mapped[str] = mapped_column(String(20), default="dns")
    access_id: Mapped[int | None] = mapped_column(Integer, default=0)
    remark: Mapped[str | None] = mapped_column(String(255), default="")


class CnameRecord(Base, TimestampMixin):
    """CNAME 记录（域名 → 记录值 → 所在 DNS 授权）。

    记录本身可以只做本地登记（不绑定授权），也可以绑定 DNS 授权后
    一键写入 / 删除对端解析，并随时校验 CNAME 是否真的生效。
    """
    __tablename__ = "cert_cname_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    # 完整记录名，例如 www.example.com 或 _acme-challenge.example.com
    domain: Mapped[str] = mapped_column(String(255), index=True)
    # 主域名（子域名托管命中时以托管域名为准）
    main_domain: Mapped[str] = mapped_column(String(255), default="")
    # 相对主域名的主机记录，根域名用 @
    host_record: Mapped[str] = mapped_column(String(255), default="")
    # CNAME 记录值（目标域名）
    record_value: Mapped[str] = mapped_column(String(255), default="")
    # 写入用的 DNS 授权，0 表示只做本地登记
    access_id: Mapped[int | None] = mapped_column(Integer, default=0)
    # pending / valid / error / synced
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, default="")
    # 是否已写入对端 DNS
    synced: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), default="")


class SubDomain(Base, TimestampMixin):
    """子域名托管。

    登记后的子域名（例如 apps.example.com）在解析主域名、创建 CNAME 记录时
    会被当成一个独立的主域名，避免把记录写到上级域名下。
    """
    __tablename__ = "cert_sub_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    access_id: Mapped[int | None] = mapped_column(Integer, default=0)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str | None] = mapped_column(String(255), default="")


class SiteMonitor(Base, TimestampMixin):
    __tablename__ = "mon_site"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    url: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=443)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # ok / error / unknown
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    error: Mapped[str | None] = mapped_column(Text, default="")
    issuer: Mapped[str | None] = mapped_column(String(255), default="")
    not_before: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    expire_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_check_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Notification(Base, TimestampMixin):
    __tablename__ = "sys_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[str] = mapped_column(Text, default="{}")  # 加密存储
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "sys_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "sys_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    username: Mapped[str | None] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str | None] = mapped_column(Text, default="")
    ip: Mapped[str | None] = mapped_column(String(64), default="")
    create_time: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class ApiKey(Base, TimestampMixin):
    __tablename__ = "sys_api_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128))
    key_id: Mapped[str] = mapped_column(String(64), unique=True)
    secret: Mapped[str] = mapped_column(String(255))  # 加密存储
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
