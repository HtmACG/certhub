"""通知渠道管理接口"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Notification, User
from ..plugins import NOTIFY_TYPES
from ..security import decrypt_json, encrypt_json, merge_secret
from ..services import notify

router = APIRouter(prefix="/api/notification", tags=["notification"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _serialize(row: Notification) -> dict:
    cfg = decrypt_json(row.config)
    return {
        "id": row.id, "type": row.type,
        "typeName": NOTIFY_TYPES.get(row.type, {}).get("name", row.type),
        "name": row.name, "enabled": bool(row.enabled),
        "isDefault": bool(row.is_default),
        # 同授权：明文返回，前端用「小眼睛」控制是否显示
        "config": cfg,
        "createTime": _fmt(row.create_time),
    }


@router.get("/list")
def list_notifications(page: int = Depends(page_no), size: int = Query(20),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    total = query.count()
    rows = query.order_by(Notification.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize(r) for r in rows], "total": total,
               "current": page, "size": size})


@router.get("/options")
def options(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Notification)
            .filter(Notification.user_id == user.id, Notification.enabled.is_(True))
            .order_by(Notification.is_default.desc(), Notification.id.desc()).all())
    return ok([{"id": r.id, "name": r.name,
                "typeName": NOTIFY_TYPES.get(r.type, {}).get("name", r.type)} for r in rows])


class NotifyParams(BaseModel):
    type: str
    name: str
    config: dict = {}
    enabled: bool = True
    isDefault: bool = False


@router.post("")
def create_notification(params: NotifyParams, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if params.type not in NOTIFY_TYPES:
        return fail("不支持的通知类型")
    if params.isDefault:
        db.query(Notification).filter(Notification.user_id == user.id).update({"is_default": False})
    row = Notification(user_id=user.id, type=params.type, name=params.name,
                       config=encrypt_json(params.config), enabled=params.enabled,
                       is_default=params.isDefault)
    db.add(row)
    db.commit()
    audit(db, user, "新增通知渠道", params.name)
    return ok({"id": row.id})


@router.put("/{notify_id}")
def update_notification(notify_id: int, params: NotifyParams,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Notification, notify_id)
    if not row or row.user_id != user.id:
        return fail("通知渠道不存在")
    if params.isDefault:
        db.query(Notification).filter(Notification.user_id == user.id).update({"is_default": False})
    old = decrypt_json(row.config)
    row.type = params.type
    row.name = params.name
    row.config = encrypt_json(merge_secret(old, params.config))
    row.enabled = params.enabled
    row.is_default = params.isDefault
    db.commit()
    return ok(True)


@router.delete("/{notify_id}")
def delete_notification(notify_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    row = db.get(Notification, notify_id)
    if not row or row.user_id != user.id:
        return fail("通知渠道不存在")
    db.delete(row)
    db.commit()
    return ok(True)


@router.post("/{notify_id}/test")
def test_notification(notify_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    row = db.get(Notification, notify_id)
    if not row or row.user_id != user.id:
        return fail("通知渠道不存在")
    try:
        notify.send(row.type, decrypt_json(row.config), "CertHub 测试通知",
                    "这是一条测试消息，收到说明通知渠道配置正确。")
        return ok({"success": True, "message": "发送成功"})
    except Exception as exc:
        return ok({"success": False, "message": str(exc)})
