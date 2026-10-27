"""流水线模板：把常见组合固化成可一键创建的骨架。

模板只是「骨架」，用户创建后仍需在编辑页选择授权、填写域名与路径。
刻意不填 accessId —— 授权是每个账号私有的，硬编码没有意义。
"""


def _stage(sid: str, title: str, tasks: list) -> dict:
    return {"id": sid, "title": title, "tasks": tasks}


def _task(tid: str, type_: str, title: str, input_: dict, continue_on_error: bool = False) -> dict:
    return {
        "id": tid,
        "type": type_,
        "title": title,
        "input": input_,
        "continueOnError": continue_on_error,
    }


def _cert_task(provider: str = "letsencrypt", challenge: str = "dns") -> dict:
    return _task("task-cert", "CertApply", "证书申请", {
        "domains": [],
        "provider": provider,
        "email": "",
        "challengeType": challenge,
        "dnsAccessId": None,
        "httpUploadType": "local",
        "httpWebRoot": "/var/www/html",
        "httpAccessId": None,
        "keyType": "ec256",
        "renewDays": 20,
        "forceUpdate": False,
    })


PIPELINE_TEMPLATES: list[dict] = [
    {
        "id": "le-nginx-local",
        "name": "Let's Encrypt + Nginx（本机）",
        "desc": "DNS 验证申请证书，写入本机目录后由 Nginx 直接引用",
        "tags": ["最常用", "DNS 验证"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [_cert_task()]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToLocal", "复制到本机目录", {
                        "dir": "/etc/nginx/ssl",
                        "certName": "{domain}.crt",
                        "keyName": "{domain}.key",
                        "pfxName": "",
                        "pfxPassword": "",
                    }),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "le-remote-host",
        "name": "Let's Encrypt + 远程主机（SSH）",
        "desc": "证书上传到远程服务器并通过 SSH 执行 reload 命令",
        "tags": ["DNS 验证", "SSH"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [_cert_task()]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToHost", "部署到远程主机", {
                        "accessId": None,
                        "certPath": "/etc/nginx/ssl/{domain}.crt",
                        "keyPath": "/etc/nginx/ssl/{domain}.key",
                        "pfxPath": "",
                        "pfxPassword": "",
                        "reloadCmd": "nginx -t && nginx -s reload",
                    }),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "le-http01-nginx",
        "name": "Let's Encrypt + HTTP 验证",
        "desc": "无需 DNS API，把验证文件写进 Web 根目录（适合没有域名解析权限的场景）",
        "tags": ["HTTP 验证", "无需 API"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [_cert_task(challenge="http")]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToLocal", "复制到本机目录", {
                        "dir": "/etc/nginx/ssl",
                        "certName": "{domain}.crt",
                        "keyName": "{domain}.key",
                        "pfxName": "",
                        "pfxPassword": "",
                    }),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "le-aliyun-cdn",
        "name": "Let's Encrypt + 阿里云 CDN",
        "desc": "申请证书后自动上传并绑定到阿里云 CDN 加速域名",
        "tags": ["DNS 验证", "云厂商"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [_cert_task()]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToAliyunCdn", "部署到阿里云 CDN", {
                        "accessId": None,
                        "domain": "",
                        "certName": "certd-{domain}-{timestamp}",
                    }),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "le-tencent-cdn",
        "name": "Let's Encrypt + 腾讯云 CDN",
        "desc": "申请证书后上传并绑定到腾讯云 CDN 加速域名",
        "tags": ["DNS 验证", "云厂商"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [_cert_task()]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToTencentCdn", "部署到腾讯云 CDN", {
                        "accessId": None,
                        "domain": "",
                    }),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "volc-free-cert",
        "name": "火山引擎免费证书 + CDN",
        "desc": "用火山引擎证书中心申请免费 DV 证书，自动完成 DNS 验证并绑定到 CDN",
        "tags": ["免费证书", "火山引擎", "云厂商"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [
                    _task("task-cert", "CertApplyVolcengine", "申请火山引擎免费证书", {
                        "domains": "",
                        "accessId": None,
                        "keyType": "RSA",
                        "dnsAccessId": None,
                        "pollInterval": 10,
                        "timeout": 900,
                    }),
                ]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToVolcengine", "部署到火山引擎 CDN", {
                        "accessId": None,
                        "domain": "",
                        "certName": "certd-{domain}-{timestamp}",
                    }),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "trustasia-dv-wildcard",
        "name": "TrustAsia 泛域名证书 + Nginx（本机）",
        "desc": "用 TrustAsia（亚洲诚信）申请泛域名 DV 证书，DNS 验证后写入本机目录",
        "tags": ["泛域名", "TrustAsia", "商业 CA"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [
                    _task("task-cert", "CertApplyTrustAsia", "申请 TrustAsia 证书", {
                        "domains": [],
                        "accessId": None,
                        "productId": "trustasia_ssl_dv_wildcard_v2",
                        "dcvMethod": "dns",
                        "dnsAccessId": None,
                        "keyType": "rsa2048",
                        "validityMonths": 3,
                        "email": "",
                        "pollInterval": 10,
                        "timeout": 1800,
                    }),
                ]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToLocal", "复制到本机目录", {
                        "dir": "/etc/nginx/ssl",
                        "certName": "{domain}.crt",
                        "keyName": "{domain}.key",
                        "pfxName": "",
                        "pfxPassword": "",
                    }, continue_on_error=True),
                ]),
            ],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "apply-only",
        "name": "仅申请证书（不下发）",
        "desc": "只把证书存进证书库，需要时手动下载，适合先跑通签发流程",
        "tags": ["最小配置"],
        "content": {
            "stages": [_stage("stage-cert", "申请证书", [_cert_task()])],
            "triggers": [{"id": "trigger-timer", "type": "timer", "cron": "0 3 * * *", "enabled": True}],
        },
    },
    {
        "id": "self-signed",
        "name": "自签证书（本地测试）",
        "desc": "不联网、不消耗 CA 配额，用于验证流水线与部署链路是否通",
        "tags": ["测试", "无需网络"],
        "content": {
            "stages": [
                _stage("stage-cert", "申请证书", [
                    _task("task-cert", "CertApplySelfSigned", "自签证书", {
                        "domains": ["localhost"],
                        "days": 365,
                        "keyType": "ec256",
                    }),
                ]),
                _stage("stage-deploy", "部署证书", [
                    _task("task-deploy", "DeployToLocal", "复制到本机目录", {
                        "dir": "./data/deploy",
                        "certName": "{domain}.crt",
                        "keyName": "{domain}.key",
                        "pfxName": "",
                        "pfxPassword": "",
                    }, continue_on_error=True),
                ]),
            ],
            "triggers": [],
        },
    },
]


def find_template(template_id: str) -> dict | None:
    for tpl in PIPELINE_TEMPLATES:
        if tpl["id"] == template_id:
            return tpl
    return None
