"""功能权限目录。

用户组勾选的就是这里的键；后端各 router 用 `require_perm(key)` 挂载，
前端按同一份键过滤菜单和路由。改键名时两边一起改。
"""

PERMISSIONS: list[dict] = [
    {"key": "pipelines", "name": "证书流水线", "desc": "流水线、分组、执行与日志"},
    {"key": "history", "name": "执行历史", "desc": "历史记录、运行日志与停止"},
    {"key": "certs", "name": "证书库", "desc": "查看、导入、下载与删除证书"},
    {"key": "access", "name": "授权管理", "desc": "DNS / 云厂商 / 面板等凭据"},
    {"key": "dns", "name": "DNS 记录", "desc": "CNAME 记录与子域名托管"},
    {"key": "monitor", "name": "站点监控", "desc": "站点巡检与证书到期提醒"},
    {"key": "notifications", "name": "通知渠道", "desc": "邮件 / Webhook / 机器人"},
]

PERMISSION_KEYS = {item["key"] for item in PERMISSIONS}


def normalize(keys) -> list[str]:
    """只保留已知权限键，去重并按目录顺序排列。"""
    wanted = set(keys or [])
    return [item["key"] for item in PERMISSIONS if item["key"] in wanted]
