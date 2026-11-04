"""收集 `services/deploy_vendor_*.py` 里声明的新厂商插件。

每个厂商一个模块，自带：
- ``PLUGINS``：插件元数据（和 plugins.py 里 ``_deploy()`` 的输出同构）
- ``ACCESS_TYPES``：授权类型元数据（和 plugins.ACCESS_TYPES 同构）
- ``HANDLERS``：部署实现（模块末尾自己注册进 ``deploy.DEPLOY_HANDLERS``）

``plugins.py`` 在装配 TASK_PLUGINS 时调用 ``collect()`` 合并进来，
新增厂商就不用再改那份两千行的大注册表。
"""
from __future__ import annotations

import importlib
import pkgutil

from . import __path__ as _SERVICES_PATH


def collect() -> tuple[list[dict], dict[str, dict]]:
    plugins: list[dict] = []
    access_types: dict[str, dict] = {}
    for info in pkgutil.iter_modules(_SERVICES_PATH):
        if not info.name.startswith("deploy_vendor_") or info.name == "deploy_vendor_registry":
            continue
        module = importlib.import_module(f"{__package__}.{info.name}")
        plugins.extend(getattr(module, "PLUGINS", []) or [])
        access_types.update(getattr(module, "ACCESS_TYPES", {}) or {})
    return plugins, access_types
