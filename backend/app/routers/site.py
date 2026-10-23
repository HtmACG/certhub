"""站点公开配置（无需登录）。

登录页、浏览器标题、Logo 等需要在未登录状态就能读到，
所以单独开一个不需要鉴权的只读接口，且只暴露展示类字段。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..defaults import merge_defaults
from ..deps import ok
from ..models import Setting

router = APIRouter(prefix="/api/site", tags=["site"])


@router.get("/config")
def public_config(db: Session = Depends(get_db)):
    row = db.get(Setting, "site")
    try:
        stored = json.loads(row.value) if row else {}
    except Exception:
        stored = {}
    site = merge_defaults("site", stored)
    return ok({
        "name": site.get("name") or "CertHub",
        # 副标题：菜单栏 / 顶部栏标题下面的那一行小字
        "subtitle": site.get("subtitle") or "",
        "title": site.get("title") or site.get("name") or "CertHub",
        "logo": site.get("logo") or "",
        "loginNotice": site.get("loginNotice") or "",
        "homeNotice": site.get("homeNotice") or "",
        "hideBrand": bool(site.get("hideBrand")),
        "registerEnabled": bool(site.get("registerEnabled", False)),
        "copyright": site.get("copyright") or "",
    })
