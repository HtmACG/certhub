"""关于信息与 GitHub 更新检查。

- `/api/meta/about`：项目与开发者信息（免登录）
- `/api/meta/updates`：拉 GitHub Releases（没有 Release 就退回最近的 commits），
  并和当前版本比较，告诉前端有没有新版本。

GitHub 请求统一走 `services.net`，所以「系统设置 → 网络」里配的代理会生效；
拿不到数据时返回 `error` 字段让前端显示人话，不抛 500。
"""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user, ok
from ..models import Setting, User
from ..services import net

router = APIRouter(prefix="/api/meta", tags=["meta"])

#: 开发者信息（「关于」页展示）
DEVELOPERS = ["北慕林奈", "墨韵先知软媒工坊"]
WEBSITE = "https://www.htmacg.com"
EMAIL = "htmacg@163.com"
DEFAULT_REPO = "HtmACG/certhub"

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 600  # 10 分钟内复用，避免狂点「检查更新」把 GitHub 限额打满


def _site(db: Session) -> dict:
    row = db.get(Setting, "site")
    try:
        return json.loads(row.value) if row else {}
    except Exception:
        return {}


def _repo_of(site: dict) -> str:
    repo = str(site.get("githubRepo") or "").strip()
    return repo or DEFAULT_REPO


def _github_get(path: str):
    return net.get(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "CertHub-update-check",
        },
        timeout=20,
    )


@router.get("/about")
def about(db: Session = Depends(get_db)):
    site = _site(db)
    repo = _repo_of(site)
    return ok({
        "name": site.get("name") or "CertHub",
        "version": settings.VERSION,
        "developers": DEVELOPERS,
        "website": WEBSITE,
        "email": EMAIL,
        "repo": repo,
        "repoUrl": f"https://github.com/{repo}",
    })


def _version_tuple(text: str) -> tuple[int, ...]:
    """把 v1.2.3 / 1.2 这种标签拆成可比较的元组；解析不了就返回空元组。"""
    raw = str(text or "").strip().lstrip("vV")
    parts: list[int] = []
    for piece in raw.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


@router.get("/updates")
def updates(refresh: int = Query(0), user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    repo = _repo_of(_site(db))
    now = dt.datetime.now().timestamp()
    cached = _CACHE.get(repo)
    if not refresh and cached and now - cached[0] < _TTL:
        return ok(cached[1])

    data: dict = {
        "repo": repo,
        "repoUrl": f"https://github.com/{repo}",
        "current": settings.VERSION,
        "latest": "",
        "updateAvailable": False,
        "source": "",
        "releases": [],
        "commits": [],
        "checkedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": "",
    }

    try:
        resp = _github_get(f"/repos/{repo}/releases?per_page=10")
        if resp.status_code == 404:
            data["error"] = f"GitHub 上找不到仓库「{repo}」，请到「系统设置 → 站点信息」改正仓库名"
            return ok(data)
        if resp.status_code >= 400:
            data["error"] = f"GitHub 返回 HTTP {resp.status_code}（可能是访问频率限制，稍后再试）"
            return ok(data)

        for item in resp.json() or []:
            data["releases"].append({
                "tag": item.get("tag_name") or "",
                "name": item.get("name") or item.get("tag_name") or "",
                "publishedAt": (item.get("published_at") or "")[:10],
                "body": (item.get("body") or "")[:4000],
                "url": item.get("html_url") or "",
                "prerelease": bool(item.get("prerelease")),
            })

        if data["releases"]:
            latest = data["releases"][0]
            data["source"] = "release"
            data["latest"] = latest["tag"]
            current_v = _version_tuple(settings.VERSION)
            latest_v = _version_tuple(latest["tag"])
            data["updateAvailable"] = bool(latest_v and current_v and latest_v > current_v)
        else:
            # 没有 Release 就退回到最近提交，至少能看到「更新记录」
            resp = _github_get(f"/repos/{repo}/commits?per_page=10")
            if resp.status_code < 400:
                for item in resp.json() or []:
                    commit = item.get("commit") or {}
                    data["commits"].append({
                        "sha": (item.get("sha") or "")[:7],
                        "message": (commit.get("message") or "").split("\n")[0][:200],
                        "date": ((commit.get("author") or {}).get("date") or "")[:10],
                        "url": item.get("html_url") or "",
                        "author": ((commit.get("author") or {}).get("name") or ""),
                    })
            data["source"] = "commit"
            if data["commits"]:
                data["latest"] = data["commits"][0]["sha"]
    except Exception as exc:  # noqa: BLE001 - 更新检查失败不该让接口 500
        data["error"] = (f"访问 GitHub 失败：{exc.__class__.__name__}"
                         f"（{str(exc) or '无详细原因'}）；如果服务器在境内，"
                         "请到「系统设置 → 网络」配置代理后重试")

    _CACHE[repo] = (now, data)
    return ok(data)
