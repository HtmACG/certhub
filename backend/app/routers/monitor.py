"""站点证书监控接口"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import SiteMonitor, User
from ..services.scheduler import check_site

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _serialize(r: SiteMonitor) -> dict:
    days = (r.expire_time - dt.datetime.now()).days if r.expire_time else None
    return {
        "id": r.id, "url": r.url, "port": r.port,
        "enabled": bool(r.enabled), "notifyEnabled": bool(r.notify_enabled),
        "status": r.status, "error": r.error or "", "issuer": r.issuer or "",
        "notBefore": _fmt(r.not_before), "expireTime": _fmt(r.expire_time),
        "daysLeft": days, "lastCheckTime": _fmt(r.last_check_time),
    }


@router.get("/site/list")
def list_sites(page: int = Depends(page_no), size: int = Query(10), keyword: str = "",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(SiteMonitor).filter(SiteMonitor.user_id == user.id)
    if keyword:
        query = query.filter(SiteMonitor.url.like(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(SiteMonitor.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize(r) for r in rows], "total": total,
               "current": page, "size": size})


class SiteParams(BaseModel):
    url: str
    port: int = 443
    enabled: bool = True
    notifyEnabled: bool = True


@router.post("/site")
def create_site(params: SiteParams, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    url = params.url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    row = SiteMonitor(user_id=user.id, url=url, port=params.port,
                      enabled=params.enabled, notify_enabled=params.notifyEnabled)
    db.add(row)
    db.commit()
    audit(db, user, "新增站点监控", url)
    return ok({"id": row.id})


@router.put("/site/{site_id}")
def update_site(site_id: int, params: SiteParams, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.get(SiteMonitor, site_id)
    if not row or row.user_id != user.id:
        return fail("站点不存在")
    row.url = params.url
    row.port = params.port
    row.enabled = params.enabled
    row.notify_enabled = params.notifyEnabled
    db.commit()
    return ok(True)


@router.delete("/site/{site_id}")
def delete_site(site_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.get(SiteMonitor, site_id)
    if not row or row.user_id != user.id:
        return fail("站点不存在")
    db.delete(row)
    db.commit()
    return ok(True)


@router.post("/site/{site_id}/check")
def check_now(site_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    row = db.get(SiteMonitor, site_id)
    if not row or row.user_id != user.id:
        return fail("站点不存在")
    try:
        info = check_site(row.url, row.port or 443)
        row.status = "ok"
        row.error = ""
        row.issuer = info["issuer"]
        row.not_before = info["not_before"]
        row.expire_time = info["not_after"]
        row.last_check_time = dt.datetime.now()
        db.commit()
        return ok(_serialize(row))
    except Exception as exc:
        row.status = "error"
        row.error = str(exc)[:300]
        row.last_check_time = dt.datetime.now()
        db.commit()
        return ok(_serialize(row))
