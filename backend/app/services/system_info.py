"""系统信息采集：CPU / 内存 / 硬盘 / 主机。

工作台「系统信息」看板用。全部走 psutil，跨平台（Windows / Linux / macOS），
采集函数可能阻塞（CPU 使用率要取两次采样），调用方应在工作线程里跑。
"""
from __future__ import annotations

import datetime as dt
import os
import platform
import time

import psutil

# 这些文件系统不是真实物理盘（容器 / 临时文件系统），硬盘列表里跳过
_SKIP_FSTYPES = {
    "squashfs", "tmpfs", "devtmpfs", "iso9660", "romfs", "autofs",
    "cgroup", "cgroup2", "pstore", "bpf", "tracefs", "debugfs",
    "fusectl", "configfs", "efivarfs", "mqueue", "sysfs", "proc",
}


def _cpu_name() -> str:
    """取 CPU 型号名，各平台来源不一样，取不到就回退到平台标识。"""
    system = platform.system()
    try:
        if system == "Windows":
            # platform.processor() 在 Windows 上读环境变量 PROCESSOR_IDENTIFIER，
            # 通常是 "Intel64 Family 6 Model 165 Stepping 5, GenuineIntel"
            return platform.processor() or platform.machine()
        if system == "Linux":
            with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
            return platform.machine()
        if system == "Darwin":
            return os.popen("sysctl -n machdep.cpu.brand_string").read().strip() or platform.machine()
    except Exception:
        pass
    return platform.machine() or "unknown"


def _system_mount() -> str:
    """系统盘的挂载点：Windows 取系统盘符（C:\\），类 Unix 取根目录 /。"""
    if platform.system() == "Windows":
        drive = (os.environ.get("SystemDrive") or "C:").strip().rstrip("\\/")
        return drive.upper() + os.sep
    return os.path.abspath(os.sep)


def _same_mount(a: str, b: str) -> bool:
    """比较两个挂载点是否指向同一个盘（Windows 大小写不敏感、末尾斜杠可有可无）。"""
    norm = lambda p: (p or "").strip().rstrip("\\/").lower()
    left, right = norm(a), norm(b)
    return bool(left) and left == right


def _os_name() -> str:
    """人类可读的操作系统名，带版本。"""
    system = platform.system()
    if system == "Windows":
        # platform.release() 在 Win10/11 上可能还显示 10，uname().version 更具体
        return f"Windows {platform.release()} {platform.version()}".strip()
    if system == "Linux":
        # 尽量带上发行版名（Ubuntu 22.04 这种）
        try:
            import distro  # type: ignore

            name = distro.name(pretty=True)
            if name:
                return name
        except Exception:
            pass
        pretty = ""
        try:
            pretty = os.popen("lsb_release -ds 2>/dev/null").read().strip().strip("'\"")
        except Exception:
            pretty = ""
        return pretty or f"Linux {platform.release()}"
    if system == "Darwin":
        mac_ver = platform.mac_ver()[0]
        return f"macOS {mac_ver}".strip()
    return f"{system} {platform.release()}".strip()


def collect_system_info(cpu_interval: float = 0.4) -> dict:
    """采集一次系统信息，返回可直接 JSON 序列化的字典。

    cpu_interval：CPU 使用率两次采样的间隔秒，取 0 会返回自上次调用以来的值
    （第一次为 0）。要在当次就拿到真实读数，给一个小间隔。
    """
    now = time.time()
    boot_ts = psutil.boot_time()
    uptime = max(0, int(now - boot_ts))

    # CPU
    cpu_percent = psutil.cpu_percent(interval=cpu_interval)
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    try:
        freq = psutil.cpu_freq()
        freq_mhz = round(freq.current) if freq else 0
    except Exception:
        freq_mhz = 0
    load_avg = None
    try:
        if hasattr(os, "getloadavg"):
            load_avg = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        # Windows 没有 load average
        load_avg = None

    # 内存
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # 硬盘
    system_mount = _system_mount()
    disks: list[dict] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        partitions = []
    for part in partitions:
        fstype = part.fstype or ""
        if fstype.lower() in _SKIP_FSTYPES:
            continue
        # 光驱 / 未就绪的盘会抛异常，逐个跳过
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        disks.append({
            "device": part.device,
            "mount": part.mountpoint,
            "fstype": fstype,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(usage.percent, 1),
            "system": _same_mount(part.mountpoint, system_mount),
        })
    # 万一全被过滤掉，至少保证当前盘（数据盘）有一条
    if not disks:
        try:
            usage = psutil.disk_usage(os.path.abspath(os.sep))
            disks.append({
                "device": os.path.abspath(os.sep),
                "mount": os.path.abspath(os.sep),
                "fstype": "",
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": round(usage.percent, 1),
                "system": True,
            })
        except Exception:
            pass

    # 系统盘：优先按系统盘符匹配；匹配不到（容器 / 非常规挂载）时退化为第一块盘
    system_disk = next((d for d in disks if d["system"]), None)
    if system_disk is None and disks:
        system_disk = disks[0]
    if system_disk is not None:
        for disk in disks:
            disk["system"] = disk is system_disk

    return {
        "hostname": platform.node(),
        "system": platform.system(),
        "machine": platform.machine(),
        "os": _os_name(),
        "bootTime": dt.datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d %H:%M:%S"),
        "uptime": uptime,
        "cpu": {
            "name": _cpu_name(),
            "percent": round(cpu_percent, 1),
            "perCore": [round(v, 1) for v in per_core],
            "coresPhysical": psutil.cpu_count(logical=False) or psutil.cpu_count() or 0,
            "coresLogical": psutil.cpu_count(logical=True) or 0,
            "freqMhz": freq_mhz,
            "loadAvg": load_avg,
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.total - mem.available,
            "percent": round(mem.percent, 1),
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": round(swap.percent, 1),
        },
        "disks": disks,
        # 工作台只展示系统盘（内存/CPU/系统盘三个仪表）
        "systemDisk": system_disk,
    }
