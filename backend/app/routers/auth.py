"""认证接口"""
from __future__ import annotations

import datetime as dt
import json

import pyotp
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import audit, fail, get_bind_user, get_current_user, ok, site_name
from ..models import Setting, User
from ..security import create_token, decode_token, hash_password, validate_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginParams(BaseModel):
    userName: str
    password: str
    code: str = ""


class RegisterParams(BaseModel):
    userName: str
    password: str
    email: str = ""
    code: str = ""


def _security_setting(db: Session) -> dict:
    row = db.get(Setting, "security")
    try:
        return json.loads(row.value) if row else {}
    except Exception:
        return {}


@router.post("/login")
def login(params: LoginParams, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == params.userName).first()
    ip = request.client.host if request.client else ""

    if not user:
        return fail("账号或密码错误")

    if user.locked_until and user.locked_until > dt.datetime.now():
        left = int((user.locked_until - dt.datetime.now()).total_seconds() // 60) + 1
        return fail(f"登录失败次数过多，请 {left} 分钟后再试")

    if not verify_password(params.password, user.password):
        sec = _security_setting(db)
        limit = int(sec.get("loginFailLimit") or 5)
        user.login_fail_count = (user.login_fail_count or 0) + 1
        if limit and user.login_fail_count >= limit:
            user.locked_until = dt.datetime.now() + dt.timedelta(minutes=int(sec.get("lockMinutes") or 10))
            user.login_fail_count = 0
        db.commit()
        return fail("账号或密码错误")

    if user.status != 1:
        return fail("账号已被禁用，请联系管理员")

    if user.totp_enabled:
        # 前端不知道账号有没有开 2FA，所以先回一个 need2fa，让它把验证码框露出来
        if not params.code:
            return ok({"need2fa": True, "userName": user.username})
        totp = pyotp.TOTP(user.totp_secret or "")
        if not totp.verify(params.code, valid_window=1):
            # 验证码错误同样计入失败次数：否则知道密码的攻击者可以无限撞 6 位码
            sec = _security_setting(db)
            limit = int(sec.get("loginFailLimit") or 5)
            user.login_fail_count = (user.login_fail_count or 0) + 1
            if limit and user.login_fail_count >= limit:
                user.locked_until = dt.datetime.now() + dt.timedelta(
                    minutes=int(sec.get("lockMinutes") or 10))
                user.login_fail_count = 0
                db.commit()
                audit(db, user, "登录失败", f"两步验证码错误次数过多，已锁定；IP {ip}", ip)
                return fail("两步验证码错误次数过多，账号已临时锁定")
            db.commit()
            audit(db, user, "登录失败", f"两步验证码错误；IP {ip}", ip)
            return fail("两步验证码错误")
    elif _security_setting(db).get("force2fa"):
        # 强制 2FA：密码正确但还没绑定，只能拿到「绑定专用」的临时令牌
        return ok({
            "needBind2fa": True,
            "userName": user.username,
            "bindToken": create_token(user.id, user.username, user.role,
                                      minutes=10, typ="bind"),
        })

    user.login_fail_count = 0
    user.locked_until = None
    user.last_login_time = dt.datetime.now()
    db.commit()
    audit(db, user, "登录", f"IP {ip}", ip)

    return ok({
        "token": create_token(user.id, user.username, user.role),
        "refreshToken": create_token(user.id, user.username, user.role,
                                     minutes=settings.REFRESH_EXPIRE_MINUTES, typ="refresh"),
    })


@router.post("/refresh")
def refresh(body: dict):
    token = body.get("refreshToken") or ""
    payload = decode_token(token)
    if not payload or payload.get("typ") != "refresh":
        return fail("刷新令牌无效，请重新登录", 401)
    return ok({
        "token": create_token(int(payload["sub"]), payload["username"], payload["role"]),
        "refreshToken": create_token(int(payload["sub"]), payload["username"], payload["role"],
                                     minutes=settings.REFRESH_EXPIRE_MINUTES, typ="refresh"),
    })


@router.post("/logout")
def logout(user: User = Depends(get_current_user)):
    return ok(True)


# ---------------------------------------------------------------- 强制绑定两步验证

class BindCodeParams(BaseModel):
    code: str = ""


@router.post("/2fa/secret")
def bind_secret(user: User = Depends(get_bind_user), db: Session = Depends(get_db)):
    """强制绑定场景下拿密钥：只能凭 bind 令牌调用，不校验登录态。"""
    secret = user.totp_secret or pyotp.random_base32()
    user.totp_secret = secret
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username,
                                              issuer_name=site_name(db))
    return ok({"secret": secret, "uri": uri, "userName": user.username})


@router.post("/2fa/bind")
def bind_2fa(params: BindCodeParams, user: User = Depends(get_bind_user),
             db: Session = Depends(get_db)):
    if not user.totp_secret:
        return fail("请先获取密钥")
    if not params.code:
        return fail("请输入两步验证码")
    if not pyotp.TOTP(user.totp_secret).verify(params.code, valid_window=1):
        return fail("两步验证码错误")
    user.totp_enabled = True
    user.login_fail_count = 0
    user.locked_until = None
    user.last_login_time = dt.datetime.now()
    db.commit()
    audit(db, user, "绑定两步验证")
    return ok({
        "token": create_token(user.id, user.username, user.role),
        "refreshToken": create_token(user.id, user.username, user.role,
                                     minutes=settings.REFRESH_EXPIRE_MINUTES, typ="refresh"),
    })


@router.get("/settings")
def auth_settings(db: Session = Depends(get_db)):
    """登录页需要的公开配置"""
    site = db.get(Setting, "site")
    data = {}
    try:
        data = json.loads(site.value) if site else {}
    except Exception:
        pass
    return ok({
        "siteName": data.get("name", settings.APP_NAME),
        # 副标题（系统设置 → 站点信息），登录页底部那行小字用它
        "subtitle": data.get("subtitle", "") or "",
        "title": data.get("title", settings.APP_NAME),
        # 默认关闭自助注册：这是个「一个团队一套」的证书管理系统，
        # 门户大开时任何人都能注册进来自己建流水线。要开放去系统设置里显式打开。
        "registerEnabled": bool(data.get("registerEnabled", False)),
        "copyright": data.get("copyright", ""),
        "force2fa": bool(_security_setting(db).get("force2fa")),
    })


@router.post("/register")
def register(params: RegisterParams, db: Session = Depends(get_db)):
    site_row = db.get(Setting, "site")
    site = json.loads(site_row.value) if site_row else {}
    if not site.get("registerEnabled", False):
        return fail("当前未开放注册")
    error = validate_password(params.password, params.userName)
    if error:
        return fail(error)
    if db.query(User).filter(User.username == params.userName).first():
        return fail("用户名已存在")
    user = User(username=params.userName, password=hash_password(params.password),
                email=params.email, nickname=params.userName, role="user", status=1)
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user, "注册", params.userName)
    return ok({"token": create_token(user.id, user.username, user.role),
               "refreshToken": create_token(user.id, user.username, user.role, typ="refresh")})
