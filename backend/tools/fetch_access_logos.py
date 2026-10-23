"""把厂商 logo 全部拉成本地 SVG
=====================================

为什么要本地化：卡片、任务选择器要在内网 / 离线环境也能显示厂商图标。
以前用的是 Iconify 在线图标名（logos:xxx）和 favicon.im / icon.horse 这类
在线 favicon 服务，断网或服务抽风时就成了空白块；而且 favicon 是 PNG/ICO 位图，
大小不一、边缘发虚，跟其它矢量图标放一起很违和。

现在的规则：**只用 logo 图标，全部本地 SVG**，一个都不走 favicon。

落盘位置：
  frontend/public/logos/access/<type>.svg   授权类型的厂商 logo
  frontend/public/logos/task/<type>.svg     部署任务自己的图标（Nginx / Apache / 脚本这类）

两类来源：
  1. Iconify 上有的品牌：下 SVG，并把 currentColor 换成品牌色
     （simple-icons / mdi 这类单色图标集如果保留 currentColor，暗色模式下会变成一片死黑或死白）；
  2. Iconify 上没有的品牌（宝塔 / 京东云 / 多吉云 / 白山云 / 又拍云 / 易盾 / 括彩云 / 我爱云）：
     仓库里已经有手绘的同风格 SVG，脚本跳过、不覆盖。

部署任务优先复用授权类型里同一品牌的那张 SVG（见 plugins._DEPLOY_LOGO_BRAND），
所以同一个品牌只会存一份。

下载后逐个校验：文件非空、内容确实是 SVG、里面不再残留 currentColor。
校验失败直接非零退出，不会留下半成品。

用法：
    cd backend && python tools/fetch_access_logos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.plugins import _ACCESS_LOGO_EXT, ACCESS_TYPES, TASK_PLUGINS  # noqa: E402

PROJECT = Path(__file__).resolve().parents[2]
ACCESS_DIR = PROJECT / "frontend" / "public" / "logos" / "access"
TASK_DIR = PROJECT / "frontend" / "public" / "logos" / "task"

#: 这些品牌用的是官网原图（128px PNG，见 plugins.py 的 _ACCESS_LOGO_EXT）
#: 或手工挑选的矢量，脚本一律跳过，免得被 Iconify 的通用图标覆盖掉。
KEEP_LOCAL = {"baota", "synology", "qnap", "jdcloud", "dogecloud", "yidun",
              "upyun", "baishan", "kuocaicdn", "woai", "ctyun"}


def iconify_url(icon: str, color: str) -> str:
    prefix, _, name = icon.partition(":")
    return f"https://api.iconify.design/{prefix}/{name}.svg?color=%23{color.lstrip('#')}"


def fetch(client: httpx.Client, url: str) -> bytes:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.content


def _save(path: Path, data: bytes, label: str, url: str, failed: list[str]) -> int:
    """校验并落盘，返回写入字节数（校验不过返回 0 并记录原因）。"""
    text = data.decode("utf-8", "replace")
    if "<svg" not in text or len(data) < 120:
        failed.append(f"{label}: 不是有效的 SVG（{len(data)} 字节）{url}")
        return 0
    if "currentColor" in text:
        failed.append(f"{label}: SVG 里仍有 currentColor，暗色模式会看不见 {url}")
        return 0
    path.write_bytes(data)
    return len(data)


def main() -> int:
    ACCESS_DIR.mkdir(parents=True, exist_ok=True)
    TASK_DIR.mkdir(parents=True, exist_ok=True)

    failed: list[str] = []
    saved: dict[str, int] = {}
    skipped: list[str] = []

    with httpx.Client(timeout=30, follow_redirects=True,
                      headers={"User-Agent": "CertHub-logo-fetcher"}) as client:
        # ---------------- 授权类型 ----------------
        for key, meta in ACCESS_TYPES.items():
            if key in KEEP_LOCAL:
                skipped.append(key)
                continue
            icon = meta.get("logo") or ""
            if not icon:
                failed.append(f"{key}: 既没有 Iconify 图标也不是手绘品牌，需要补一张 SVG")
                continue
            url = iconify_url(icon, meta.get("color") or "#909399")
            try:
                data = fetch(client, url)
            except Exception as exc:  # noqa: BLE001 - 一次性报全，不中断
                failed.append(f"{key}: 下载失败 {url} -> {exc}")
                continue
            size = _save(ACCESS_DIR / f"{key}.svg", data, key, url, failed)
            if size:
                saved[f"access/{key}.svg"] = size

        # ---------------- 部署任务 ----------------
        for plugin in TASK_PLUGINS:
            if plugin.get("group") != "deploy":
                continue
            logo_file = plugin.get("logoFile") or ""
            # 复用授权类型那张的不用再下一份
            if logo_file.startswith("/logos/access/"):
                continue
            icon = plugin.get("logo") or ""
            if not icon:
                failed.append(f"{plugin['type']}: 没有可下载的图标，需要补一张 SVG")
                continue
            url = iconify_url(icon, plugin.get("color") or "#909399")
            try:
                data = fetch(client, url)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{plugin['type']}: 下载失败 {url} -> {exc}")
                continue
            size = _save(TASK_DIR / f"{plugin['type']}.svg", data,
                         plugin["type"], url, failed)
            if size:
                saved[f"task/{plugin['type']}.svg"] = size

    # 清掉旧的非 SVG 文件（以前下过 favicon 的 PNG / ICO）。
    # 注意：_ACCESS_LOGO_EXT 里声明的 10 家「官网只给位图」的品牌（宝塔 / 群晖 /
    # 京东云 / 多吉云 / 易盾 / 又拍云 / 白山云 / 括彩云 / 我爱云 / 天翼云）是仓库里的
    # 手工资产，脚本自己不会重新下载，**必须保留**；以前这里无脑删非 SVG，
    # 一跑就把它们的 logo 删光，表现为「厂商图标全都不显示了」。
    keep_ext = {f"{brand}.{ext}" for brand, ext in _ACCESS_LOGO_EXT.items()}
    for directory in (ACCESS_DIR, TASK_DIR):
        for old in directory.iterdir():
            if old.suffix.lower() == ".svg":
                continue
            if old.name in keep_ext:
                print(f"  保留本地位图 {old.name}")
                continue
            old.unlink()
            print(f"  移除旧位图 {old.name}")

    print(f"写入 {len(saved)} 个 SVG -> {ACCESS_DIR.parent}")
    for name, size in sorted(saved.items()):
        print(f"  ok  {name} ({size}B)")
    if skipped:
        print(f"跳过 {len(skipped)} 个手绘品牌：{', '.join(sorted(skipped))}")
    if failed:
        print("\n失败：", file=sys.stderr)
        for line in failed:
            print("  err ", line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
