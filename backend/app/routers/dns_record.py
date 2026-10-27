"""CNAME 记录管理与子域名托管接口

CNAME 记录：把「待申请证书的域名」固定 CNAME 到自家代理域名下，
之后 ACME 的 TXT 记录写到代理域名即可，解决域名服务商不被支持的问题。

子域名托管：免费二级域名（sub.example.com）在服务商那边是独立 zone，
登记后解析记录时以它为主域名，不再错误地写到 example.com 下。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Access, CnameRecord, SubDomain, User, now
from ..security import decrypt_json
from ..services import dns as dns_service

router = APIRouter(prefix="/api/dns", tags=["dns"])

_LABEL_RE = re.compile(r"^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$")


def _fmt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _norm(value: str) -> str:
    return (value or "").strip().lower().lstrip("*.").strip(".")


def _valid_domain(value: str) -> bool:
    labels = value.split(".")
    return len(labels) >= 2 and all(_LABEL_RE.match(label) for label in labels)


def _hosted_roots(db: Session, user: User) -> list[str]:
    rows = (db.query(SubDomain)
            .filter(SubDomain.user_id == user.id, SubDomain.disabled.is_(False))
            .all())
    return [row.domain for row in rows]


def _main_domain(db: Session, user: User, domain: str) -> str:
    return dns_service.main_domain_for(domain, _hosted_roots(db, user))


def _host_record(main: str, domain: str) -> str:
    if domain == main:
        return "@"
    if domain.endswith("." + main):
        return domain[: -(len(main) + 1)]
    return domain


def _dns_access(db: Session, user: User, access_id: int | None):
    """返回 (授权行, 解密配置, 错误说明)。access_id 为空表示只做本地登记。"""
    if not access_id:
        return None, {}, ""
    row = db.get(Access, int(access_id))
    if not row or row.user_id != user.id:
        return None, {}, "DNS 授权不存在或无权限"
    if row.type not in dns_service.PROVIDERS:
        return None, {}, "所选授权不是 DNS 服务商，无法写入解析记录"
    return row, decrypt_json(row.config), ""


def _serialize_cname(row: CnameRecord) -> dict:
    return {
        "id": row.id, "domain": row.domain, "mainDomain": row.main_domain,
        "hostRecord": row.host_record, "recordValue": row.record_value,
        # CNAME（手动登记）/ TXT（证书申请自动写入的验证记录）
        "recordType": (row.record_type or "CNAME").upper(),
        # manual / acme / cloud：来源不同，操作按钮也不同（自动的只读）
        "source": row.source or "manual",
        "pipelineId": row.pipeline_id or 0,
        "pipelineTitle": row.pipeline_title or "",
        "writeCount": int(row.write_count or 0),
        "cleanedTime": _fmt(row.cleaned_time),
        "accessId": row.access_id or 0, "status": row.status,
        "error": row.error or "", "synced": bool(row.synced),
        "verifyTime": _fmt(row.verify_time), "remark": row.remark or "",
        "createTime": _fmt(row.create_time),
        # updateTime 是最近一次写入 / 清理的时间，页面上显示成「最近写入」
        "updateTime": _fmt(row.update_time),
    }


def _write_to_dns(db: Session, user: User, row: CnameRecord) -> None:
    """把记录写入对端 DNS：同名记录已存在就改成目标值，避免重复添加报错。"""
    access_row, cfg, error = _dns_access(db, user, row.access_id)
    if error:
        row.status = "error"
        row.error = error
        row.synced = False
        db.commit()
        return
    if not access_row:
        row.status = "pending"
        row.error = "未绑定 DNS 授权，仅本地登记"
        row.synced = False
        db.commit()
        return
    try:
        records = dns_service.list_records(access_row.type, cfg, row.main_domain, "CNAME")
        same = [item for item in records
                if (item.get("host") or "").lower() == (row.host_record or "@").lower()]
        if same:
            dns_service.update_record(access_row.type, cfg, row.main_domain,
                                      row.host_record, "CNAME", row.record_value)
        else:
            dns_service.add_record(access_row.type, cfg, row.main_domain,
                                   row.host_record, "CNAME", row.record_value)
        row.synced = True
        row.status = "synced"
        row.error = ""
    except Exception as exc:  # noqa: BLE001 - 厂商错误统一转成一行中文
        row.synced = False
        row.status = "error"
        row.error = str(exc)
    db.commit()


# ---------------------------------------------------------------- CNAME 记录

@router.get("/cname/list")
def list_cname(page: int = Depends(page_no), size: int = Query(20), keyword: str = "",
               status: str = "", source: str = "", record_type: str = "",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """DNS 记录列表：手动登记的 CNAME + 证书申请自动写入的验证记录。

    两类行靠 source 区分（manual / acme / cloud），自动的只读，页面上不给同步 / 校验按钮。
    """
    query = db.query(CnameRecord).filter(CnameRecord.user_id == user.id)
    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(CnameRecord.domain.like(like),
                                 CnameRecord.record_value.like(like),
                                 CnameRecord.remark.like(like),
                                 CnameRecord.pipeline_title.like(like)))
    if status:
        query = query.filter(CnameRecord.status == status)
    if source:
        query = query.filter(CnameRecord.source == source)
    if record_type:
        query = query.filter(CnameRecord.record_type == record_type.upper())
    total = query.count()
    rows = query.order_by(CnameRecord.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize_cname(row) for row in rows], "total": total,
               "current": page, "size": size})


class CnameParams(BaseModel):
    domain: str
    recordValue: str = ""
    accessId: int = 0
    remark: str = ""
    sync: bool = False


@router.post("/cname")
def create_cname(params: CnameParams, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    domain = _norm(params.domain)
    value = _norm(params.recordValue)
    if not domain or not _valid_domain(domain):
        return fail("请填写正确的域名，例如 _acme-challenge.example.com")
    if not value or not _valid_domain(value):
        return fail("请填写正确的 CNAME 记录值，例如 abc123.cname.example.net")
    if value == domain:
        return fail("记录值不能与域名相同")
    if (db.query(CnameRecord)
            .filter(CnameRecord.user_id == user.id,
                    CnameRecord.domain == domain,
                    CnameRecord.record_type == "CNAME").first()):
        return fail(f"{domain} 的 CNAME 记录已存在")

    main = _main_domain(db, user, domain)
    row = CnameRecord(user_id=user.id, domain=domain, main_domain=main,
                      host_record=_host_record(main, domain), record_value=value,
                      access_id=params.accessId or 0, status="pending",
                      record_type="CNAME", source="manual",
                      remark=params.remark)
    db.add(row)
    db.commit()
    db.refresh(row)
    if params.sync:
        _write_to_dns(db, user, row)
    audit(db, user, "新增 CNAME 记录", f"{domain} -> {value}")
    return ok(_serialize_cname(row))


@router.put("/cname/{record_id}")
def update_cname(record_id: int, params: CnameParams,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CnameRecord, record_id)
    if not row or row.user_id != user.id:
        return fail("CNAME 记录不存在")
    if (row.source or "manual") != "manual" or (row.record_type or "CNAME").upper() != "CNAME":
        return fail("这是证书申请自动登记的验证记录，只读；需要修改请在对应的流水线里改")
    domain = _norm(params.domain)
    value = _norm(params.recordValue)
    if not domain or not _valid_domain(domain):
        return fail("请填写正确的域名，例如 _acme-challenge.example.com")
    if not value or not _valid_domain(value):
        return fail("请填写正确的 CNAME 记录值，例如 abc123.cname.example.net")
    if value == domain:
        return fail("记录值不能与域名相同")
    other = (db.query(CnameRecord)
             .filter(CnameRecord.user_id == user.id, CnameRecord.domain == domain,
                     CnameRecord.id != row.id).first())
    if other:
        return fail(f"{domain} 的 CNAME 记录已存在")

    changed = (row.domain != domain or row.record_value != value
               or (row.access_id or 0) != (params.accessId or 0))
    row.domain = domain
    row.record_value = value
    row.access_id = params.accessId or 0
    row.remark = params.remark
    row.main_domain = _main_domain(db, user, domain)
    row.host_record = _host_record(row.main_domain, domain)
    if changed:
        row.synced = False
        row.status = "pending"
        row.error = ""
    db.commit()
    if params.sync and changed:
        _write_to_dns(db, user, row)
    audit(db, user, "修改 CNAME 记录", f"{domain} -> {value}")
    return ok(_serialize_cname(row))


@router.delete("/cname/{record_id}")
def delete_cname(record_id: int, remote: bool = Query(False),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CnameRecord, record_id)
    if not row or row.user_id != user.id:
        return fail("CNAME 记录不存在")
    domain, value = row.domain, row.record_value
    # 自动登记的验证记录对端已经清理过，remote 只对手动 CNAME 生效
    if remote and row.synced and (row.source or "manual") == "manual" and \
            (row.record_type or "CNAME").upper() == "CNAME":
        access_row, cfg, error = _dns_access(db, user, row.access_id)
        if access_row:
            try:
                dns_service.delete_record(access_row.type, cfg, row.main_domain,
                                          row.host_record, "CNAME", value)
            except Exception as exc:  # noqa: BLE001
                return fail(f"删除对端解析失败：{exc}")
        elif error:
            return fail(error)
    db.delete(row)
    db.commit()
    audit(db, user, "删除 CNAME 记录", domain)
    return ok(True)


@router.post("/cname/{record_id}/sync")
def sync_cname(record_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = db.get(CnameRecord, record_id)
    if not row or row.user_id != user.id:
        return fail("CNAME 记录不存在")
    if (row.source or "manual") != "manual":
        return fail("这是证书申请自动登记的验证记录，由流水线写入 / 清理，不需要手动同步")
    if not row.access_id:
        return fail("请先为该记录绑定 DNS 授权")
    _write_to_dns(db, user, row)
    audit(db, user, "同步 CNAME 记录", row.domain)
    if row.status == "error":
        return fail(row.error or "同步失败")
    return ok(_serialize_cname(row))


@router.post("/cname/{record_id}/verify")
def verify_cname(record_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    row = db.get(CnameRecord, record_id)
    if not row or row.user_id != user.id:
        return fail("CNAME 记录不存在")
    if (row.record_type or "CNAME").upper() != "CNAME":
        return fail("TXT 验证记录是临时记录，验证完就清理，不做 CNAME 校验")
    passed, actual, error = dns_service.check_cname(row.domain, row.record_value)
    row.verify_time = now()
    row.status = "valid" if passed else "error"
    row.error = "" if passed else error
    db.commit()
    return ok({"success": passed, "actual": actual, "message": error or "CNAME 指向正确",
               "record": _serialize_cname(row)})


class CheckParams(BaseModel):
    domain: str
    expected: str


@router.post("/cname/check")
def check_cname_value(params: CheckParams, user: User = Depends(get_current_user)):
    """临时校验一条 CNAME，不落库（新增记录前先确认手填的解析已生效）。"""
    domain = _norm(params.domain)
    expected = _norm(params.expected)
    if not domain or not expected:
        return fail("请填写域名与记录值")
    passed, actual, error = dns_service.check_cname(domain, expected)
    return ok({"success": passed, "actual": actual,
               "message": error or "CNAME 指向正确"})


# ---------------------------------------------------------------- 子域名托管

def _serialize_sub(row: SubDomain) -> dict:
    return {"id": row.id, "domain": row.domain, "accessId": row.access_id or 0,
            "disabled": bool(row.disabled), "remark": row.remark or "",
            "createTime": _fmt(row.create_time)}


@router.get("/subdomain/list")
def list_subdomain(page: int = Depends(page_no), size: int = Query(20), keyword: str = "",
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(SubDomain).filter(SubDomain.user_id == user.id)
    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(SubDomain.domain.like(like), SubDomain.remark.like(like)))
    total = query.count()
    rows = query.order_by(SubDomain.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize_sub(row) for row in rows], "total": total,
               "current": page, "size": size})


class SubDomainParams(BaseModel):
    domain: str
    accessId: int = 0
    disabled: bool = False
    remark: str = ""


@router.post("/subdomain")
def create_subdomain(params: SubDomainParams, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    domain = _norm(params.domain)
    if not domain or not _valid_domain(domain):
        return fail("请填写正确的子域名，例如 sub.example.com")
    if db.query(SubDomain).filter(SubDomain.user_id == user.id,
                                  SubDomain.domain == domain).first():
        return fail(f"{domain} 已在托管列表中")
    row = SubDomain(user_id=user.id, domain=domain, access_id=params.accessId or 0,
                    disabled=params.disabled, remark=params.remark)
    db.add(row)
    db.commit()
    audit(db, user, "新增子域名托管", domain)
    return ok(_serialize_sub(row))


@router.put("/subdomain/{sub_id}")
def update_subdomain(sub_id: int, params: SubDomainParams,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SubDomain, sub_id)
    if not row or row.user_id != user.id:
        return fail("子域名不存在")
    domain = _norm(params.domain)
    if not domain or not _valid_domain(domain):
        return fail("请填写正确的子域名，例如 sub.example.com")
    other = (db.query(SubDomain)
             .filter(SubDomain.user_id == user.id, SubDomain.domain == domain,
                     SubDomain.id != row.id).first())
    if other:
        return fail(f"{domain} 已在托管列表中")
    row.domain = domain
    row.access_id = params.accessId or 0
    row.disabled = params.disabled
    row.remark = params.remark
    db.commit()
    audit(db, user, "修改子域名托管", domain)
    return ok(_serialize_sub(row))


@router.delete("/subdomain/{sub_id}")
def delete_subdomain(sub_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    row = db.get(SubDomain, sub_id)
    if not row or row.user_id != user.id:
        return fail("子域名不存在")
    db.delete(row)
    db.commit()
    audit(db, user, "删除子域名托管", row.domain)
    return ok(True)


@router.post("/subdomain/{sub_id}/verify")
def verify_subdomain(sub_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    row = db.get(SubDomain, sub_id)
    if not row or row.user_id != user.id:
        return fail("子域名不存在")
    access_row, cfg, error = _dns_access(db, user, row.access_id)
    if error:
        return fail(error)
    passed, ns_list, message = dns_service.check_subdomain(
        row.domain,
        access_row.type if access_row else "",
        cfg if access_row else None,
    )
    return ok({"success": passed, "ns": ns_list,
               "message": message or f"NS 已委派到 {', '.join(ns_list)}"})
