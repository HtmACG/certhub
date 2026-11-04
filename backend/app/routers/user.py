"""用户与个人中心接口"""
from __future__ import annotations

import base64
import io
import json

import pyotp
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, require_admin, page_no, permissions_of, site_name
from ..models import User, UserGroup
from ..permissions import PERMISSIONS, normalize
from ..security import hash_password, validate_password, verify_password

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/info")
def info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    effective = permissions_of(user, db)
    return ok({
        "buttons": ["*"],
        "roles": ["R_SUPER"] if user.role == "admin" else ["R_USER"],
        "userId": user.id,
        "userName": user.username,
        "nickname": user.nickname or user.username,
        "email": user.email or "",
        "avatar": "",
        "role": user.role,
        "isAdmin": user.role == "admin",
        # 管理员给全部权限键，前端统一按 permissions 判断
        "permissions": [item["key"] for item in PERMISSIONS] if "*" in effective else sorted(effective),
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

def _qr_data_url(text: str) -> str:
    """把 otpauth:// 链接画成二维码，直接给前端 <img src> 用（内网不依赖任何外部服务）。"""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()


@router.get("/2fa/secret")
def gen_2fa(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """取（或首次生成）TOTP 密钥，返回二维码要用的 otpauth:// 链接和二维码图。

    - 已开启两步验证时**沿用原密钥**：多台设备扫同一张码即可，不会把老设备踢掉；
    - issuer 用站点名称，「系统设置 → 站点信息」里改了名字，App 里显示的也就跟着变。
    """
    row = db.get(User, user.id)
    secret = row.totp_secret or pyotp.random_base32()
    row.totp_secret = secret
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=row.username,
                                              issuer_name=site_name(db))
    return ok({"secret": secret, "uri": uri, "qr": _qr_data_url(uri),
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


# ---------------------------------------------------------------- 用户组（管理员）

class GroupParams(BaseModel):
    name: str
    remark: str = ""
    permissions: list[str] = []


@router.get("/permissions")
def permission_catalog(_: User = Depends(require_admin)):
    """可选的功能权限目录，前端用它渲染勾选框。"""
    return ok(PERMISSIONS)


@router.get("/groups")
def list_groups(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(UserGroup).order_by(UserGroup.id.asc()).all()
    counts = dict(db.query(User.group_id, func.count(User.id)).group_by(User.group_id).all())
    def _keys(row: UserGroup) -> list[str]:
        try:
            return normalize(json.loads(row.permissions or "[]"))
        except Exception:
            return []

    return ok([
        {"id": row.id, "name": row.name, "remark": row.remark or "",
         "permissions": _keys(row),
         "userCount": int(counts.get(row.id, 0))}
        for row in rows
    ])


@router.post("/groups")
def create_group(params: GroupParams, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    name = params.name.strip()
    if not name:
        return fail("请填写用户组名称")
    if db.query(UserGroup).filter(UserGroup.name == name).first():
        return fail("用户组已存在")
    row = UserGroup(name=name, remark=params.remark.strip(),
                    permissions=json.dumps(normalize(params.permissions), ensure_ascii=False))
    db.add(row)
    db.commit()
    audit(db, admin, "新增用户组", name)
    return ok({"id": row.id})


@router.put("/groups/{group_id}")
def update_group(group_id: int, params: GroupParams,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(UserGroup, group_id)
    if not row:
        return fail("用户组不存在")
    name = params.name.strip()
    if not name:
        return fail("请填写用户组名称")
    exists = db.query(UserGroup).filter(UserGroup.name == name, UserGroup.id != group_id).first()
    if exists:
        return fail("用户组已存在")
    row.name = name
    row.remark = params.remark.strip()
    row.permissions = json.dumps(normalize(params.permissions), ensure_ascii=False)
    db.commit()
    audit(db, admin, "修改用户组", name)
    return ok(True)


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    row = db.get(UserGroup, group_id)
    if not row:
        return fail("用户组不存在")
    # 组里的用户退回「未分组」，不删账号
    db.query(User).filter(User.group_id == group_id).update({User.group_id: 0})
    db.delete(row)
    db.commit()
    audit(db, admin, "删除用户组", row.name)
    return ok(True)


# ---------------------------------------------------------------- 用户管理（管理员）

@router.get("/list")
def list_users(page: int = Depends(page_no), size: int = Query(10), keyword: str = "",
               groupId: int = Query(0),
               admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(User)
    if keyword:
        query = query.filter(or_(User.username.like(f"%{keyword}%"),
                                 User.nickname.like(f"%{keyword}%")))
    if groupId:
        query = query.filter(User.group_id == groupId)
    total = query.count()
    rows = query.order_by(User.id.asc()).offset((page - 1) * size).limit(size).all()
    groups = {g.id: g.name for g in db.query(UserGroup).all()}
    records = [{
        "id": r.id, "userName": r.username, "nickname": r.nickname, "email": r.email,
        "role": r.role, "status": r.status,
        "groupId": r.group_id or 0,
        "groupName": groups.get(r.group_id or 0, ""),
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
    groupId: int = 0


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
               role=params.role, status=params.status, group_id=params.groupId)
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
    row.group_id = params.groupId
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
