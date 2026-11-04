"""飞牛 NAS（fnOS）证书部署。

走 SSH：读面板自己的证书清单 `/usr/trim/etc/network_cert_all.conf`，
按选中的证书 ID 覆盖证书/私钥/fullchain/issuer，再更新 trim_connect 里的有效期，
最后重启 webdav / smbftpd / trim_nginx 让面板和共享服务用上新证书。

前置条件（面板机器上）：SSH 账号需要 sudo 免密，
`sudo visudo` 末尾加 `用户名 ALL=(ALL) NOPASSWD: ALL`。
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import posixpath
from typing import Callable

from .deploy import CertContext, DeployError, _ssh_client


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToFnOs",
        "name": "飞牛NAS-部署证书",
        "group": "deploy",
        "icon": "cloud",
        "category": "面板",
        "desc": "通过 SSH 替换飞牛 NAS 面板证书并重启相关服务",
        "logo": "",
        "color": "#0f766e",
        "inputs": [
            f("accessId", "飞牛 SSH 授权", "access", accessCategory="host",
              accessTypes=["ssh"], required=True,
              helper="先配置 sudo 免密：sudo visudo，末尾加「用户名 ALL=(ALL) NOPASSWD: ALL」"),
            f("certIds", "证书 ID", "tags", required=True,
              helper="面板证书选 fnOS；FTP / WebDAV 等选「已使用」。"
                     "ID 来自 /usr/trim/etc/network_cert_all.conf 的 sum，"
                     "需要先在面板的证书管理里上传过一次证书"),
            f("restart", "部署后重启服务", "switch", default=True,
              helper="重启 webdav / smbftpd / trim_nginx"),
        ],
        "outputs": [],
    },
]

ACCESS_TYPES: dict[str, dict] = {}
HANDLERS: dict[str, Callable] = {}


def _register(*names: str):
    def deco(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return deco


def _exec(client, command: str, timeout: int = 120) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return stdout.channel.recv_exit_status(), out, err


def _cert_validity_ms(crt: str) -> tuple[int, int]:
    """返回 (not_before_ms, not_after_ms)，与面板数据库里的时间戳单位一致。"""
    try:
        from cryptography import x509
    except Exception as exc:  # pragma: no cover - 环境缺少依赖时给一句人话
        raise DeployError(f"解析证书有效期失败（缺少 cryptography）：{exc}") from exc
    try:
        cert = x509.load_pem_x509_certificate(crt.encode())
        start = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before
        end = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt.timezone.utc)
            end = end.replace(tzinfo=dt.timezone.utc)
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    except Exception as exc:
        raise DeployError(f"解析证书有效期失败：{exc}") from exc


def _issuer_pem(crt: str) -> str:
    """证书链里第一张之外的中间证书，写进 issuer_certificate.crt；没有就留空。"""
    blocks = crt.split("-----END CERTIFICATE-----")
    parts = [block + "-----END CERTIFICATE-----\n" for block in blocks if "BEGIN CERTIFICATE" in block]
    return "".join(parts[1:]).strip()


def _as_ids(value) -> list[str]:
    if value is None or value == "":
        return []
    items = value if isinstance(value, (list, tuple)) else str(value).split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _write_remote(client, path: str, content: bytes) -> None:
    """用 base64 过 SSH 写文件；`sudo tee` 保证目标目录权限不变。"""
    payload = base64.b64encode(content).decode()
    command = (f"echo {payload} | base64 -d | sudo tee {path} > /dev/null")
    code, out, err = _exec(client, command)
    if code != 0:
        raise DeployError(f"写入 {path} 失败（exit {code}）：{err or out}"
                          "（如果提示权限不足，请先配置 sudo 免密）")


@_register("DeployToFnOs")
def deploy_to_fnos(ctx: CertContext, config: dict, log: Callable) -> None:
    cert_ids = _as_ids(config.get("certIds"))
    if not cert_ids:
        raise DeployError("请选择要部署的飞牛证书 ID")

    log(f"连接飞牛 NAS {config.get('host')} ...")
    client = _ssh_client(config)
    try:
        code, out, err = _exec(client, "cat /usr/trim/etc/network_cert_all.conf")
        if code != 0:
            raise DeployError(f"读取证书清单失败：{err or out}")
        try:
            rows = json.loads(out)
        except ValueError:
            raise DeployError(f"证书清单不是合法 JSON：{out[:200]}")

        if not rows:
            raise DeployError("证书清单为空，请先在飞牛面板的证书管理里上传一次证书")

        by_id = {str(row.get("sum")): row for row in rows if row.get("sum") is not None}
        valid_from, valid_to = _cert_validity_ms(ctx.crt)
        issuer = _issuer_pem(ctx.crt)

        for cert_id in cert_ids:
            row = by_id.get(cert_id)
            if not row:
                raise DeployError(f"没有找到证书 {cert_id}，请重新选择")
            cert_path = row.get("certificate") or ""
            key_path = row.get("privateKey") or ""
            if not cert_path or not key_path:
                raise DeployError(f"证书 {cert_id} 缺少文件路径（面板数据不完整）")
            cert_dir = posixpath.dirname(key_path)
            log(f"部署证书 {cert_id}（{row.get('domain') or ''}）→ {cert_dir}")

            _write_remote(client, cert_path, ctx.crt.encode())
            _write_remote(client, key_path, ctx.key.encode())
            _write_remote(client, posixpath.join(cert_dir, "fullchain.crt"), ctx.crt.encode())
            _write_remote(client, posixpath.join(cert_dir, "issuer_certificate.crt"),
                          (issuer + "\n").encode() if issuer else b"")

            _exec(client, f'sudo chmod 0755 "{cert_dir}/" -R')
            safe_key = str(key_path).replace("'", "''")
            sql = (f'UPDATE cert SET valid_to={valid_to}, valid_from={valid_from} '
                   f"WHERE private_key='{safe_key}'")
            code, out, err = _exec(
                client, f'sudo -u postgres psql -d trim_connect -c "{sql}"')
            if code != 0:
                # 数据库更新失败不阻断部署，证书文件已经就位
                log(f"更新面板有效期失败（不影响证书生效）：{err or out}")

        if config.get("restart", True):
            log("重启 webdav / smbftpd / trim_nginx ...")
            code, out, err = _exec(
                client,
                "sudo systemctl restart webdav.service; "
                "sudo systemctl restart smbftpd.service; "
                "sudo systemctl restart trim_nginx.service")
            if code != 0:
                raise DeployError(f"重启飞牛服务失败（exit {code}）：{err or out}")
            log("服务已重启")
        log("飞牛 NAS 证书部署完成")
    finally:
        client.close()


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
