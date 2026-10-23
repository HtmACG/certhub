"""用户与个人中心接口"""
from __future__ import annotations

import json

import pyotp
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, require_admin, page_no, site_name
from ..models import User
from ..security import hash_password, validate_password, verify_password

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/info")
def info(user: User = Depends(get_current_user)):
    return ok({
        "buttons": ["*"],
        "roles": ["R_SUPER"] if user.role == "admin" else ["R_USER"],
        "userId": user.id,
        "userName": user.username,
        "nickname": user.nickname or user.username,
        "email": user.email or "",
        "avatar": "",
        "role": user.role,
        "totpEnabled": bool(user.totp_enabled),
    })


class ProfileParams(BaseModel):
    nickname: str = ""
    email: str = ""


@router.put("/info")
def update_info(params: ProfileParams, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.get(User, user.id)
    row.nickname = params.nickname or row.username
    row.email = params.email
    db.commit()
    return ok(True)


class PasswordParams(BaseModel):
    oldPassword: str
    newPassword: str


@router.put("/password")
def change_password(params: PasswordParams, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    row = db.get(User, user.id)
    if not verify_password(params.oldPassword, row.password):
        # 原密码错也计入登录失败次数，避免拿着别人的会话暴力试密码
        return fail("原密码错误")
    error = validate_password(params.newPassword, row.username)
    if error:
        return fail(error)
    if params.oldPassword == params.newPassword:
        return fail("新密码不能与原密码相同")
    row.password = hash_password(params.newPassword)
    # 改密后清空失败计数与锁定状态
    row.login_fail_count = 0
    row.locked_until = None
    db.commit()
    audit(db, user, "修改密码")
    return ok(True)


# ---------------------------------------------------------------- 两步验证

@router.get("/2fa/secret")
def gen_2fa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """取（或首次生成）TOTP 密钥，返回二维码要用的 otpauth:// 链接。

    - 已开启两步验证时**沿用原密钥**：多台设备扫同一张码即可，不会把老设备踢掉；
    - issuer 用站点名称，「系统设置 → 站点信息」里改了名字，App 里显示的也就跟着变。
    """
    row = db.get(User, user.id)
    secret = row.totp_secret or pyotp.random_base32()
    row.totp_secret = secret
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=row.username,
                                              issuer_name=site_name(db))
    return ok({"secret": secret, "uri": uri,
               "account": row.username, "enabled": bool(row.totp_enabled)})


class CodeParams(BaseModel):
    code: str


@router.post("/2fa/enable")
def enable_2fa(params: CodeParams, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = db.get(User, user.id)
    if not row.totp_secret:
        return fail("请先获取密钥")
    if not pyotp.TOTP(row.totp_secret).verify(params.code, valid_window=1):
        return fail("验证码错误")
    row.totp_enabled = True
    db.commit()
    audit(db, user, "开启两步验证")
    return ok(True)


@router.post("/2fa/disable")
def disable_2fa(params: CodeParams, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.get(User, user.id)
    if row.totp_enabled and not pyotp.TOTP(row.totp_secret or "").verify(params.code, valid_window=1):
        return fail("验证码错误")
    row.totp_enabled = False
    db.commit()
    audit(db, user, "关闭两步验证")
    return ok(True)


# ---------------------------------------------------------------- 用户管理（管理员）

@router.get("/list")
def list_users(page: int = Depends(page_no), size: int = Query(10), keyword: str = "",
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(User)
    if keyword:
        query = query.filter(or_(User.username.like(f"%{keyword}%"),
                                 User.nickname.like(f"%{keyword}%")))
    total = query.count()
    rows = query.order_by(User.id.asc()).offset((page - 1) * size).limit(size).all()
    records = [{
        "id": r.id, "userName": r.username, "nickname": r.nickname, "email": r.email,
        "role": r.role, "status": r.status,
        "totpEnabled": r.totp_enabled,
        "lastLoginTime": r.last_login_time.strftime("%Y-%m-%d %H:%M:%S") if r.last_login_time else "",
        "createTime": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
    } for r in rows]
    return ok({"records": records, "total": total, "current": page, "size": size})


class UserParams(BaseModel):
    userName: str
    password: str = ""
    nickname: str = ""
    email: str = ""
    role: str = "user"
    status: int = 1


@router.post("")
def create_user(params: UserParams, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == params.userName).first():
        return fail("用户名已存在")
    error = validate_password(params.password, params.userName)
    if error:
        return fail(error)
    row = User(username=params.userName, password=hash_password(params.password),
               nickname=params.nickname or params.userName, email=params.email,
               role=params.role, status=params.status)
    db.add(row)
    db.commit()
    audit(db, admin, "新增用户", params.userName)
    return ok({"id": row.id})


@router.put("/{user_id}")
def update_user(user_id: int, params: UserParams,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(User, user_id)
    if not row:
        return fail("用户不存在")
    row.nickname = params.nickname or row.nickname
    row.email = params.email
    row.role = params.role
    row.status = params.status
    if params.password:
        error = validate_password(params.password, row.username)
        if error:
            return fail(error)
        row.password = hash_password(params.password)
        # 重置密码后解锁，避免用户改了密码还是被锁
        row.login_fail_count = 0
        row.locked_until = None
    db.commit()
    audit(db, admin, "修改用户" + ("（含重置密码）" if params.password else ""), row.username)
    return ok(True)


@router.delete("/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if user_id == admin.id:
        return fail("不能删除当前登录账号")
    row = db.get(User, user_id)
    if not row:
        return fail("用户不存在")
    db.delete(row)
    db.commit()
    audit(db, admin, "删除用户", row.username)
    return ok(True)
