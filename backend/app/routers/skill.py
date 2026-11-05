"""给 AI / 脚本看的接口说明。

- `GET /api/skill`：Markdown 版（默认返回，浏览器直接看，AI 也能直接读）
- `GET /api/skill.json`：结构化版（认证方式、错误格式、接口清单）
- 接口清单从 `app.openapi()` 实时生成，新增接口不用再改这份文档

默认随 `CERTD_DOCS` 一起开启；设 `CERTD_DOCS=0` 会连同 Swagger 一起关闭。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..config import settings

router = APIRouter(prefix="/api", tags=["meta"])

#: 不需要登录就能访问的接口（其余默认按 JWT 鉴权写）
PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/captcha",
    "/api/auth/refresh",
    "/api/auth/register",
    "/api/auth/settings",
    "/api/site/config",
    "/api/meta/about",
    "/api/meta/updates",
    "/api/openapi.json",
    "/api/docs",
    "/api/redoc",
    "/api/skill",
    "/api/skill.json",
}


def _auth_of(path: str) -> str:
    if path.startswith("/api/open/v1/"):
        return "API Key（X-Api-Key + X-Api-Secret）"
    if path in PUBLIC_PATHS:
        return "公开"
    return "JWT（Authorization: Bearer <token>）"


def _endpoints(request: Request) -> list[dict]:
    schema = request.app.openapi()
    rows: list[dict] = []
    for path, operations in (schema.get("paths") or {}).items():
        for method, operation in operations.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            summary = (operation.get("summary") or operation.get("description") or "").strip()
            rows.append({
                "method": method.upper(),
                "path": path,
                "summary": summary.split("\n")[0][:80],
                "tags": operation.get("tags") or [],
                "auth": _auth_of(path),
            })
    rows.sort(key=lambda row: (row["path"], row["method"]))
    return rows


def _markdown(request: Request, rows: list[dict]) -> str:
    base = str(request.base_url).rstrip("/")
    lines = [
        f"# {settings.APP_NAME} API Skill",
        "",
        f"- 版本：`{settings.VERSION}`",
        f"- 基础地址：`{base}`",
        "- 完整 OpenAPI：`/api/openapi.json`；Swagger：`/api/docs`",
        "",
        "## 认证",
        "",
        "1. 网页登录：`POST /api/auth/login`，body `{\"userName\":\"admin\",\"password\":\"...\"}`，",
        "   返回 `data.token`；之后所有请求带 `Authorization: Bearer <token>`。",
        "2. 脚本调用：在「开放接口」页创建 API Key，请求头带 `X-Api-Key` 与 `X-Api-Secret`，",
        "   可访问 `/api/open/v1/*`。",
        "3. 两步验证开启后，登录可能返回 `need2fa`，需要再提交一次 `code`。",
        "",
        "## 响应格式",
        "",
        "```json",
        '{"code": 200, "msg": "", "data": {}}',
        "```",
        "",
        "业务失败时 HTTP 仍可能是 200，但 `code` 非 200，`msg` 是中文结论；",
        "鉴权失败 / 未登录会直接返回 HTTP 401（body 为 `{\"detail\": \"...\"}`）。",
        "",
        "## 快速开始",
        "",
        "```bash",
        f'TOKEN=$(curl -s -X POST {base}/api/auth/login \\',
        '  -H "Content-Type: application/json" \\',
        '  -d \'{"userName":"admin","password":"123456"}\' | jq -r .data.token)',
        "",
        f'curl -s {base}/api/pipeline/list -H "Authorization: Bearer $TOKEN"',
        f'curl -s -X POST {base}/api/pipeline/1/run -H "Authorization: Bearer $TOKEN"',
        "```",
        "",
        "## 关键流程",
        "",
        "- 运行流水线：`POST /api/pipeline/{id}/run` → 返回 `historyId`；",
        "- 实时日志：`GET /api/history/{historyId}/stream`（SSE，事件 `tasks` / `status` / `end`）；",
        "- 历史详情：`GET /api/history/{historyId}`；",
        "- 证书列表：`GET /api/cert/list`；证书下载：`GET /api/cert/{id}/download?type=crt|key|pfx`；",
        "- 授权（凭据）：`GET /api/access/list`、`POST /api/access`；",
        "- 插件元数据：`GET /api/pipeline/plugins`（表单字段、授权类型都在这里，前端也是读它渲染）。",
        "",
        "## 接口清单",
        "",
        "| 方法 | 路径 | 鉴权 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        summary = row["summary"].replace("|", "\\|")
        lines.append(f"| {row['method']} | `{row['path']}` | {row['auth']} | {summary} |")
    lines += [
        "",
        "> 这份文档默认公开，方便 AI 调研接口；不需要时用环境变量 `CERTD_DOCS=0` 关闭",
        "> （会同时关闭 `/api/docs`、`/api/openapi.json` 和本页）。",
        "",
    ]
    return "\n".join(lines)


@router.get("/skill", response_class=PlainTextResponse, include_in_schema=False)
def skill_markdown(request: Request):
    rows = _endpoints(request)
    return PlainTextResponse(_markdown(request, rows), media_type="text/markdown; charset=utf-8")


@router.get("/skill.md", response_class=PlainTextResponse, include_in_schema=False)
def skill_markdown_alias(request: Request):
    return skill_markdown(request)


@router.get("/skill.json", include_in_schema=False)
def skill_json(request: Request):
    rows = _endpoints(request)
    return JSONResponse({
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "baseUrl": str(request.base_url).rstrip("/"),
        "docs": "/api/docs",
        "openapi": "/api/openapi.json",
        "auth": {
            "jwt": "Authorization: Bearer <token>，来自 POST /api/auth/login 的 data.token",
            "apiKey": "X-Api-Key + X-Api-Secret，可访问 /api/open/v1/*",
            "twoFactor": "账号开启两步验证时，登录可能要求再次提交 code",
        },
        "response": {"code": 200, "msg": "", "data": {}},
        "errors": {
            "401": "未登录 / token 过期",
            "403": "没有该功能的权限",
            "400": "业务校验失败，msg 为中文原因",
        },
        "endpoints": rows,
    })
