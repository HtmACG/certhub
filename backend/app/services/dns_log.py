"""DNS 记录登记簿：把每次往对端 DNS 写入 / 清理的记录落到 cert_cname_record。

为什么要落库
------------
证书申请走 DNS 验证时，引擎会写一条 _acme-challenge.<域名> 的 TXT 记录，
验证通过立刻删掉。跑完之后（尤其是有多条流水线时）用户完全看不出
「这个域名到底有没有走过 DNS 记录、是哪条流水线写的」。所以这里把它记成
一张「域名 → 记录」的登记簿，和手动登记的 CNAME 一起在「DNS 记录」页展示。

行语义
------
- 同一条记录（user + 记录名 + 类型）反复写入只更新一行：累加 write_count、
  更新最近的值与时间，不新增脏数据；
- 引擎清理记录时把状态改成 cleaned（已清理）并记下清理时间，行本身保留作留痕；
- source 区分来源：acme（证书申请）/ cloud（云厂商免费证书）/ manual（手动登记）。

失败不影响主流程：留痕只是辅助信息，任何异常都吞掉。
"""
from __future__ import annotations

import datetime as dt

from ..db import SessionLocal
from ..models import CnameRecord


def _main_and_host(record_name: str, roots: list[str] | None = None) -> tuple[str, str]:
    """记录名 → (主域名, 主机记录)。子域名托管优先。"""
    from . import dns as dns_service

    name = (record_name or "").strip(".").lower()
    main = dns_service.main_domain_for(name, roots)
    if name == main:
        return main, "@"
    if name.endswith("." + main):
        return main, name[: -(len(main) + 1)]
    return main, name


def remember(
    user_id: int,
    *,
    record_name: str,
    record_value: str,
    record_type: str = "TXT",
    source: str = "acme",
    access_id: int = 0,
    pipeline_id: int = 0,
    pipeline_title: str = "",
    roots: list[str] | None = None,
) -> None:
    """登记一条刚写入对端 DNS 的记录（已存在就更新，不新增行）。"""
    record_name = (record_name or "").strip(".").lower()
    record_type = (record_type or "TXT").upper()
    if not user_id or not record_name:
        return
    db = SessionLocal()
    try:
        main, host = _main_and_host(record_name, roots)
        row = (db.query(CnameRecord)
                 .filter(CnameRecord.user_id == user_id,
                         CnameRecord.domain == record_name,
                         CnameRecord.record_type == record_type)
                 .first())
        if row is None:
            row = CnameRecord(user_id=user_id, domain=record_name,
                              main_domain=main, host_record=host,
                              record_type=record_type, source=source,
                              create_time=dt.datetime.now())
            db.add(row)
        row.record_value = record_value or ""
        row.main_domain = main
        row.host_record = host
        row.access_id = int(access_id or 0)
        row.source = source or "acme"
        row.pipeline_id = int(pipeline_id or 0)
        row.pipeline_title = pipeline_title or ""
        row.write_count = int(row.write_count or 0) + 1
        # 验证记录只读：状态用 written（已写入对端 DNS）
        row.status = "written"
        row.synced = True
        row.error = ""
        row.cleaned_time = None
        db.commit()
    except Exception:  # noqa: BLE001 - 留痕失败不影响签发
        db.rollback()
    finally:
        db.close()


def forget(user_id: int, *, record_name: str, record_type: str = "TXT",
           error: str = "") -> None:
    """把记录标成已清理（验证完成后引擎会删掉对端记录）。"""
    record_name = (record_name or "").strip(".").lower()
    if not user_id or not record_name:
        return
    db = SessionLocal()
    try:
        row = (db.query(CnameRecord)
                 .filter(CnameRecord.user_id == user_id,
                         CnameRecord.domain == record_name,
                         CnameRecord.record_type == (record_type or "TXT").upper())
                 .first())
        if row is None:
            return
        row.status = "error" if error else "cleaned"
        row.error = error or ""
        row.synced = False
        row.cleaned_time = dt.datetime.now()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
