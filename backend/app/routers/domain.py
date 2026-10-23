"""域名管理接口"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Domain, User

router = APIRouter(prefix="/api/domain", tags=["domain"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _serialize(r: Domain) -> dict:
    return {"id": r.id, "domain": r.domain, "verifyType": r.verify_type,
            "accessId": r.access_id, "remark": r.remark or "",
            "createTime": _fmt(r.create_time)}


@router.get("/list")
def list_domains(page: int = Depends(page_no), size: int = Query(20), keyword: str = "",
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Domain).filter(Domain.user_id == user.id)
    if keyword:
        query = query.filter(Domain.domain.like(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(Domain.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize(r) for r in rows], "total": total,
               "current": page, "size": size})


class DomainParams(BaseModel):
    domain: str
    verifyType: str = "dns"
    accessId: int = 0
    remark: str = ""


@router.post("")
def create_domain(params: DomainParams, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if not params.domain.strip():
        return fail("请填写域名")
    row = Domain(user_id=user.id, domain=params.domain.strip().lower(),
                 verify_type=params.verifyType, access_id=params.accessId,
                 remark=params.remark)
    db.add(row)
    db.commit()
    audit(db, user, "新增域名", params.domain)
    return ok({"id": row.id})


@router.put("/{domain_id}")
def update_domain(domain_id: int, params: DomainParams,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Domain, domain_id)
    if not row or row.user_id != user.id:
        return fail("域名不存在")
    row.domain = params.domain.strip().lower()
    row.verify_type = params.verifyType
    row.access_id = params.accessId
    row.remark = params.remark
    db.commit()
    return ok(True)


@router.delete("/{domain_id}")
def delete_domain(domain_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    row = db.get(Domain, domain_id)
    if not row or row.user_id != user.id:
        return fail("域名不存在")
    db.delete(row)
    db.commit()
    return ok(True)
