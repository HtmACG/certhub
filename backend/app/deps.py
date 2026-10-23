"""FastAPI 依赖与通用响应封装"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_token


def ok(data: Any = None, msg: str = "") -> dict:
    return {"code": 200, "msg": msg, "data": data}


def fail(msg: str, code: int = 400) -> dict:
    return {"code": code, "msg": msg, "data": None}


class BizError(Exception):
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(authorization)
    payload = decode_token(token) if token else None
    if not payload or payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, int(payload["sub"]))
    if not user or user.status != 1:
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")
    return user


def get_bind_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """强制绑定两步验证时用的临时身份。

    这类令牌只能调绑定接口，拿不到正常业务接口的权限，
    避免「系统开了强制 2FA 但用户还没绑定」被当成已登录。
    """
    token = _extract_token(authorization)
    payload = decode_token(token) if token else None
    if not payload or payload.get("typ") != "bind":
        raise HTTPException(status_code=401, detail="绑定会话已过期，请重新登录")
    user = db.get(User, int(payload["sub"]))
    if not user or user.status != 1:
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def page_no(page: int = Query(1, ge=1), current: int = Query(0, ge=0)) -> int:
    """页码参数：前端的 useTable 发的是 `current`，后端历史接口用 `page`。

    两边都认，避免出现「点了第 2 页列表还是第 1 页」这种分页器失效的问题。
    """
    if current > 0:
        return current
    return page


def page_size(size: int = Query(10, ge=1, le=500)) -> int:
    return size


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def site_name(db: Session, fallback: str = "CertHub") -> str:
    """站点名称（系统设置 → 站点信息），给两步验证的 issuer 等展示场景用。

    读不到 / 没填时回退，调用方拿到的永远是可显示的名字。
    """
    from .defaults import merge_defaults
    from .models import Setting

    row = db.get(Setting, "site")
    try:
        stored = json.loads(row.value) if row else {}
    except Exception:
        stored = {}
    name = str(merge_defaults("site", stored).get("name") or "").strip()
    return name or fallback


def audit(db: Session, user: User | None, action: str, detail: str = "", ip: str = ""):
    from .models import AuditLog

    db.add(AuditLog(user_id=user.id if user else 0,
                    username=user.username if user else "",
                    action=action, detail=detail[:2000], ip=ip,
                    create_time=dt.datetime.now()))
    db.commit()
