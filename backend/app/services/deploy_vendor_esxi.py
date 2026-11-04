"""VMware ESXi 主机证书部署。

ESXi 的 Web 服务（hostd / rhttpproxy）读 `/etc/vmware/ssl/rui.crt` 与 `rui.key`，
替换后重启这两个服务即可生效。走 SSH（ESXi 一般只允许 root 登录）。

注意：ESXi 的 shell 是 busybox，脚本里不要用 bash 专有语法。
"""
from __future__ import annotations

import time
from typing import Callable

from .deploy import CertContext, DeployError, _sftp_write, _ssh_client


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


PLUGINS: list[dict] = [
    {
        "type": "DeployToEsxi",
        "name": "ESXi-部署证书到ESXi",
        "group": "deploy",
        "icon": "cloud",
        "category": "主机",
        "desc": "替换 ESXi 主机 Web 证书（/etc/vmware/ssl），可自动重启 hostd / rhttpproxy",
        "logo": "",
        "color": "#607078",
        "inputs": [
            f("accessId", "ESXi SSH 授权", "access", accessCategory="host",
              accessTypes=["ssh"], required=True,
              helper="ESXi 通常只能用 root 通过 SSH 登录：主机 → 管理 → 服务 → 启用 SSH"),
            f("certPath", "证书路径", default="/etc/vmware/ssl/rui.crt"),
            f("keyPath", "私钥路径", default="/etc/vmware/ssl/rui.key"),
            f("backup", "备份原证书", "switch", default=True,
              helper="原文件改名成 *.bak-<时间戳>"),
            f("restart", "重启 Web 服务", "switch", default=True,
              helper="执行 /etc/init.d/hostd restart 与 /etc/init.d/rhttpproxy restart"),
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


def _run(client, command: str, timeout: int = 120) -> tuple[int, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return stdout.channel.recv_exit_status(), (out or err)


@_register("DeployToEsxi")
def deploy_to_esxi(ctx: CertContext, config: dict, log: Callable) -> None:
    cert_path = ctx.render(config.get("certPath") or "/etc/vmware/ssl/rui.crt")
    key_path = ctx.render(config.get("keyPath") or "/etc/vmware/ssl/rui.key")

    log(f"连接 ESXi {config.get('host')} ...")
    client = _ssh_client(config)
    try:
        if config.get("backup", True):
            stamp = time.strftime("%Y%m%d%H%M%S")
            for path in (cert_path, key_path):
                code, out = _run(client, f"cp {path} {path}.bak-{stamp}")
                # 第一次部署时原文件可能不存在，备份失败不算错
                if code != 0:
                    log(f"备份 {path} 跳过：{out or '原文件不存在'}")
                else:
                    log(f"已备份 {path} → {path}.bak-{stamp}")

        sftp = client.open_sftp()
        try:
            log(f"写入 {cert_path}")
            _sftp_write(sftp, cert_path, ctx.crt.encode())
            log(f"写入 {key_path}")
            _sftp_write(sftp, key_path, ctx.key.encode())
        finally:
            sftp.close()

        code, out = _run(client, f"ls -l {cert_path} {key_path}")
        if code != 0:
            raise DeployError(f"写入后校验失败：{out}")
        log(out.replace("\n", "；"))

        if config.get("restart", True):
            log("重启 hostd / rhttpproxy ...")
            code, out = _run(
                client,
                "/etc/init.d/hostd restart >/dev/null 2>&1; "
                "/etc/init.d/rhttpproxy restart >/dev/null 2>&1; echo done",
                timeout=180)
            if code != 0:
                raise DeployError(f"重启 ESXi 服务失败（exit {code}）：{out}")
            log("hostd / rhttpproxy 已重启")

        log("ESXi 证书部署完成，浏览器刷新 https://<ESXi 地址> 查看新证书")
    finally:
        client.close()


from . import deploy as _deploy  # noqa: E402

_deploy.DEPLOY_HANDLERS.update(HANDLERS)
