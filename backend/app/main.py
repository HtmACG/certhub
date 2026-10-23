"""CertHub 后端入口"""
from __future__ import annotations

import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, DATA_DIR, PROJECT_DIR, settings
from .db import SessionLocal, init_db
from .defaults import DEFAULT_SETTINGS
from .models import Pipeline, Setting, User
from .security import hash_password
from .services import engine, scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("certd")


def seed():
    db = SessionLocal()
    try:
        for key, value in DEFAULT_SETTINGS.items():
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=json.dumps(value, ensure_ascii=False)))

        if not db.query(User).first():
            db.add(User(
                username=settings.ADMIN_USERNAME,
                password=hash_password(settings.ADMIN_PASSWORD),
                nickname="管理员", role="admin", email="", status=1,
            ))
            logger.info("已创建默认管理员：%s / %s",
                        settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)

        if not db.query(Pipeline).first():
            demo = {
                "stages": [
                    {"id": "stage-cert", "title": "申请证书", "tasks": [
                        {"id": "task-cert", "type": "CertApplySelfSigned", "title": "自签证书（示例）",
                         "input": {"domains": ["demo.local"], "days": 365, "keyType": "ec256"},
                         "continueOnError": False}
                    ]},
                    {"id": "stage-deploy", "title": "部署证书", "tasks": [
                        {"id": "task-deploy", "type": "DeployToLocal", "title": "复制到本机目录",
                         "input": {"dir": "./data/deploy", "certName": "{domain}.crt",
                                   "keyName": "{domain}.key"},
                         "continueOnError": True}
                    ]},
                ],
                "triggers": [
                    {"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}
                ],
            }
            db.add(Pipeline(
                user_id=1, title="示例：自签证书流水线", type="cert_apply",
                content=json.dumps(demo, ensure_ascii=False),
                remark="首次启动自动创建，可直接点击运行体验完整流程",
                keep_history_count=20, disabled=False,
            ))
        db.commit()
    finally:
        db.close()


def _startup_checks():
    """上线自检：只打 WARN/INFO，不阻止启动（配置不对时也让人能进后台去改）。"""
    import shutil

    logger.info("数据目录：%s", DATA_DIR)
    logger.info("数据库：%s", settings.DB_URL)
    logger.info("时区：%s｜流水线并发：%s", settings.TIMEZONE, settings.PIPELINE_MAX_CONCURRENCY)

    if settings.ADMIN_PASSWORD == "123456":
        logger.warning("默认管理员密码仍是 123456，上线前请登录后台修改（或设置 CERTD_ADMIN_PASSWORD）")
    if "*" in settings.CORS_ORIGINS:
        logger.warning("CORS 允许任意来源（CERTD_CORS_ORIGINS=*），建议改成实际访问域名")

    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_mb = int(usage.free / 1024 / 1024)
        if free_mb < 1024:
            logger.warning("数据目录剩余磁盘仅 %s MB，证书与数据库写入可能受影响", free_mb)
        else:
            logger.info("数据目录剩余磁盘：%s MB", free_mb)
    except Exception as exc:  # noqa: BLE001
        logger.warning("无法读取磁盘空间：%s", exc)

    try:
        db = SessionLocal()
        try:
            abandoned = engine.cleanup_stale_runs()
            if abandoned:
                logger.warning("已把 %s 条中断的执行记录标记为失败", abandoned)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动自检读取数据库失败：%s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed()
    # 上一次进程如果是被强杀的，库里会留下 status=running 的记录，先收尾
    stale = engine.cleanup_stale_runs()
    if stale:
        logger.warning("收尾 %s 条上次中断的执行记录", stale)
    scheduler.start()
    _startup_checks()
    logger.info("%s 启动完成，监听 %s:%s", settings.APP_NAME, settings.HOST, settings.PORT)
    yield
    scheduler.shutdown()


# Swagger / OpenAPI JSON 默认关闭：它们把全部接口、参数、模型都摊开，
# 对公网暴露等于给攻击者一份接口地图。需要时用 CERTD_DOCS=1 打开。
_docs_enabled = os.getenv("CERTD_DOCS", "0") == "1"
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if _docs_enabled else None,
    redoc_url="/api/redoc" if _docs_enabled else None,
    openapi_url="/api/openapi.json" if _docs_enabled else None,
)

# CORS 只在前端与后端不同源时才需要；默认（"*"）不注册中间件：
# 同源部署下浏览器根本不会发跨域请求，放开 "*" 反而让任意站点带着
# 用户 Cookie/Token 来打接口（配合 allow_credentials=True 是经典漏洞）。
_cors_origins = [o for o in (settings.CORS_ORIGINS or []) if o and o.strip() and o.strip() != "*"]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    logger.info("未配置 CORS 白名单（同源部署），已关闭跨域请求")


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """未预期异常：细节只进服务端日志，不回给客户端。

    以前这里把 f"服务器内部错误：{exc}" 直接返回，异常里可能带着
    SQL、文件路径甚至部分凭据，等于给攻击者递情报。
    """
    trace_id = secrets.token_hex(6)
    logger.exception("未处理异常 [trace=%s] %s %s：%s", trace_id,
                     request.method, request.url.path, exc)
    return JSONResponse(status_code=200,
                        content={"code": 500,
                                 "msg": f"服务器内部错误，请把错误编号 {trace_id} 提供给管理员",
                                 "data": None})


from .routers import access, auth, cert, dashboard, dns_record, domain, history, monitor, notification, openapi, pipeline, site, settings as settings_router, user  # noqa: E402

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(pipeline.router)
app.include_router(history.router)
app.include_router(access.router)
app.include_router(cert.router)
app.include_router(domain.router)
app.include_router(dns_record.router)
app.include_router(monitor.router)
app.include_router(notification.router)
app.include_router(settings_router.router)
app.include_router(dashboard.router)
app.include_router(site.router)
app.include_router(openapi.router)


#: 请求体上限：证书 PEM 一般几十 KB，20MB 足够富余，超出直接拒绝
MAX_BODY_BYTES = int(os.getenv("CERTD_MAX_BODY_MB", "20")) * 1024 * 1024


@app.middleware("http")
async def _limit_body(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413,
                            content={"code": 413, "msg": "请求体过大", "data": None})
    return await call_next(request)


#: 基础安全响应头。CSP 不开：前端用了内联样式和 data: 图片，
#: 一上来就上 CSP 会把页面打白，需要单独排期联调。
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # 只在请求确实是 HTTPS 时才发 HSTS，避免本地 http 调试被浏览器记住
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")
    return response


@app.get("/api/health")
def health():
    """健康检查：给监控 / 负载均衡用，能看出「服务活着但数据库坏了 / 磁盘满了」。

    - db：能否连上并执行一条查询（SQLite 锁表、磁盘满都会在这里暴露）
    - disk：数据目录所在盘的剩余空间
    - scheduler：定时任务调度器是否在跑（跑不起来 = 续期不会自动触发）
    """
    import shutil

    from sqlalchemy import text

    data: dict = {"version": settings.VERSION}
    healthy = True

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        data["db"] = "ok"
    except Exception as exc:  # noqa: BLE001
        data["db"] = f"error: {exc.__class__.__name__}: {exc}"
        healthy = False

    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_mb = int(usage.free / 1024 / 1024)
        data["diskFreeMb"] = free_mb
        data["diskFreePercent"] = round(usage.free / usage.total * 100, 1)
        if free_mb < 200:
            healthy = False
            data["diskWarning"] = "磁盘剩余不足 200MB，证书申请与数据库写入可能失败"
    except Exception as exc:  # noqa: BLE001
        data["disk"] = f"error: {exc}"

    try:
        # 注意：scheduler 是模块，真正的调度器实例挂在 scheduler.scheduler 上
        running = bool(getattr(scheduler.scheduler, "running", False))
        data["scheduler"] = "running" if running else "stopped"
        if not running:
            healthy = False
    except Exception as exc:  # noqa: BLE001
        data["scheduler"] = f"unknown: {exc.__class__.__name__}"

    if healthy:
        return {"code": 200, "msg": "ok", "data": data}
    return JSONResponse(status_code=503, content={"code": 503, "msg": "unhealthy", "data": data})


# ---------------------------------------------------------------- 前端静态资源
# 这里刻意不在启动时判断 dist 是否存在：
# 先启后端、后构建前端是很常见的顺序，早期版本会把整个 SPA 路由漏挂，
# 结果就是构建完了页面还是 404，必须重启后端才好。
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"code": 404, "msg": "接口不存在", "data": None})
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return JSONResponse(status_code=503,
                            content={"code": 503, "msg": "前端尚未构建，请先执行 pnpm build", "data": None})
    file = FRONTEND_DIST / full_path
    if full_path and file.is_file():
        return FileResponse(file)
    # index.html 必须每次回源校验：否则前端重新构建后，浏览器还在跑旧 bundle，
    # 表现成「新功能没出现」，而且刷新也不一定生效（只能硬刷新）。
    return FileResponse(index, headers={"Cache-Control": "no-cache, must-revalidate"})
