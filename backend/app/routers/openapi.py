"""Open API：密钥管理与外部触发"""
from __future__ import annotations

import datetime as dt
import hmac
import secrets

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok
from ..models import ApiKey, Certificate, Pipeline, User
from ..security import decrypt_json, encrypt_json
from ..services.engine import run_pipeline_async

router = APIRouter(tags=["open"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


# ---------------------------------------------------------------- 密钥管理（登录态）

@router.get("/api/open/keys")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.id.desc()).all()
    return ok([{
        "id": r.id, "name": r.name, "keyId": r.key_id,
        "enabled": bool(r.enabled),
        "lastUsedTime": _fmt(r.last_used_time),
        "createTime": _fmt(r.create_time),
    } for r in rows])


class KeyParams(BaseModel):
    name: str


@router.post("/api/open/keys")
def create_key(params: KeyParams, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    key_id = "ck_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    row = ApiKey(user_id=user.id, name=params.name, key_id=key_id,
                 secret=encrypt_json(secret), enabled=True)
    db.add(row)
    db.commit()
    audit(db, user, "创建 API 密钥", params.name)
    return ok({"id": row.id, "keyId": key_id, "secret": secret})


@router.delete("/api/open/keys/{key_id}")
def delete_key(key_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        return fail("密钥不存在")
    db.delete(row)
    db.commit()
    return ok(True)


# ---------------------------------------------------------------- 对外接口（密钥鉴权）

def _auth(db: Session, key: str, secret: str) -> User | None:
    if not key or not secret:
        return None
    row = db.query(ApiKey).filter(ApiKey.key_id == key, ApiKey.enabled.is_(True)).first()
    if not row:
        return None
    if not hmac.compare_digest(decrypt_json(row.secret) or "", secret):
        return None
    row.last_used_time = dt.datetime.now()
    db.commit()
    return db.get(User, row.user_id)


@router.get("/api/open/v1/pipelines")
def open_list_pipelines(x_api_key: str = Header(default=""),
                        x_api_secret: str = Header(default=""),
                        db: Session = Depends(get_db)):
    user = _auth(db, x_api_key, x_api_secret)
    if not user:
        return fail("鉴权失败", 401)
    rows = db.query(Pipeline).filter(Pipeline.user_id == user.id).all()
    return ok([{"id": r.id, "title": r.title, "disabled": bool(r.disabled),
                "lastHistoryTime": _fmt(r.last_history_time)} for r in rows])


@router.post("/api/open/v1/pipelines/{pipeline_id}/run")
def open_run_pipeline(pipeline_id: int, x_api_key: str = Header(default=""),
                      x_api_secret: str = Header(default=""),
                      db: Session = Depends(get_db)):
    user = _auth(db, x_api_key, x_api_secret)
    if not user:
        return fail("鉴权失败", 401)
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在", 404)
    run_pipeline_async(p.id, "openapi", user.id)
    return ok({"pipelineId": p.id, "status": "started"})


@router.get("/api/open/v1/certs")
def open_list_certs(x_api_key: str = Header(default=""),
                    x_api_secret: str = Header(default=""),
                    db: Session = Depends(get_db)):
    user = _auth(db, x_api_key, x_api_secret)
    if not user:
        return fail("鉴权失败", 401)
    rows = (db.query(Certificate).filter(Certificate.user_id == user.id)
            .order_by(Certificate.id.desc()).limit(100).all())
    return ok([{
        "id": r.id, "domains": r.domains.split(",") if r.domains else [],
        "issuer": r.issuer, "notAfter": _fmt(r.not_after),
        "createTime": _fmt(r.create_time),
    } for r in rows])


@router.get("/api/open/v1/certs/{cert_id}")
def open_get_cert(cert_id: int, x_api_key: str = Header(default=""),
                  x_api_secret: str = Header(default=""),
                  db: Session = Depends(get_db)):
    user = _auth(db, x_api_key, x_api_secret)
    if not user:
        return fail("鉴权失败", 401)
    row = db.get(Certificate, cert_id)
    if not row or row.user_id != user.id:
        return fail("证书不存在", 404)
    return ok({
        "id": row.id, "domains": row.domains.split(",") if row.domains else [],
        "cert": row.cert_pem, "key": decrypt_json(row.key_pem),
        "notAfter": _fmt(row.not_after), "issuer": row.issuer,
    })
