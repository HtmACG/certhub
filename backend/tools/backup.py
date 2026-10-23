"""数据备份 / 恢复辅助脚本
=========================================================
一次性交付、上线后不再维护的系统，数据库和证书私钥的备份必须能自己做：

    # 备份（默认写到 data/backups/，保留最近 14 份）
    python tools/backup.py

    # 指定目录 / 保留份数
    python tools/backup.py --dir D:/backup/certhub --keep 30

    # 恢复（会先备份当前数据，再把 .zip 解回去）
    python tools/backup.py --restore data/backups/certhub-20260101-030000.zip

备份内容：
    certd.db          SQLite 数据库（用 sqlite3 的在线备份 API，运行中也能一致备份）
    certs/            证书与私钥（data/certs）
    secret.key        （可选）JWT 签名密钥，恢复后原来登录态仍然有效
    manifest.json     版本、时间、文件清单与大小

用法建议：Linux 用 cron / Windows 用计划任务，每天凌晨跑一次，备份目录再同步到另一台机器。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR, settings  # noqa: E402

DEFAULT_KEEP = 14
MAX_KEEP = 365


def _db_path() -> Path | None:
    """从 DB_URL 里取出 SQLite 文件路径；非 SQLite 直接返回 None。"""
    url = settings.DB_URL or ""
    if not url.startswith("sqlite:///"):
        return None
    return Path(url[len("sqlite:///"):])


def backup(db_path: Path, target_dir: Path, keep: int, include_secret: bool) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = target_dir / f"certhub-{stamp}.zip"

    pieces: list[tuple[str, int]] = []
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) 数据库：先落到临时文件再打包（在线备份，不锁库）
        if db_path and db_path.exists():
            snapshot = target_dir / f".snapshot-{stamp}.db"
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            dst = sqlite3.connect(snapshot)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            data = snapshot.read_bytes()
            zf.writestr("certd.db", data)
            pieces.append(("certd.db", len(data)))
            snapshot.unlink(missing_ok=True)
        else:
            print("跳过数据库：DB_URL 不是 SQLite 或库文件不存在", file=sys.stderr)

        # 2) 证书目录
        cert_dir = DATA_DIR / "certs"
        if cert_dir.exists():
            for item in cert_dir.rglob("*"):
                if not item.is_file():
                    continue
                arc = "certs/" + item.relative_to(cert_dir).as_posix()
                zf.write(item, arc)
                pieces.append((arc, item.stat().st_size))

        # 3) 签名密钥（恢复后原有登录态有效；不想要可以关掉）
        if include_secret:
            key_file = DATA_DIR / "secret.key"
            if key_file.exists():
                zf.writestr("secret.key", key_file.read_bytes())
                pieces.append(("secret.key", key_file.stat().st_size))

        manifest = {
            "version": settings.VERSION,
            "createdAt": stamp,
            "dbUrl": settings.DB_URL,
            "files": [{"path": p, "size": s} for p, s in pieces],
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    _prune(target_dir, keep)
    return archive


def _prune(target_dir: Path, keep: int) -> None:
    items = sorted(target_dir.glob("certhub-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in items[keep:]:
        try:
            old.unlink()
            print(f"清理旧备份：{old.name}")
        except OSError as exc:
            print(f"清理旧备份失败（跳过）：{old.name} {exc}", file=sys.stderr)


def restore(archive: Path, db_path: Path | None) -> None:
    if not archive.exists():
        raise SystemExit(f"备份文件不存在：{archive}")

    # 先把当前数据挪走，恢复失败还能回滚
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safety = DATA_DIR.parent / f"restore-before-{stamp}"
    safety.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if db_path and "certd.db" in names and db_path.exists():
            shutil.copy2(db_path, safety / db_path.name)
            print(f"已把现有数据库备份到：{safety / db_path.name}")

        for name in names:
            if name == "manifest.json":
                continue
            if name == "certd.db":
                if not db_path:
                    print("跳过数据库：当前 DB_URL 不是 SQLite", file=sys.stderr)
                    continue
                db_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(db_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"已恢复数据库：{db_path}")
            elif name.startswith("certs/"):
                target = DATA_DIR / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif name == "secret.key":
                target = DATA_DIR / name
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"已恢复签名密钥：{target}")
    print("恢复完成，请重启后端服务")


def main() -> int:
    parser = argparse.ArgumentParser(description="CertHub 数据备份 / 恢复")
    parser.add_argument("--dir", default=str(DATA_DIR / "backups"), help="备份目录")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="保留份数")
    parser.add_argument("--restore", default="", help="恢复指定的备份 .zip")
    parser.add_argument("--no-secret", action="store_true", help="备份时不包含 secret.key")
    args = parser.parse_args()

    keep = max(1, min(int(args.keep or DEFAULT_KEEP), MAX_KEEP))
    db_path = _db_path()

    if args.restore:
        restore(Path(args.restore), db_path)
        return 0

    archive = backup(db_path, Path(args.dir), keep, not args.no_secret)
    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"备份完成：{archive}（{size_mb:.2f} MB，保留最近 {keep} 份）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
