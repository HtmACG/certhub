"""系统默认设置。

单独成模块，避免 main.py 与 router 之间互相 import 造成循环依赖。
新增设置项时只需改这里，读取侧会自动把缺失的键补上默认值。
"""

DEFAULT_SETTINGS: dict[str, dict] = {
    "site": {
        "name": "CertHub",
        # 副标题：显示在侧边栏标题下方 / 顶部栏标题下方，留空则不显示
        "subtitle": "",
        "title": "CertHub 证书管理系统",
        # 自助注册默认关闭：单团队自用系统，开着等于给公网留了个建号入口。
        # 需要多人协作时去「系统设置 → 站点信息」显式打开。
        "registerEnabled": False,
        "copyright": "CertHub · 开源免费，无任何付费功能",
        # ---- 站点个性化（商业版能力）----
        # logo 支持 http(s) 图片地址，也支持系统设置里上传后存下来的 data:image/... 内联图
        "logo": "",
        "loginNotice": "",
        "homeNotice": "",
        "hideBrand": False,
    },
    "security": {
        "loginFailLimit": 5,
        "lockMinutes": 10,
        "force2fa": False,
        # 密码输错几次之后开始要求图形验证码（默认开启，失败 1 次就要）
        "captchaEnabled": True,
        "captchaAfter": 1,
    },
    "notify": {
        "expireDays": 15,
    },
    # ---- 网络设置（HTTP_PROXY / HTTPS_PROXY / NO_PROXY 同一套语义）----
    "network": {
        "httpProxy": "",
        "httpsProxy": "",
        # 排除清单：命中这些域名/网段的请求不走代理（localhost,127.0.0.1,.example.com,192.168.*）
        "noProxy": "",
        # CA 域名 → 反代域名覆盖值；留空则用 services/net.py 里的内置默认
        "reverseProxies": {},
    },
}


def merge_defaults(key: str, stored: dict | None) -> dict:
    """把库里存的设置与默认值合并，保证新增字段有默认值。"""
    base = dict(DEFAULT_SETTINGS.get(key) or {})
    base.update(stored or {})
    return base
