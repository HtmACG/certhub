"""
插件注册表
==========
CertHub 采用「元数据驱动」的设计：后端声明每个插件的输入项（inputs），
前端据此动态渲染表单。新增插件只需在 TASK_PLUGINS / ACCESS_TYPES 中登记，
并在 services 层实现对应 handler 即可。

全部功能均为免费功能，不存在任何授权校验或付费门槛。
"""

from typing import Any

# ---------------------------------------------------------------- 表单字段组件
# input / password / textarea / number / switch / select / tags / access / cron / radio


def f(key: str, title: str, component: str = "input", **kwargs) -> dict:
    item = {"key": key, "title": title, "component": component}
    item.update(kwargs)
    return item


# ---------------------------------------------------------------- 授权（Access）类型
ACCESS_TYPES: dict[str, dict[str, Any]] = {
    "aliyun": {
        "name": "阿里云",
        "category": "cloud",
        "desc": "阿里云 DNS 解析、CDN 证书部署",
        "inputs": [
            f("accessKeyId", "AccessKey ID", required=True),
            f("accessKeySecret", "AccessKey Secret", "password", required=True),
        ],
    },
    "tencentcloud": {
        "name": "腾讯云 / DNSPod",
        "category": "cloud",
        "desc": "腾讯云 DNS 解析、CDN / EdgeOne 证书部署",
        "inputs": [
            f("secretId", "SecretId", required=True),
            f("secretKey", "SecretKey", "password", required=True),
        ],
    },
    "cloudflare": {
        "name": "Cloudflare",
        "category": "cloud",
        "desc": "Cloudflare DNS 解析",
        "inputs": [
            f("apiToken", "API Token", "password", required=True,
              helper="在 Cloudflare 控制台创建 API Token，权限选择 Zone.DNS:Edit"),
            f("zoneId", "Zone ID", required=False, helper="可选，留空则自动查询"),
        ],
    },
    "huawei": {
        "name": "华为云",
        "category": "cloud",
        "desc": "华为云 DNS 解析",
        "inputs": [
            f("accessKeyId", "AccessKey ID", required=True),
            f("secretAccessKey", "Secret Access Key", "password", required=True),
            f("region", "Region", default="cn-north-4"),
        ],
    },
    "godaddy": {
        "name": "GoDaddy",
        "category": "cloud",
        "desc": "GoDaddy DNS 解析",
        "inputs": [
            f("apiKey", "API Key", required=True),
            f("apiSecret", "API Secret", "password", required=True),
        ],
    },
    "namesilo": {
        "name": "NameSilo",
        "category": "cloud",
        "desc": "NameSilo DNS 解析",
        "inputs": [f("apiKey", "API Key", "password", required=True)],
    },
    "qiniu": {
        "name": "七牛云",
        "category": "cloud",
        "desc": "七牛云 SSL 证书部署",
        "inputs": [
            f("accessKey", "AccessKey", required=True),
            f("secretKey", "SecretKey", "password", required=True),
        ],
    },
    "baiducloud": {
        "name": "百度智能云",
        "category": "cloud",
        "desc": "百度智能云 CDN 证书部署（证书按加速域名挂载）",
        "inputs": [
            f("accessKeyId", "AccessKeyID", required=True,
              helper="百度智能云控制台 → 安全认证 → AccessKey 里的 AK"),
            f("accessKeySecret", "AccessKeySecret", "password", required=True),
        ],
    },
    "volcengine": {
        "name": "火山引擎",
        "category": "cloud",
        "desc": "火山引擎证书中心，可申请免费 DV 证书、托管已有证书",
        "inputs": [
            f("accessKeyId", "AccessKey ID", required=True,
              helper="控制台 → 访问控制 → 访问密钥"),
            f("accessKeySecret", "Secret Access Key", "password", required=True),
            f("region", "Region", default="cn-north-1",
              helper="证书中心默认使用 cn-north-1"),
            f("sessionToken", "临时 Token", "password", required=False,
              helper="仅使用 STS 临时凭证时需要填写"),
        ],
    },
    "trustasia": {
        "name": "TrustAsia 亚洲诚信",
        "category": "cloud",
        "desc": "CertCloud OpenAPI 证书申请（Key ID + API Key），支持 DV / OV / EV、泛域名与多域名",
        "inputs": [
            f("keyId", "Key ID", required=True,
              helper="CertCloud 控制台 → 账户/开发者 → OpenAPI 密钥里创建的 Key ID"),
            f("authKey", "API Key", "password", required=True,
              helper="创建密钥时生成的完整 API Key（只显示一次，丢了就重新建一个）"),
            f("environment", "接口环境", "select", default="prod",
              options=[{"label": "正式环境（api.certcloud.cn）", "value": "prod"},
                       {"label": "测试环境（api-uat.certcloud.cn）", "value": "uat"}],
              helper="正式申请选正式环境；联调可以切测试环境"),
            f("apiBase", "自定义接口地址", default="",
              helper="留空即可。只有走自建代理 / 本地联调时才填，例如 http://127.0.0.1:9000/openapi/v3"),
        ],
    },
    "ssh": {
        "name": "主机 SSH",
        "category": "host",
        "desc": "通过 SSH/SFTP 部署证书到远程主机",
        "inputs": [
            f("host", "主机地址", required=True, placeholder="192.168.1.10"),
            f("port", "端口", "number", default=22),
            f("username", "用户名", default="root"),
            f("authType", "认证方式", "select", default="password",
              options=[{"label": "密码", "value": "password"}, {"label": "私钥", "value": "key"}]),
            f("password", "密码", "password", showWhen={"key": "authType", "value": "password"}),
            f("privateKey", "私钥", "textarea", showWhen={"key": "authType", "value": "key"}),
            f("passphrase", "私钥密码", "password", showWhen={"key": "authType", "value": "key"}),
        ],
    },
    "ftp": {
        "name": "FTP 服务器",
        "category": "host",
        "desc": "通过 FTP / FTPS 上传证书到虚拟主机或文件服务器",
        "inputs": [
            f("host", "服务器地址", required=True, placeholder="ftp.example.com"),
            f("port", "端口", "number", default=21),
            f("username", "用户名", required=True),
            f("password", "密码", "password", required=True),
            f("tls", "加密方式", "select", default="none",
              options=[{"label": "明文 FTP", "value": "none"},
                       {"label": "显式 TLS（FTPS）", "value": "explicit"}]),
            f("passive", "被动模式", "switch", default=True,
              helper="云服务器 / NAT 后面一般要开，否则列目录会超时"),
        ],
    },
    "baota": {
        "name": "宝塔面板",
        "category": "panel",
        "desc": "宝塔面板 API，自动部署到站点",
        "inputs": [
            f("url", "面板地址", required=True, placeholder="http://1.2.3.4:8888"),
            f("apiKey", "接口密钥", "password", required=True,
              helper="面板设置 -> API 接口 -> 接口密钥"),
        ],
    },
    "1panel": {
        "name": "1Panel",
        "category": "panel",
        "desc": "1Panel API，自动部署到网站",
        "inputs": [
            f("url", "面板地址", required=True, placeholder="http://1.2.3.4:10086"),
            f("apiKey", "API 密钥", "password", required=True),
        ],
    },
    "synology": {
        "name": "群晖 DSM",
        "category": "panel",
        "desc": "群晖 NAS，上传证书到 DSM 证书库并可设为默认证书",
        "inputs": [
            # ---- 连接 ----
            f("url", "DSM 地址", required=True, group="连接", placeholder="https://192.168.1.10:5001",
              helper="https://IP 或域名:端口，端口是 DSM「Web 服务」的 HTTPS 端口（默认 5001），"
                     "末尾不要带 /"),
            f("dsmVersion", "群晖版本", "select", default="auto", group="连接",
              options=[
                  {"label": "自动识别（推荐）", "value": "auto"},
                  {"label": "DSM 7.1 及以上", "value": "7.1"},
                  {"label": "DSM 7.0", "value": "7.0"},
              ],
              helper="证书导入接口在两个版本里名字不同：7.1+ 是 SYNO.Core.Certificate.CRT，"
                     "7.0 是 SYNO.Core.Certificate。点「测试」会自动识别并回填这里"),
            # ---- 账号 ----
            f("username", "账号", required=True, group="账号",
              helper="需要有管理员权限的账号：导入系统证书只有 admin 组能做"),
            f("password", "密码", "password", required=True, group="账号"),
            # ---- 二步验证 ----
            f("twoFactor", "已开启二步验证", "switch", default=False, group="二步验证",
              # 老授权没有这个开关，靠 otpType 推导，避免默认值把已有行为改掉
              deriveFrom={"key": "otpType",
                          "map": {"none": False, "key": True, "code": True}},
              helper="DSM「个人设置 → 双重认证」是否开着。开着就必须过一次验证，"
                     "否则登录会返回 403 / 404"),
            # 与 certd 一致：输一次 6 位验证码换「设备ID」，之后登录只带 device_id 免验证码
            f("deviceId", "设备 ID", "password", default="", group="二步验证",
              showWhen={"key": "twoFactor", "value": True},
              action={"type": "synology-device-id", "label": "获取设备ID"},
              placeholder="点右侧「获取设备ID」自动填入",
              helper="填好上面的地址 / 账号 / 密码后点「获取设备ID」，输入双重认证 APP 上的 6 位码，"
                     "它会自动填入（只需要做一次）。"
                     "前置：DSM → 控制面板 → 安全性 → 勾选「允许网页浏览器的用户通过信任设备来跳过双重验证」；"
                     "DSM 的「信任设备」列表里会多一条记录，不要删；"
                     "证书续签间隔建议 ≤30 天，避免设备 ID 过期（过期后重新获取一次即可）"),
            f("deviceName", "设备名", default="CertHub", group="二步验证",
              showWhen={"key": "twoFactor", "value": True},
              helper="DSM「信任设备」列表里显示的名字，同一台机器随便起，多个流水线共用同一个即可"),
            f("otpSecret", "验证密钥（可选兜底）", "password", default="", group="二步验证",
              showWhen={"key": "twoFactor", "value": True},
              helper="没有设备 ID 时的兜底：DSM → 个人设置 → 双重认证 → 「遗失手机或设备」里那串 Base32"
                     "（例：JBSWY3DPEHPK3PXP）。填了它，设备 ID 过期时能自动用现算的验证码重登"),
            f("otpType", "验证码来源", "select", default="key", group="二步验证",
              showWhen={"key": "twoFactor", "value": True},
              options=[
                  {"label": "验证密钥自动生成（推荐，长期可用）", "value": "key"},
                  {"label": "临时填 6 位验证码（仅排障）", "value": "code"},
              ],
              helper="只在没有设备 ID 时才有意义；长期自动续签优先用「设备 ID」"),
            f("otpCode", "6 位验证码（临时）", "password", default="", group="二步验证",
              showWhen=[{"key": "twoFactor", "value": True},
                        {"key": "otpType", "values": ["code"]}],
              helper="30 秒过期，只适合当下排障；长期请用「设备 ID」或「验证密钥」"),
            # ---- 证书 ----
            f("asDefault", "设为默认证书", "switch", default=True, group="证书",
              helper="导入后把这张证书设为 DSM 默认证书（DSM 与套件 https 都用它）"),
            f("certDesc", "证书名称", default="{domain}", group="证书",
              helper="DSM 证书列表里显示的名字，支持 {domain} 占位；同名会被覆盖，不会越传越多"),
            # ---- 高级 ----
            f("insecure", "忽略证书校验", "switch", default=True, group="高级",
              helper="DSM 多为自签证书，连不上时先确认是否开启"),
        ],
    },
    "qnap": {
        "name": "威联通 QTS",
        "category": "panel",
        "desc": "威联通 NAS，上传证书到系统证书库（专业版能力）",
        "inputs": [
            f("url", "QTS 地址", required=True, placeholder="https://192.168.1.11:8080"),
            f("username", "账号", required=True),
            f("password", "密码", "password", required=True),
            f("insecure", "忽略证书校验", "switch", default=True),
        ],
    },
    "proxmox": {
        "name": "Proxmox VE",
        "category": "panel",
        "desc": "PVE 集群节点，上传证书到 /etc/pve/local（专业版能力）",
        "inputs": [
            f("url", "PVE 地址", required=True, placeholder="https://192.168.1.12:8006"),
            f("tokenId", "API Token ID", required=True,
              helper="格式 user@realm!tokenid，例如 root@pam!certd"),
            f("tokenSecret", "API Token Secret", "password", required=True),
            f("node", "节点名", default="pve", helper="多节点集群需指定要部署的节点"),
            f("insecure", "忽略证书校验", "switch", default=True),
        ],
    },
    "aws": {
        "name": "AWS",
        "category": "cloud",
        "desc": "AWS S3 / CloudFront / ACM",
        "inputs": [
            f("accessKeyId", "Access Key ID", required=True),
            f("secretAccessKey", "Secret Access Key", "password", required=True),
            f("region", "Region", default="us-east-1"),
            f("sessionToken", "临时 Token", "password", required=False,
              helper="仅使用 STS 临时凭证时填写"),
        ],
    },
    "s3": {
        "name": "S3 兼容存储",
        "category": "cloud",
        "desc": "MinIO / Ceph / 各类 S3 兼容对象存储",
        "inputs": [
            f("endpoint", "Endpoint", required=True, placeholder="https://s3.example.com",
              helper="只填协议+域名+端口，不要带桶名"),
            f("accessKeyId", "Access Key", required=True),
            f("secretAccessKey", "Secret Key", "password", required=True),
            f("region", "Region", default="us-east-1"),
        ],
    },
    "r2": {
        "name": "Cloudflare R2",
        "category": "cloud",
        "desc": "Cloudflare R2 对象存储",
        "inputs": [
            f("accountId", "Account ID", required=True),
            f("accessKeyId", "Access Key ID", required=True),
            f("secretAccessKey", "Secret Access Key", "password", required=True),
        ],
    },
    "npm": {
        "name": "Nginx Proxy Manager",
        "category": "panel",
        "desc": "NPM 面板，上传证书并绑定代理主机",
        "inputs": [
            f("url", "面板地址", required=True, placeholder="http://192.168.1.20:81"),
            f("email", "登录邮箱", required=True),
            f("password", "密码", "password", required=True),
            f("insecure", "忽略证书校验", "switch", default=True),
        ],
    },
    "k8s": {
        "name": "Kubernetes",
        "category": "panel",
        "desc": "通过 API Server 写入 Secret（需要 ServiceAccount Token）",
        "inputs": [
            f("apiServer", "API Server", required=True,
              placeholder="https://192.168.1.30:6443"),
            f("token", "Token", "password", required=True,
              helper="kubectl -n kube-system create token <sa> 生成"),
            f("namespace", "命名空间", default="default"),
            f("caCert", "集群 CA 证书", "textarea", required=False,
              helper="自建集群的自签 CA（PEM）；开启下面的忽略校验时可以不填"),
            f("insecure", "忽略证书校验", "switch", default=True),
        ],
    },
    "fastly": {
        "name": "Fastly",
        "category": "cloud",
        "desc": "Fastly CDN，上传证书到服务版本",
        "inputs": [
            f("apiToken", "API Token", "password", required=True,
              helper="Fastly 控制台 → Account → API tokens，需要全局权限"),
        ],
    },
    "ctyun": {
        "name": "天翼云",
        "category": "cloud",
        "desc": "天翼云 CDN / 全站加速证书部署",
        "inputs": [
            f("accessKeyId", "AccessKey ID", required=True,
              helper="IAM 控制台 → 我的 AccessKey（iam.ctyun.cn/myAccessKey）"),
            f("securityKey", "Security Key", "password", required=True,
              helper="天翼云的 SecretKey 本身就是 base64 字符串，原样填入即可"),
        ],
    },
    "jdcloud": {
        "name": "京东云",
        "category": "cloud",
        "desc": "京东云数字证书中心 + CDN",
        "inputs": [
            f("accessKeyId", "AccessKey ID", required=True,
              helper="京东云 → 账户管理 → 访问密钥（uc.jdcloud.com/account/accesskey）"),
            f("secretAccessKey", "Secret Access Key", "password", required=True),
            f("region", "Region", default="cn-north-1"),
        ],
    },
    "dogecloud": {
        "name": "多吉云",
        "category": "cloud",
        "desc": "多吉云 CDN，每月免费 30G",
        "inputs": [
            f("accessKey", "AccessKey", required=True,
              helper="多吉云控制台 → 用户中心 → 密钥管理"),
            f("secretKey", "SecretKey", "password", required=True),
        ],
    },
    "yidun": {
        "name": "易盾 DCDN",
        "category": "cloud",
        "desc": "网易易盾 CDN / RCDN，以防御为主",
        "inputs": [
            f("apiKey", "API Key", required=True,
              helper="user.yiduncdn.com → 账号 → API 配置，点开启后获取"),
            f("apiSecret", "API Secret", "password", required=True),
        ],
    },
    "kuocaicdn": {
        "name": "括彩云 CDN",
        "category": "cloud",
        "desc": "括彩云 CDN，每月免费 30G",
        "inputs": [
            f("username", "账号", required=True, helper="注册用的手机号"),
            f("password", "密码", "password", required=True),
        ],
    },
    "woai": {
        "name": "我爱云 CDN",
        "category": "cloud",
        "desc": "我爱云 Edge 加速，证书按 ID 覆盖",
        "inputs": [
            f("username", "账号", required=True),
            f("password", "密码", "password", required=True),
            f("baseApi", "接口地址", default="",
              helper="留空使用 https://console.edeg.ttzi.cn，末尾不要带 /"),
        ],
    },
    "baishan": {
        "name": "白山云",
        "category": "cloud",
        "desc": "白山云 CDN，证书按 ID 更新",
        "inputs": [
            f("token", "Token", "password", required=True,
              helper="白山云控制台获取，或联系服务商申请"),
        ],
    },
    "upyun": {
        "name": "又拍云",
        "category": "cloud",
        "desc": "又拍云 CDN / 云存储 USS",
        "inputs": [
            f("username", "账号", required=True, helper="又拍云控制台登录账号"),
            f("password", "密码", "password", required=True),
        ],
    },
    "safeline": {
        "name": "长亭雷池 WAF",
        "category": "panel",
        "desc": "雷池 SafeLine，更新控制台与防护站点的证书",
        "inputs": [
            f("baseUrl", "雷池访问地址", required=True,
              placeholder="https://192.168.1.10:9443",
              helper="控制台地址，末尾不要带 /"),
            f("apiToken", "ApiToken", "password", required=True,
              helper="雷池控制台 → 系统设置 → 开放接口 里创建"),
            f("insecure", "忽略证书校验", "switch", default=True,
              helper="雷池多为自签证书，建议开启"),
        ],
    },
    # ------------------------------------------------------------ 证书签发
    # EAB（External Account Binding）是「CA 发给你的注册凭据」：
    # Google / SSL.com 这类 CA 注册 ACME 账户时必须带它。
    # 它属于凭据，和 AK/SK 一样放授权管理里统一维护：
    # 换一次 EAB 只改授权，不用去逐条流水线里改任务。
    "eab": {
        "name": "EAB 凭据",
        "category": "cert",
        "desc": "ACME 外部账户绑定凭据（Google Trust Services / SSL.com 等必需）",
        "inputs": [
            f("provider", "所属 CA", "select", default="google",
              options=[
                  {"label": "Google Trust Services", "value": "google"},
                  {"label": "SSL.com", "value": "sslcom"},
                  {"label": "FreeSSL / LiteSSL（亚洲诚信）", "value": "litessl"},
                  {"label": "其它 CA", "value": "other"},
              ],
              helper="只做标识与提示用，实际以证书申请任务里选的 CA 为准"),
            f("kid", "EAB Key ID", required=True,
              helper="CA 控制台创建「ACME 注册密钥」后给的 Key ID（Google 叫 Key ID）"),
            f("hmacKey", "EAB HMAC Key", "password", required=True,
              helper="与 Key ID 配对的 HMAC Key（Google 叫 b64MacKey），Base64 原样粘贴。"
                     "Google 的 EAB key 创建后 7 天失效，过期后在这里更新即可"),
        ],
    },
}

# 一个授权能用在哪些地方。
# 阿里云 / 腾讯云这类账号既能把证书部署到 CDN，也能改 DNS 解析，
# 所以同一个授权要同时出现在「DNS 授权」和「云厂商授权」两个下拉里。
# 之前前端只按 category 分组，导致 DNS 下拉永远是空的（没有 category=dns 的授权）。
_DNS_CAPABLE = {"aliyun", "tencentcloud", "cloudflare", "huawei", "godaddy", "namesilo"}

for _key, _meta in ACCESS_TYPES.items():
    _meta["capabilities"] = [_meta["category"]]
    if _key in _DNS_CAPABLE:
        _meta["capabilities"].append("dns")


# ---------------------------------------------------------------- 授权类型外观
# 「新增授权」里的类型是卡片展示的：卡片要分得清类型，也得认得出厂商，
# 所以每家都要有品牌色 + logo，并且按 ACCESS_CATEGORIES 分组、带分类色。
# logo 一律是联网校验过的 Iconify 图标名
# （api.iconify.design/<prefix>/<name>.svg 实测 200 且非空），禁止凭记忆写。
_ACCESS_VISUAL: dict[str, tuple[str, str, str]] = {
    # type: (Iconify 图标名, 品牌色, 无 logo 时的字母牌首字)
    "aliyun": ("thesvg-color:alibabacloud", "#ff6a00", "阿"),
    "tencentcloud": ("thesvg-color:tencentcloud", "#006eff", "腾"),
    "cloudflare": ("simple-icons:cloudflare", "#f38020", "C"),
    "huawei": ("thesvg-color:huaweicloud", "#c7000b", "华"),
    "godaddy": ("simple-icons:godaddy", "#0e7c86", "G"),
    "namesilo": ("thesvg-color:namesilo", "#30b86b", "N"),
    "qiniu": ("thesvg-color:qiniu", "#07beff", "七"),
    "volcengine": ("thesvg-color:volcengine", "#1664ff", "火"),
    "aws": ("simple-icons:amazonaws", "#ff9900", "A"),
    "s3": ("simple-icons:minio", "#c72e49", "S"),
    "r2": ("simple-icons:cloudflare", "#f38020", "R"),
    "fastly": ("simple-icons:fastly", "#ff282d", "F"),
    "ctyun": ("arcticons:china-telecom", "#0a56a1", "天"),
    "jdcloud": ("", "#e1251b", "京"),
    "dogecloud": ("", "#1e90ff", "多"),
    "yidun": ("", "#e4393c", "易"),
    "kuocaicdn": ("", "#3f8cff", "括"),
    "woai": ("", "#7b68ee", "我"),
    "baishan": ("", "#00a0e9", "白"),
    "upyun": ("", "#1e6fd9", "又"),
    "ssh": ("mdi:server-network", "#409eff", "SSH"),
    "ftp": ("mdi:folder-network-outline", "#4b8bbe", "F"),
    "baota": ("", "#468cc8", "宝"),
    "1panel": ("thesvg-color:1panel", "#087f8c", "1"),
    "synology": ("thesvg-color:synology", "#4c809d", "群"),
    "qnap": ("thesvg-color:qnap", "#0c9ed6", "威"),
    "proxmox": ("thesvg-color:proxmox", "#e57000", "P"),
    "npm": ("thesvg-color:nginx-proxy-manager", "#f15833", "N"),
    "k8s": ("logos:kubernetes", "#326ce5", "K"),
    "safeline": ("thesvg-color:safeline", "#0b6cf0", "雷"),
    "baiducloud": ("simple-icons:baidu", "#2932e1", "百"),
    "trustasia": ("", "#c6272a", "信"),
    "eab": ("mdi:key-variant", "#8b5cf6", "E"),
}

#: Iconify 上没有的品牌，logo 是手绘矢量（同放在 logos/access/ 下，同样是 SVG）。
#: 这张表只记录「这个授权类型用的是哪个品牌 key」，下载脚本据此跳过、不覆盖。
_ACCESS_FAVICON: dict[str, str] = {}

#: 授权分类：前端「授权类型」卡片的筛选标签、分组标题、分类色都来自这里，
#: 不要再在前端硬编码一份。
ACCESS_CATEGORIES: list[dict[str, Any]] = [
    {"key": "cloud", "name": "云厂商", "color": "#409eff",
     "desc": "云厂商与 DNS 服务商的 API 凭据，可用于 DNS 验证、CDN / 对象存储部署"},
    {"key": "host", "name": "主机 SSH", "color": "#67c23a",
     "desc": "SSH / SFTP 直连，把证书文件写到远程主机"},
    {"key": "panel", "name": "服务器面板", "color": "#e6a23c",
     "desc": "面板、集群、WAF 的 API Token，自动绑定站点证书"},
    {"key": "cert", "name": "证书签发", "color": "#8b5cf6",
     "desc": "EAB 外部账户绑定凭据，供证书申请任务选择（ACME 账户私钥由引擎自动生成并跟流水线保存）"},
]

_CATEGORY_BY_KEY = {c["key"]: c for c in ACCESS_CATEGORIES}

#: logo 全部落在本地（frontend/public/logos/access/）：
#: 内网 / 离线部署也能显示，不依赖 favicon.im / icon.horse 这类在线服务。
#:
#: 绝大多数是 SVG；但有 10 家官方只给位图（宝塔 / 群晖 / 京东云 / 多吉云 / 易盾 /
#: 又拍云 / 白山云 / 括彩云 / 我爱云 / 天翼云），手绘矢量跟真 logo 差太远，
#: 干脆用官网原图缩到 128px PNG。所以 logoFile 的后缀不能写死。
#: 重新下载：cd backend && python tools/fetch_access_logos.py
_ACCESS_LOGO_EXT: dict[str, str] = {
    "baota": "png",
    "synology": "png",
    "jdcloud": "png",
    "dogecloud": "png",
    "yidun": "png",
    "upyun": "png",
    "baishan": "png",
    "kuocaicdn": "png",
    "woai": "png",
    "ctyun": "png",
}


def _brand_logo(brand: str) -> str:
    """品牌 key → 本地 logo 路径（按实际文件后缀）。"""
    return f"/logos/access/{brand}.{_ACCESS_LOGO_EXT.get(brand, 'svg')}"


for _key, _meta in ACCESS_TYPES.items():
    _logo, _color, _short = _ACCESS_VISUAL.get(_key, ("", "#909399", ""))
    _cat = _CATEGORY_BY_KEY.get(_meta["category"], {})
    _meta["logo"] = _logo
    _meta["color"] = _color
    _meta["short"] = _short or (_meta["name"] or "?")[:1].upper()
    _meta["categoryName"] = _cat.get("name", _meta["category"])
    _meta["categoryColor"] = _cat.get("color", "#909399")
    _meta["favicon"] = ""
    _meta["logoFile"] = _brand_logo(_key)


# ---------------------------------------------------------------- 证书申请
_CERT_INPUTS = [
    f("domains", "证书域名", "tags", required=True, domainFrom="dnsAccessId",
      helper="支持多个域名与泛域名，例如 foo.com、*.foo.com；泛域名只覆盖一级，"
             "已被泛域名覆盖的子域名不要再填。选好 DNS 授权后可一键带出该账号下的域名"),
    f("provider", "证书颁发机构（CA）", "select", default="letsencrypt",
      options=[
          {"label": "Let's Encrypt（免费 DV，90 天）", "value": "letsencrypt"},
          {"label": "ZeroSSL（免费 DV，90 天，自动换取 EAB）", "value": "zerossl"},
          {"label": "Google Trust Services（免费 DV，90 天，必须先建 EAB 凭据）", "value": "google"},
          {"label": "Buypass（免费 DV，180 天）", "value": "buypass"},
          {"label": "FreeSSL / LiteSSL（亚洲诚信，免费 DV，需 EAB）", "value": "litessl"},
          {"label": "自定义 ACME（填目录地址）", "value": "custom"},
      ],
      helper="不同 CA 的资质要求不同：Google Trust Services 与 SSL.com 这类 CA 必须先有 "
             "EAB 凭据才能注册账户（在「授权管理 → 证书签发」里添加），只填邮箱是签不出证书的。"),
    f("directory", "ACME 目录地址", required=True,
      showWhen={"key": "provider", "value": "custom"},
      placeholder="https://acme.example.com/directory",
      helper="选择「自定义 ACME」时填写，例如 ssl.com 的 https://acme.ssl.com/sslcom-dv-rsa、"
             "或自建 step-ca 的 https://ca.internal/acme/acme/directory"),
    f("email", "联系邮箱", required=True, placeholder="admin@example.com",
      helper="ACME 账户注册邮箱，CA 的证书到期提醒也发到这里；账号私钥首次申请时自动生成，"
             "跟着流水线保存，续期时直接复用，不需要在授权管理里预先建账号"),
    f("eabAccessId", "EAB 凭据", "access", accessCategory="cert",
      showWhen={"key": "provider", "values": ["google", "custom", "litessl"]},
      helper="Google Trust Services / SSL.com / FreeSSL（LiteSSL）这类 CA 必须先有 EAB 凭据："
             "到「授权管理 → 证书签发」新建一条 EAB 凭据，再在这里选它。"
             "Google 的 EAB key 创建后 7 天失效，过期后在授权里更新即可，不用改流水线"),
    f("useProxy", "使用代理访问 CA", "switch", default=False,
      helper="acme-v02.api.letsencrypt.org / dv.acme-v02.api.pki.goog 被墙时打开。"
             "不打开也会先试直连，连不上会自动改用反向代理"),
    f("reverseProxy", "自定义反代地址", default="",
      placeholder="gg.yourproxy.com",
      helper="填写你自己的反向代理域名，不要带 http://。Let's Encrypt 的反代目标是 "
             "acme-v02.api.letsencrypt.org，Google 的目标是 dv.acme-v02.api.pki.goog；"
             "填了就一直走反代，优先级高于系统默认"),
    f("challengeType", "域名验证方式", "select", default="dns",
      options=[
          {"label": "DNS 验证（支持泛域名，推荐）", "value": "dns"},
          {"label": "HTTP 验证（不支持泛域名）", "value": "http"},
      ]),
    f("dnsAccessId", "DNS 授权", "access", accessCategory="dns",
      showWhen={"key": "challengeType", "value": "dns"},
      helper="选择 DNS 服务商授权，流水线会自动添加并清理 TXT 验证记录"),
    f("httpUploadType", "验证文件写入方式", "select", default="local",
      showWhen={"key": "challengeType", "value": "http"},
      options=[
          {"label": "写入本机目录", "value": "local"},
          {"label": "上传到远程主机", "value": "ssh"},
      ]),
    f("httpWebRoot", "网站根目录", default="/var/www/html",
      showWhen={"key": "challengeType", "value": "http"},
      helper="验证文件写入 {根目录}/.well-known/acme-challenge/"),
    f("httpAccessId", "主机授权", "access", accessCategory="host",
      showWhen={"key": "httpUploadType", "value": "ssh"}),
    f("keyType", "密钥类型", "select", default="ec256",
      options=[
          {"label": "ECC 256（推荐）", "value": "ec256"},
          {"label": "ECC 384", "value": "ec384"},
          {"label": "RSA 2048", "value": "rsa2048"},
          {"label": "RSA 3072", "value": "rsa3072"},
          {"label": "RSA 4096", "value": "rsa4096"},
      ]),
    # ---------------- 证书格式（PFX / JKS 转换参数） ----------------
    f("pfxPassword", "PFX 导出密码", "password", default="",
      group="证书格式",
      helper="打包成 PFX / JKS 时用的密码；部署到 IIS / Tomcat 会用到，证书库导出时也可再填"),
    f("pfxArgs", "PFX 兼容性", "select", default="",
      group="证书格式",
      options=[
          {"label": "最新 Windows 服务器（默认）", "value": ""},
          {"label": "Windows Server 2016 兼容（SHA1 + 3DES）",
           "value": "-macalg SHA1 -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES"},
          {"label": "Windows Server 2008 兼容（无 MAC + 3DES）",
           "value": "-nomac -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES"},
      ],
      helper="老版本 Windows 只认 SHA1/3DES 的 PFX，导入失败时换这里的兼容档（需要服务器装了 openssl）"),

    # ---------------- 申请成功通知 ----------------
    f("notifyOnSuccess", "申请成功后发通知", "switch", default=True,
      group="成功通知",
      helper="证书签发成功就通过通知渠道发一条（域名 + 有效期），不用再单独加「发送通知」任务"),
    f("notificationId", "通知渠道", "notification",
      group="成功通知",
      helper="留空则用「通知渠道」里设为默认的那一条；没有配置渠道时静默跳过"),

    # ---------------- 高级：证书链 / 配置档 / DNS 传播与重试 ----------------
    f("preferredChain", "首选证书链", "select", default="",
      group="高级设置",
      options=[
          {"label": "使用 CA 默认链", "value": ""},
          {"label": "ISRG Root X1（Let's Encrypt，兼容老设备）", "value": "ISRG Root X1"},
          {"label": "ISRG Root X2（Let's Encrypt，纯 ECDSA）", "value": "ISRG Root X2"},
          {"label": "GTS Root R1（Google）", "value": "GTS Root R1"},
          {"label": "GlobalSign（Google，兼容性更好）", "value": "GlobalSign"},
      ],
      helper="部分老设备只认特定根证书：换链只影响证书链，不影响证书本身"),
    f("certProfile", "证书配置档", "select", default="",
      group="高级设置",
      options=[
          {"label": "CA 默认", "value": ""},
          {"label": "tlsserver（服务器认证，推荐）", "value": "tlsserver"},
          {"label": "shortlived（短有效期）", "value": "shortlived"},
          {"label": "classic（经典档）", "value": "classic"},
      ],
      helper="仅当 CA 支持 ACME Profiles（例如 Let's Encrypt）时才生效，不支持会自动退回默认配置"),
    f("skipLocalVerify", "跳过本地 DNS 校验", "switch", default=False,
      group="高级设置",
      helper="跳过本地的 TXT 记录传播检查，直接交给 CA 验证：申请更快，但失败率会略高"),
    f("waitDnsDiffuseTime", "DNS 传播等待（秒）", "number", default=0, min=0, max=1800,
      group="高级设置", placeholder="0",
      helper="先固定等这么久再检查记录（解析商刷新生效慢时填 300~600）"),
    f("maxCheckRetryCount", "传播校验重试次数", "number", default=3, min=1, max=20,
      group="高级设置",
      helper="本地查不到 TXT 记录时的重试倍数，DNS 生效慢就往大调"),
    f("certApplyRetryCount", "申请失败重试次数", "number", default=0, min=0, max=5,
      group="高级设置", placeholder="0",
      helper="失败后 30 秒自动重试的次数；瞬时性失败（CA 5xx、挑战超时）重试一次常常就过了"),

    # 续期策略单独成组：以前这里的「到期前多少天续期」是个光秃秃的数字框，
    # 正好落在「DNS 授权」下面，用户看不出它是什么、也不知道填来干嘛。
    f("renewDays", "提前续期天数", "number", default=20, min=1, max=90,
      group="续期策略",
      placeholder="20",
      helper="证书剩余天数小于这个值时才真正去续签（默认 20 天）；重复执行不会重复申请",
      ),
    f("forceUpdate", "强制续期", "switch", default=False, group="续期策略",
      helper="开启后忽略剩余有效期，每次执行都重新申请证书"),
    f("skipIfCertificateExists", "证书已存在且未过期就跳过", "switch", default=True,
      group="续期策略",
      helper="证书库里已有同域名的有效证书时不重复申请，直接执行后面的部署 / 通知步骤"),
    f("skipRecentMinutes", "刚申请过就跳过（分钟）", "number", default=10, min=0, max=1440,
      group="续期策略", placeholder="10",
      helper="同一套域名在这么多分钟内已经签出过证书就不再下单，避免重复运行 / 多环境同时触发"
             "导致重复申请；填 0 关闭这条判断"),
]

CERT_OUTPUTS = [
    "cert.crt", "cert.key", "cert.pfx", "cert.der", "cert.p7b",
    "cert.domain", "cert.issuer", "cert.expiresTime",
]


# ---------------------------------------------------------------- 部署插件外观
# 概览页要把「能部署到哪些平台」逐个列出来，每家配一个 logo（Iconify 图标名，
# 联网查出来的真实存在的图标；查不到的留空，前端会显示品牌色 + 首字母）。
_DEPLOY_VISUAL: dict[str, tuple[str, str]] = {
    # 主机
    "DeployToHost": ("mdi:server-network", "#409eff"),
    "DeployToLocal": ("mdi:folder-outline", "#909399"),
    "DeployToNginx": ("logos:nginx", "#009639"),
    "DeployToApache": ("logos:apache", "#d22128"),
    "DeployToHaproxy": ("devicon:haproxy", "#106da9"),
    "DeployToTomcat": ("logos:tomcat", "#d1760a"),
    "DeployToIis": ("mdi:microsoft-windows", "#0078d4"),
    # 对象存储
    "DeployToAliyunOss": ("thesvg-color:alibabacloud", "#ff6a00"),
    "DeployToTencentCos": ("thesvg-color:tencentcloud", "#006eff"),
    "DeployToHuaweiObs": ("thesvg-color:huaweicloud", "#c7000b"),
    "DeployToVolcengineTos": ("thesvg-color:volcengine", "#1664ff"),
    "DeployToAwsS3": ("logos:aws", "#ff9900"),
    "DeployToS3": ("simple-icons:minio", "#c72e49"),
    "DeployToCloudflareR2": ("logos:cloudflare", "#f38020"),
    "DeployToQiniuKodo": ("thesvg-color:qiniu", "#07beff"),
    # 云 CDN
    "DeployToAliyunCdn": ("thesvg-color:alibabacloud", "#ff6a00"),
    "DeployToAliyunDcdn": ("thesvg-color:alibabacloud", "#ff6a00"),
    "DeployToAliyunLive": ("thesvg-color:alibabacloud", "#ff6a00"),
    "DeployToAliyunVod": ("thesvg-color:alibabacloud", "#ff6a00"),
    "DeployToAliyunSlb": ("thesvg-color:alibabacloud", "#ff6a00"),
    "DeployToTencentCdn": ("thesvg-color:tencentcloud", "#006eff"),
    "DeployToTencentEdgeOne": ("thesvg-color:tencentcloud", "#006eff"),
    "DeployToQiniu": ("thesvg-color:qiniu", "#07beff"),
    "DeployToVolcengine": ("thesvg-color:volcengine", "#1664ff"),
    "DeployToVolcengineCdn": ("thesvg-color:volcengine", "#1664ff"),
    "DeployToVolcengineLive": ("thesvg-color:volcengine", "#1664ff"),
    "DeployToAwsCloudfront": ("logos:aws", "#ff9900"),
    "DeployToFastly": ("logos:fastly", "#ff282d"),
    "DeployToCtyunCdn": ("arcticons:china-telecom", "#0a56a1"),
    "DeployToUpyun": ("", "#1e6fd9"),
    "DeployToTencentClb": ("thesvg-color:tencentcloud", "#006eff"),
    "DeployToSafeline": ("thesvg-color:safeline", "#0b6cf0"),
    "DeployToJDCloudCdn": ("", "#e1251b"),
    "DeployToBaiduCdn": ("simple-icons:baidu", "#2932e1"),
    "DeployToJDCloudCert": ("", "#e1251b"),
    "DeployToDogeCdn": ("", "#1e90ff"),
    "DeployToYidunCdn": ("", "#e4393c"),
    "DeployToKuocaiCdn": ("", "#3f8cff"),
    "DeployToWoaiCdn": ("", "#7b68ee"),
    "DeployToBaishanCdn": ("", "#00a0e9"),
    # 面板 / 集群
    "DeployToBaota": ("", "#468cc8"),
    "DeployTo1Panel": ("thesvg-color:1panel", "#087f8c"),
    "DeployToSynology": ("thesvg-color:synology", "#4c809d"),
    "DeployToQnap": ("thesvg-color:qnap", "#0c9ed6"),
    "DeployToProxmox": ("thesvg-color:proxmox", "#e57000"),
    "DeployToNpm": ("thesvg-color:nginx-proxy-manager", "#f15833"),
    "DeployToOpenwrt": ("thesvg-color:openwrt", "#00b5e2"),
    "DeployToK8sSecret": ("logos:kubernetes", "#326ce5"),
    "DeployToK8sIngress": ("logos:kubernetes", "#326ce5"),
    "DeployToFtp": ("mdi:folder-network-outline", "#4b8bbe"),
    "DeployToAwsAcm": ("logos:aws", "#ff9900"),
    # 其它
    "DeployRunCommand": ("mdi:console-line", "#409eff"),
    "DeployWait": ("mdi:timer-sand", "#909399"),
    "DeployBackupCerts": ("mdi:backup-restore", "#67c23a"),
    "DeployToWebhook": ("material-symbols:webhook", "#67c23a"),
    "DeployToMail": ("mdi:email-outline", "#e6a23c"),
    "DeployToScript": ("mdi:script-text-outline", "#909399"),
}

#: 签发 / 通知类任务在流水线编辑器里的图标（部署类用 _DEPLOY_VISUAL）
_TASK_VISUAL: dict[str, tuple[str, str]] = {
    "CertApply": ("mdi:shield-key-outline", "#409eff"),
    "CertApplySelfSigned": ("mdi:file-certificate-outline", "#8b5cf6"),
    "CertApplyVolcengine": ("thesvg-color:volcengine", "#1664ff"),
    "CertApplyAliyun": ("thesvg-color:alibabacloud", "#ff6a00"),
    "CertApplyTencent": ("thesvg-color:tencentcloud", "#006eff"),
    "Notify": ("mdi:bell-outline", "#67c23a"),
}

#: 部署任务用的厂商 logo：能对上授权类型里同一品牌的，直接复用那张本地 SVG
#: （同一个品牌不重复存两份）；对不上的（图标名不同 / 没有图标）在这里点名。
#: 其余没有品牌的（Nginx / Apache / 脚本 / Webhook 这类）走 logos/task/<type>.svg，
#: 由 tools/fetch_access_logos.py 从 Iconify 下成 SVG。
_DEPLOY_LOGO_BRAND: dict[str, str] = {
    # 没有 Iconify 图标、logo 是手绘矢量的品牌
    "DeployToBaota": "baota",
    "DeployToJDCloudCert": "jdcloud",
    "DeployToJDCloudCdn": "jdcloud",
    "DeployToBaiduCdn": "baiducloud",
    "DeployToDogeCdn": "dogecloud",
    "DeployToBaishanCdn": "baishan",
    "DeployToUpyun": "upyun",
    "DeployToKuocaiCdn": "kuocaicdn",
    "DeployToYidunCdn": "yidun",
    "DeployToWoaiCdn": "woai",
    # 图标名和授权类型里那份不一致，手动指过去
    "DeployToAwsS3": "aws",
    "DeployToAwsCloudfront": "aws",
    "DeployToCloudflareR2": "r2",
    "DeployToFastly": "fastly",
    "DeployToTencentEdgeOne": "tencentcloud",
}

#: 插件的简称（历史字段：前端早期用它画「品牌色底 + 首字母」的文字牌，
#: 现在前端改为按类型兜底一个近似矢量图标，这个字段只作为无障碍/降级数据保留）
_DEPLOY_SHORT: dict[str, str] = {
    # 没有 Iconify 图标、logo 是本地 SVG 的品牌，兜底成字母牌（概览页不留空白块）
    "DeployToUpyun": "又",
    "DeployToBaota": "宝",
    "DeployToJDCloudCert": "京",
    "DeployToJDCloudCdn": "京",
    "DeployToDogeCdn": "多",
    "DeployToYidunCdn": "易",
    "DeployToKuocaiCdn": "括",
    "DeployToWoaiCdn": "我",
    "DeployToBaishanCdn": "白",
    "DeployToBaiduCdn": "百",
    "DeployToTencentEdgeOne": "腾",
    "DeployToFtp": "F",
    "DeployRunCommand": "CMD",
    "DeployWait": "等",
    "DeployBackupCerts": "备",
}

# ---------------------------------------------------------------- 部署插件（扩展）
# 部署插件很多，同类插件的差别通常只是默认路径 / endpoint / 参数。
# 这里用统一的构造器生成元数据，避免几百行重复的 dict 字面量。
def _deploy(type_: str, name: str, desc: str, inputs: list[dict], category: str) -> dict:
    logo, color = _DEPLOY_VISUAL.get(type_, ("", "#909399"))
    return {
        "type": type_,
        "name": name,
        "group": "deploy",
        "icon": "cloud",
        "category": category,
        "desc": desc,
        "logo": logo,
        "color": color,
        "inputs": inputs,
        "outputs": [],
    }


def _acc(title: str, category: str = "cloud") -> dict:
    return f("accessId", title, "access", accessCategory=category, required=True)


_STORAGE_TAIL = [
    f("dir", "存放目录", default="certhub",
      helper="桶内目录前缀，留空则放在根目录"),
    f("certName", "证书文件名", default="{domain}.crt"),
    f("keyName", "私钥文件名", default="{domain}.key"),
    f("pfxName", "PFX 文件名", default="", helper="可选，填写后额外上传一份 PKCS#12"),
    f("pfxPassword", "PFX 密码", "password", default=""),
]

_CDN_TAIL = [
    f("domain", "加速域名", required=True, placeholder="static.example.com"),
    f("certName", "证书名称", default="{domain}-{timestamp}"),
]

_EXT_DEPLOY_PLUGINS: list[dict] = [
    # ---------------- 对象存储
    _deploy("DeployToAliyunOss", "部署到阿里云 OSS",
            "上传证书文件到 OSS 存储桶", [
                _acc("阿里云授权"),
                f("bucket", "Bucket", required=True),
                f("region", "Region", default="oss-cn-hangzhou",
                  helper="形如 oss-cn-hangzhou"),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToTencentCos", "部署到腾讯云 COS",
            "上传证书文件到 COS 存储桶", [
                _acc("腾讯云授权"),
                f("bucket", "Bucket", required=True,
                  helper="需带 APPID，例如 mybucket-1250000000"),
                f("region", "Region", default="ap-guangzhou"),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToHuaweiObs", "部署到华为云 OBS",
            "上传证书文件到 OBS 存储桶", [
                _acc("华为云授权"),
                f("bucket", "Bucket", required=True),
                f("region", "Region", default="cn-north-4"),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToVolcengineTos", "部署到火山引擎 TOS",
            "上传证书文件到 TOS 存储桶", [
                _acc("火山引擎授权"),
                f("bucket", "Bucket", required=True),
                f("region", "Region", default="cn-beijing"),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToAwsS3", "部署到 AWS S3",
            "上传证书文件到 S3 存储桶", [
                _acc("AWS 授权"),
                f("bucket", "Bucket", required=True),
                f("region", "Region", default="us-east-1"),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToS3", "部署到 S3 兼容存储",
            "上传证书文件到 MinIO / Ceph 等 S3 兼容存储", [
                _acc("S3 兼容存储授权"),
                f("endpoint", "Endpoint", required=True,
                  placeholder="http://minio.local:9000",
                  helper="不带桶名，例如 https://s3.example.com"),
                f("bucket", "Bucket", required=True),
                f("region", "Region", default="us-east-1"),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToCloudflareR2", "部署到 Cloudflare R2",
            "上传证书文件到 R2 存储桶", [
                _acc("R2 授权"),
                f("accountId", "Account ID", required=True,
                  helper="Cloudflare 控制台右侧的账户 ID"),
                f("bucket", "Bucket", required=True),
                *_STORAGE_TAIL,
            ], "对象存储"),
    _deploy("DeployToQiniuKodo", "部署到七牛 Kodo",
            "上传证书文件到七牛对象存储", [
                _acc("七牛云授权"),
                f("bucket", "Bucket", required=True),
                f("region", "Region", default="cn-east-1"),
                *_STORAGE_TAIL,
            ], "对象存储"),

    # ---------------- 主机（SSH）
    _deploy("DeployToNginx", "部署到 Nginx（SSH）",
            "上传证书并重载 Nginx", [
                _acc("主机授权", "host"),
                f("certPath", "证书路径", default="/etc/nginx/ssl/{domain}.crt"),
                f("keyPath", "私钥路径", default="/etc/nginx/ssl/{domain}.key"),
                f("reloadCmd", "重载命令", "textarea", default="nginx -t && nginx -s reload"),
            ], "主机"),
    _deploy("DeployToApache", "部署到 Apache（SSH）",
            "上传证书并重载 Apache", [
                _acc("主机授权", "host"),
                f("certPath", "证书路径", default="/etc/httpd/ssl/{domain}.crt"),
                f("keyPath", "私钥路径", default="/etc/httpd/ssl/{domain}.key"),
                f("reloadCmd", "重载命令", "textarea",
                  default="httpd -t && systemctl reload httpd"),
            ], "主机"),
    _deploy("DeployToHaproxy", "部署到 HAProxy（SSH）",
            "上传证书+私钥合并的 PEM 并重载 HAProxy", [
                _acc("主机授权", "host"),
                f("certPath", "PEM 路径", default="/etc/haproxy/ssl/{domain}.pem",
                  helper="HAProxy 要求证书与私钥在同一个文件里"),
                f("reloadCmd", "重载命令", "textarea",
                  default="haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy"),
            ], "主机"),
    _deploy("DeployToTomcat", "部署到 Tomcat（SSH）",
            "上传 PKCS#12 证书并重启 Tomcat", [
                _acc("主机授权", "host"),
                f("pfxPath", "PFX 路径", default="/opt/tomcat/conf/{domain}.pfx"),
                f("pfxPassword", "PFX 密码", "password", default="",
                  helper="需与 server.xml 里的 keystorePass 一致"),
                f("reloadCmd", "重载命令", "textarea", default="systemctl restart tomcat"),
            ], "主机"),
    _deploy("DeployToIis", "部署到 IIS（Windows）",
            "导入 PFX 到证书存储并用 netsh 绑定站点", [
                _acc("主机授权", "host"),
                f("siteName", "站点域名", default="{domain}",
                  helper="netsh 绑定用的 hostname，通常是站点域名"),
                f("port", "端口", "number", default=443),
                f("pfxName", "PFX 文件名", default="{domain}.pfx"),
                f("pfxPassword", "PFX 密码", "password", default=""),
                f("dir", "临时目录", default="C:/certhub"),
            ], "主机"),

    # ---------------- 面板 / 集群
    _deploy("DeployToNpm", "部署到 Nginx Proxy Manager",
            "上传证书并绑定到代理主机", [
                _acc("NPM 授权", "panel"),
                f("proxyHostId", "代理主机（可多选）", "tags", required=False,
                  helper="选好授权后会自动拉取 NPM 代理主机，按证书域名选中匹配项；"
                         "可多选，留空则只上传证书不绑定",
                  remote="npmProxyHosts", remoteFrom="accessId", autoMatchDomains=True),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
            ], "面板"),
    _deploy("DeployToK8sSecret", "部署到 K8s Secret",
            "写入 kubernetes.io/tls 类型的 Secret，可顺带触发 Ingress 重载", [
                _acc("Kubernetes 授权", "panel"),
                f("namespace", "命名空间", default="default",
                  helper="从集群自动拉取的命名空间", remote="namespaces", remoteFrom="accessId"),
                f("secretName", "Secret 名称", default="{domain}-tls"),
                f("ingressNames", "触发重载的 Ingress", "tags", default=[],
                  helper="可选。Nginx Ingress 只监听 Ingress 变化，填了会自动打时间戳注解"),
                f("restartAnnotation", "重载注解", default="certd.io/reload-at",
                  helper="留空则使用默认注解名"),
            ], "集群"),
    _deploy("DeployToOpenwrt", "部署到 OpenWrt / iStoreOS",
            "写入证书并重启 uhttpd", [
                _acc("主机授权", "host"),
                f("service", "服务", "select", default="uhttpd",
                  options=[{"label": "uhttpd（默认）", "value": "uhttpd"},
                           {"label": "nginx", "value": "nginx"},
                           {"label": "自定义命令", "value": "custom"}]),
                f("certPath", "证书路径", default="/etc/ssl/certhub/{domain}.crt"),
                f("keyPath", "私钥路径", default="/etc/ssl/certhub/{domain}.key"),
                f("reloadCmd", "自定义重启命令", "textarea", default="",
                  showWhen={"key": "service", "value": "custom"}),
            ], "面板"),

    # ---------------- 云 CDN
    _deploy("DeployToAliyunDcdn", "部署到阿里云 DCDN",
            "绑定证书到全站加速域名", [_acc("阿里云授权"), *_CDN_TAIL], "云 CDN"),
    _deploy("DeployToAliyunLive", "部署到阿里云直播",
            "绑定证书到视频直播域名", [_acc("阿里云授权"), *_CDN_TAIL], "云 CDN"),
    _deploy("DeployToAliyunVod", "部署到阿里云点播",
            "绑定证书到视频点播加速域名", [_acc("阿里云授权"), *_CDN_TAIL], "云 CDN"),
    _deploy("DeployToAliyunSlb", "上传到阿里云 SLB 证书库",
            "上传证书到负载均衡证书库，供监听引用", [
                _acc("阿里云授权"),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
            ], "云 CDN"),
    _deploy("DeployToVolcengineCdn", "部署到火山引擎 CDN",
            "上传证书并绑定到 CDN 域名", [_acc("火山引擎授权"), *_CDN_TAIL], "云 CDN"),
    _deploy("DeployToVolcengineLive", "部署到火山引擎直播",
            "上传证书并绑定到直播域名", [_acc("火山引擎授权"), *_CDN_TAIL], "云 CDN"),
    _deploy("DeployToAwsCloudfront", "部署到 AWS CloudFront",
            "导入 ACM 证书并更新 CloudFront 分发", [
                _acc("AWS 授权"),
                f("distributionId", "分发 ID", required=True,
                  placeholder="E2ABCDEFGHIJKL"),
                f("sslMethod", "SSL 方式", "select", default="sni-only",
                  options=[{"label": "SNI（免费，推荐）", "value": "sni-only"},
                           {"label": "专用 IP（收费）", "value": "vip"}]),
            ], "云 CDN"),
    _deploy("DeployToFastly", "部署到 Fastly",
            "上传证书到服务版本并激活", [
                _acc("Fastly 授权"),
                f("serviceId", "Service ID", required=True),
                f("version", "版本号", default="",
                  helper="留空则自动克隆 active 版本"),
                f("activate", "上传后激活", "switch", default=True),
            ], "云 CDN"),
    _deploy("DeployToCtyunCdn", "部署到天翼云 CDN",
            "创建证书并批量下发到天翼云加速域名", [
                _acc("天翼云授权"),
                f("productCode", "产品类型", "select", default="008",
                  options=[{"label": "CDN 加速", "value": "008"},
                           {"label": "全站加速", "value": "006"},
                           {"label": "静态加速", "value": "001"},
                           {"label": "下载加速", "value": "003"},
                           {"label": "视频点播加速", "value": "004"},
                           {"label": "安全加速", "value": "007"},
                           {"label": "下载加速闲时", "value": "014"}]),
                f("domains", "加速域名", "tags", required=True,
                  helper="可以从天翼云自动拉取，也可以手填多个",
                  remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
            ], "云 CDN"),
    _deploy("DeployToJDCloudCert", "上传到京东云证书中心",
            "只上传证书到数字证书中心，不依赖 CDN 服务（账号未开通 CDN 时用这个）", [
                _acc("京东云授权"),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
                f("certId", "已有证书 ID", default="",
                  helper="留空则上传新证书"),
            ], "云 CDN"),
    _deploy("DeployToJDCloudCdn", "部署到京东云 CDN",
            "上传证书到数字证书中心并绑定加速域名（账号需开通 CDN）", [
                _acc("京东云授权"),
                f("domains", "加速域名", "tags", required=True,
                  helper="可以从京东云自动拉取，也可以手填",
                  remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
                f("jumpType", "跳转类型", "select", default="default",
                  options=[{"label": "不强制跳转", "value": "default"},
                           {"label": "强制跳转 HTTPS", "value": "https"},
                           {"label": "强制跳转 HTTP", "value": "http"}]),
                f("certId", "已有证书 ID", "number", default=0,
                  helper="留空则上传新证书；填了就直接复用"),
            ], "云 CDN"),
    _deploy("DeployToDogeCdn", "部署到多吉云 CDN",
            "上传证书并绑定多吉云 CDN 域名，顺带清理过期证书", [
                _acc("多吉云授权"),
                f("domains", "CDN 域名", "tags", required=True,
                  helper="可以从多吉云自动拉取，也可以手填",
                  remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
                f("certName", "证书备注", default="{domain}-{timestamp}"),
                f("ignoreDeployNullCode", "忽略绑定报错", "switch", default=False,
                  helper="绑定接口报错但控制台显示已生效时勾选"),
            ], "云 CDN"),
    _deploy("DeployToYidunCdn", "部署到易盾 DCDN",
            "按证书 ID 或站点域名更新易盾证书", [
                _acc("易盾授权"),
                f("certId", "证书 ID", "number", default=0,
                  helper="填了证书 ID 就直接更新；留空则按下面的站点域名查找"),
                f("domains", "站点域名", "tags", default=[],
                  helper="没填证书 ID 时必填，例如 cdn.example.com"),
            ], "云 CDN"),
    _deploy("DeployToKuocaiCdn", "部署到括彩云 CDN",
            "登录括彩云后按域名更新 HTTPS 配置", [
                _acc("括彩云授权"),
                f("domains", "站点域名", "tags", required=True,
                  helper="可以从括彩云自动拉取，也可以手填域名或域名 ID",
                  remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
            ], "云 CDN"),
    _deploy("DeployToWoaiCdn", "部署到我爱云 CDN",
            "登录我爱云后覆盖指定证书 ID 的内容", [
                _acc("我爱云授权"),
                f("certId", "证书 ID", required=True,
                  helper="我爱云控制台 → 证书列表里每条记录都有 ID"),
            ], "云 CDN"),
    _deploy("DeployToUpyun", "部署到又拍云 CDN / USS",
            "上传证书并绑定又拍云加速域名，可顺带设置强制 HTTPS", [
                _acc("又拍云授权"),
                f("domains", "加速域名", "tags", required=True,
                  helper="可以从又拍云自动拉取，也可以手填多个",
                  remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
                f("forceHttps", "强制 HTTPS", "select", default="keep",
                  options=[{"label": "保持原样", "value": "keep"},
                           {"label": "强制 HTTPS", "value": "true"},
                           {"label": "不强制", "value": "false"}]),
            ], "云 CDN"),
    _deploy("DeployToTencentClb", "部署到腾讯云 CLB",
            "上传证书到 SSL 证书中心并绑定到负载均衡监听器", [
                _acc("腾讯云授权"),
                f("loadBalancerId", "负载均衡实例 ID", required=True, placeholder="lb-xxxxxxxx"),
                f("listenerId", "监听器 ID", required=True, placeholder="lbl-xxxxxxxx"),
                f("domain", "证书域名", default="",
                  helper="HTTPS 监听器绑定了多个域名时填写，单域名监听器可留空"),
                f("certAlias", "证书别名", default="{domain}-{timestamp}"),
                f("certId", "已有证书 ID", default="",
                  helper="留空则上传新证书；填了就直接复用 SSL 证书中心的证书"),
            ], "云 CDN"),
    _deploy("DeployToSafeline", "部署到雷池 WAF",
            "更新长亭雷池控制台 / 防护站点的证书（按证书 ID）", [
                _acc("雷池授权", "panel"),
                f("certIds", "雷池证书 ID", "tags", default=["0"],
                  remote="certs", remoteFrom="accessId",
                  helper="填雷池控制台证书列表里的 ID；填 0 表示新增一张，"
                         "新增后把这里改成新证书 ID 才能持续自动更新"),
            ], "面板"),
    _deploy("DeployToBaishanCdn", "部署到白山云",
            "按证书 ID 更新白山云证书内容", [
                _acc("白山云授权"),
                f("certId", "证书 ID", required=True,
                  helper="白山云控制台证书列表里的 ID"),
                f("certName", "证书名称", default="{domain}"),
            ], "云 CDN"),

    # ---------------- 其它
    _deploy("DeployToMail", "证书发送到邮箱",
            "把证书与私钥作为附件发送（人工安装 / 备份场景）", [
                f("smtpHost", "SMTP 服务器", required=True, placeholder="smtp.qq.com"),
                f("smtpPort", "端口", "number", default=465),
                f("ssl", "使用 SSL", "switch", default=True),
                f("username", "账号", required=True),
                f("password", "密码 / 授权码", "password", required=True,
                  helper="多数邮箱这里要填授权码，不是登录密码"),
                f("from", "发件人", default="", helper="留空则用账号"),
                f("to", "收件人", "tags", required=True),
            ], "其它"),
    _deploy("DeployToScript", "在主机执行脚本",
            "通过 SSH 执行自定义命令，证书内容通过环境变量传入", [
                _acc("主机授权", "host"),
                f("command", "命令", "textarea", required=True,
                  default="echo $CERTD_DOMAIN > /tmp/certd.log",
                  helper="可用环境变量：CERTD_DOMAIN / CERTD_CERT / CERTD_KEY（base64）"),
            ], "其它"),
]

# ---------------------------------------------------------------- 部署插件（第二批）
# 上游 certd 的「选择任务类型」里还有这几类本系统原先没有的，
# handler 统一在 services/deploy_extra.py 里，元数据仍走 _deploy() 构造器。
_EXTRA_DEPLOY_PLUGINS: list[dict] = [
    _deploy("DeployToFtp", "上传证书到 FTP",
            "通过 FTP / FTPS 上传证书文件到虚拟主机或文件服务器", [
                _acc("FTP 授权", "host"),
                f("dir", "存放目录", default="certs",
                  helper="逐级创建，目录不存在会自动新建"),
                f("certName", "证书文件名", default="{domain}.crt"),
                f("keyName", "私钥文件名", default="{domain}.key"),
                f("pfxName", "PFX 文件名", default="",
                  helper="可选，填写后额外上传一份 PKCS#12"),
            ], "主机"),
    _deploy("DeployRunCommand", "执行远程主机命令",
            "在远程主机上执行命令（重载服务等），不需要传证书文件", [
                _acc("主机授权", "host"),
                f("command", "命令", "textarea", required=True,
                  default="nginx -s reload",
                  helper="支持 {domain} / {date} / {timestamp} 变量"),
                f("timeout", "超时（秒）", "number", default=120),
            ], "主机"),
    _deploy("DeployWait", "等待",
            "等待一段时间后再执行后续任务，适合等 CDN 下发或给流水线排节奏", [
                f("seconds", "等待秒数", "number", default=30, helper="最长 3600 秒"),
            ], "其它"),
    _deploy("DeployToK8sIngress", "部署到 K8s Ingress",
            "写入 TLS Secret，并把 Ingress 的 spec.tls 指向它", [
                _acc("Kubernetes 授权", "panel"),
                f("namespace", "命名空间", default="default"),
                f("ingressName", "Ingress 名称", required=True,
                  helper="该命名空间下的 Ingress 名称"),
                f("secretName", "Secret 名称", default="{domain}-tls"),
                f("hosts", "TLS 域名", "tags", required=False,
                  helper="留空则保留 Ingress 里原有的 hosts"),
            ], "集群"),
    _deploy("DeployToAwsAcm", "上传证书到 AWS ACM",
            "导入证书到 AWS 证书管理器，供 ALB / API Gateway / CloudFront 引用", [
                _acc("AWS 授权"),
                f("region", "区域", default="us-east-1",
                  helper="CloudFront 只认 us-east-1 的证书，其它服务按所在区域填"),
                f("certName", "证书名称（标签）", default="{domain}"),
                f("certChain", "中间证书链", "textarea", default="",
                  helper="一般留空；部分 CA 需要单独提供中间证书"),
            ], "云 CDN"),
    _deploy("DeployToBaiduCdn", "部署到百度云 CDN",
            "把证书上传到百度智能云的加速域名并开启 HTTPS（证书按域名挂载）", [
                f("accessId", "百度云授权", "access", accessCategory="cloud",
                  required=True, accessTypes=["baiducloud"]),
                f("domain", "加速域名", "tags", required=True, domainFrom="",
                  remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True,
                  helper="从左侧「资源」按钮可拉取账号下的全部加速域名"),
                f("certName", "证书名称", default="{domain}-{timestamp}"),
                f("certChain", "中间证书链", "textarea", default="",
                  helper="一般留空；证书本身就是全链 PEM 的话不用填"),
                f("httpsEnable", "启用 HTTPS", "switch", default=True),
            ], "云 CDN"),
    _deploy("DeployBackupCerts", "数据备份",
            "把本次证书打包归档到本机备份目录，换证出问题可以回滚", [
                f("dir", "备份目录", default="./data/backup",
                  helper="相对路径以项目根目录为准"),
                f("fileName", "备份文件名", default="{domain}-{timestamp}.zip"),
                f("keepCount", "保留份数", "number", default=30,
                  helper="按修改时间只保留最近 N 份，0 表示不清理"),
            ], "其它"),
]

TASK_PLUGINS: list[dict[str, Any]] = [
    # ------------------------------ 证书
    {
        "type": "CertApply",
        "name": "证书申请",
        "group": "cert",
        "icon": "certificate",
        "desc": "通过 ACME 协议向免费 CA 申请证书，支持泛域名、多域名合并",
        "inputs": _CERT_INPUTS,
        "outputs": CERT_OUTPUTS,
    },
    {
        "type": "CertApplySelfSigned",
        "name": "自签证书（本地测试）",
        "group": "cert",
        "icon": "certificate",
        "desc": "生成自签名证书，无需域名与网络，用于验证流水线流程",
        "inputs": [
            f("domains", "证书域名", "tags", required=True, default=["localhost"]),
            f("days", "有效天数", "number", default=365),
            f("keyType", "密钥类型", "select", default="ec256",
              options=[{"label": "ECC 256", "value": "ec256"},
                       {"label": "RSA 2048", "value": "rsa2048"}]),
            f("forceUpdate", "强制重新生成", "switch", default=False, group="续期策略",
              helper="开启后忽略剩余有效期与已有证书，每次执行都重新生成"),
            f("skipIfCertificateExists", "已有未过期证书就跳过", "switch", default=True,
              group="续期策略"),
            f("skipRecentMinutes", "刚生成过就跳过（分钟）", "number", default=10, min=0, max=1440,
              group="续期策略", placeholder="10"),
        ],
        "outputs": CERT_OUTPUTS,
    },
    {
        "type": "CertApplyVolcengine",
        "name": "火山引擎免费证书",
        "group": "cert",
        "icon": "cloud",
        "desc": "向火山引擎证书中心申请免费 DV 证书，自动完成 DNS 验证并回传证书",
        "inputs": [
            f("domains", "证书域名", "tags", required=True, domainFrom="dnsAccessId",
              helper="免费证书为单域名 DV，建议一次只填一个主域名"),
            f("accessId", "火山引擎授权", "access", accessCategory="cloud", required=True),
            f("plan", "套餐 Plan", required=True,
              helper="QuickApplyCertificate 的必填参数。在证书中心购买/领取免费证书的页面里"
                     "能看到套餐编码，按账号而定，填错会返回 Unsupported.OrderPlan"),
            f("organizationId", "组织机构 ID", default="",
              helper="留空则自动取证书中心里的第一个组织机构"),
            f("keyType", "密钥算法", "select", default="RSA",
              options=[{"label": "RSA（兼容性好）", "value": "RSA"},
                       {"label": "ECC（更省资源）", "value": "ECC"}]),
            f("dnsAccessId", "DNS 授权", "access", accessCategory="dns", required=True,
              helper="用于自动添加 DNS 验证记录（RecordType=dns_txt），可以是任意服务商的授权"),
            f("pollInterval", "轮询间隔（秒）", "number", default=10),
            f("timeout", "超时时间（秒）", "number", default=900,
              helper="火山引擎签发通常需要 1~10 分钟"),
            f("renewDays", "提前续期天数", "number", default=20, min=1, max=90,
              group="续期策略", placeholder="20",
              helper="证书剩余天数少于这个值才真正去续签；重复执行不会重复申请"),
            f("forceUpdate", "强制续期", "switch", default=False, group="续期策略",
              helper="开启后忽略剩余有效期与已有证书，每次执行都重新申请"),
            f("skipIfCertificateExists", "证书已存在且未过期就跳过", "switch", default=True,
              group="续期策略",
              helper="证书库里已有同域名的有效证书时跳过申请，继续执行后面的部署 / 通知步骤"),
            f("skipRecentMinutes", "刚申请过就跳过（分钟）", "number", default=10, min=0, max=1440,
              group="续期策略", placeholder="10",
              helper="这套域名在这么多分钟内已签出过证书就不再下单，避免重复申请；填 0 关闭"),

        ],
        "outputs": CERT_OUTPUTS,
    },
    {
        "type": "CertApplyAliyun",
        "name": "阿里云免费证书",
        "group": "cert",
        "icon": "cloud",
        "desc": "向阿里云数字证书管理服务申请个人测试证书（免费 DV），自动完成 DNS 验证",
        "inputs": [
            f("domains", "证书域名", "tags", required=True, domainFrom="dnsAccessId",
              helper="免费个人测试证书为单域名，建议一次只填一个主域名"),
            f("accessId", "阿里云授权", "access", accessCategory="cloud", required=True,
              helper="需授予数字证书管理服务（CAS）的读写权限"),
            f("productCode", "证书规格", "select", default="digicert-free-1-free",
              options=[
                  {"label": "DigiCert 个人测试证书（免费，3 个月）", "value": "digicert-free-1-free"},
                  {"label": "Symantec 个人测试证书 Pro（免费，12 个月，仅中国站）",
                   "value": "symantec-free-1-free"},
              ],
              helper="账号里需要有对应规格的可用额度，否则会返回额度不足"),
            f("email", "联系人邮箱", default="",
              helper="留空则使用控制台「信息管理」里最新添加的联系人"),
            f("dnsAccessId", "DNS 授权", "access", accessCategory="dns", required=True,
              helper="用于自动添加 TXT 验证记录，可以是任意服务商的授权"),
            f("pollInterval", "轮询间隔（秒）", "number", default=10),
            f("timeout", "超时时间（秒）", "number", default=900,
              helper="个人测试证书通常几分钟内签发"),
            f("renewDays", "提前续期天数", "number", default=20, min=1, max=90,
              group="续期策略", placeholder="20",
              helper="证书剩余天数少于这个值才真正去续签；重复执行不会重复申请"),
            f("forceUpdate", "强制续期", "switch", default=False, group="续期策略",
              helper="开启后忽略剩余有效期与已有证书，每次执行都重新申请"),
            f("skipIfCertificateExists", "证书已存在且未过期就跳过", "switch", default=True,
              group="续期策略",
              helper="证书库里已有同域名的有效证书时跳过申请，继续执行后面的部署 / 通知步骤"),
            f("skipRecentMinutes", "刚申请过就跳过（分钟）", "number", default=10, min=0, max=1440,
              group="续期策略", placeholder="10",
              helper="这套域名在这么多分钟内已签出过证书就不再下单，避免重复申请；填 0 关闭"),

        ],
        "outputs": CERT_OUTPUTS,
    },
    {
        "type": "CertApplyTencent",
        "name": "腾讯云免费证书",
        "group": "cert",
        "icon": "cloud",
        "desc": "向腾讯云 SSL 申请 TrustAsia C1 DV Free（免费，3 个月），自动完成 DNS 验证",
        "inputs": [
            f("domains", "证书域名", "tags", required=True, domainFrom="dnsAccessId",
              helper="免费证书为单域名 DV，一次只申请第一个域名"),
            f("accessId", "腾讯云授权", "access", accessCategory="cloud", required=True,
              helper="需授予 SSL 证书（ssl）相关接口权限"),
            f("keyType", "密钥算法", "select", default="RSA",
              options=[{"label": "RSA 2048（兼容性好）", "value": "RSA"},
                       {"label": "ECC P-256（更省资源）", "value": "ECC"}]),
            f("dnsAccessId", "DNS 授权", "access", accessCategory="dns", required=True,
              helper="用于自动添加 TXT 验证记录，可以是任意服务商的授权"),
            f("pollInterval", "轮询间隔（秒）", "number", default=10),
            f("timeout", "超时时间（秒）", "number", default=900),
            f("renewDays", "提前续期天数", "number", default=20, min=1, max=90,
              group="续期策略", placeholder="20",
              helper="证书剩余天数少于这个值才真正去续签；重复执行不会重复申请"),
            f("forceUpdate", "强制续期", "switch", default=False, group="续期策略",
              helper="开启后忽略剩余有效期与已有证书，每次执行都重新申请"),
            f("skipIfCertificateExists", "证书已存在且未过期就跳过", "switch", default=True,
              group="续期策略",
              helper="证书库里已有同域名的有效证书时跳过申请，继续执行后面的部署 / 通知步骤"),
            f("skipRecentMinutes", "刚申请过就跳过（分钟）", "number", default=10, min=0, max=1440,
              group="续期策略", placeholder="10",
              helper="这套域名在这么多分钟内已签出过证书就不再下单，避免重复申请；填 0 关闭"),
        ],
        "outputs": CERT_OUTPUTS,
    },
    {
        "type": "CertApplyTrustAsia",
        "name": "TrustAsia 亚洲诚信证书",
        "group": "cert",
        "icon": "cloud",
        "desc": "向 TrustAsia（CertCloud）下单申请 DV / OV / EV 证书，自动写 DNS 验证记录并回传证书",
        "inputs": [
            f("domains", "证书域名", "tags", required=True, domainFrom="dnsAccessId",
              helper="支持多域名与泛域名：多域名产品一次可以填多个（逗号或换行分隔），"
                     "泛域名写 *.example.com。域名个数、能不能泛域名由所选产品决定"),
            f("accessId", "TrustAsia 授权", "access", accessCategory="cloud", required=True,
              helper="在「授权管理 → 云厂商」新建一条 TrustAsia 授权，填 CertCloud 的 Key ID 与 API Key"),
            f("productId", "证书产品", "select", default="trustasia_ssl_dv_v2",
              required=True,
              options=[
                  {"label": "域名型 DV · 单域名（trustasia_ssl_dv_v2）", "value": "trustasia_ssl_dv_v2"},
                  {"label": "域名型 DV · 通配符（trustasia_ssl_dv_wildcard_v2）",
                   "value": "trustasia_ssl_dv_wildcard_v2"},
                  {"label": "域名型 DV · 多域名（trustasia_ssl_dv_sans_v2）", "value": "trustasia_ssl_dv_sans_v2"},
                  {"label": "企业型 OV · 单域名（trustasia_ssl_ov_v2）", "value": "trustasia_ssl_ov_v2"},
                  {"label": "企业型 OV · 通配符（trustasia_ssl_ov_wildcard_v2）",
                   "value": "trustasia_ssl_ov_wildcard_v2"},
                  {"label": "企业型 OV · 多域名（trustasia_ssl_ov_sans_v2）", "value": "trustasia_ssl_ov_sans_v2"},
                  {"label": "增强型 EV · 单域名（trustasia_ssl_ev_v2）", "value": "trustasia_ssl_ev_v2"},
                  {"label": "增强型 EV · 多域名（trustasia_ssl_ev_sans_v2）", "value": "trustasia_ssl_ev_sans_v2"},
              ],
              helper="产品 ID 就是下单接口的 product_id。OV / EV 需要组织审核，账号里要先有对应额度"),
            f("dcvMethod", "域名验证方式", "select", default="dns",
              options=[
                  {"label": "DNS TXT 验证（推荐，支持泛域名）", "value": "dns"},
                  {"label": "CNAME 验证", "value": "cname"},
                  {"label": "HTTP 文件验证（不支持泛域名）", "value": "file"},
                  {"label": "邮件验证（需要人工点确认邮件）", "value": "email"},
              ],
              helper="DNS / CNAME 需要选 DNS 授权，流水线会自动添加并清理验证记录；"
                     "文件验证会写进网站根目录"),
            f("dnsAccessId", "DNS 授权", "access", accessCategory="dns", required=True,
              showWhen={"key": "dcvMethod", "values": ["dns", "dns-persist", "cname"]},
              helper="用于自动添加 TXT / CNAME 验证记录，可以是任意 DNS 服务商的授权"),
            f("httpUploadType", "验证文件写入方式", "select", default="local",
              showWhen={"key": "dcvMethod", "value": "file"},
              options=[
                  {"label": "写入本机目录", "value": "local"},
                  {"label": "上传到远程主机", "value": "ssh"},
              ]),
            f("httpWebRoot", "网站根目录", default="/var/www/html",
              showWhen={"key": "dcvMethod", "value": "file"},
              helper="CA 给的验证文件路径会拼在这个目录后面"),
            f("httpAccessId", "主机授权", "access", accessCategory="host",
              showWhen=[{"key": "dcvMethod", "value": "file"},
                        {"key": "httpUploadType", "value": "ssh"}]),
            f("keyType", "密钥算法", "select", default="rsa2048",
              options=[
                  {"label": "RSA 2048（兼容性最好）", "value": "rsa2048"},
                  {"label": "RSA 3072", "value": "rsa3072"},
                  {"label": "RSA 4096", "value": "rsa4096"},
              ],
              helper="私钥在本机生成，只把 CSR 提交给 CA，私钥不会经过网络"),
            f("validityMonths", "订单有效期（月）", "number", default=3,
              helper="3 表示 90 天；其他取值必须是 12 的倍数（12 = 1 年，24 = 2 年），"
                     "可用范围受产品限制"),
            f("email", "联系人邮箱", default="",
              helper="DV 证书的 CA 通知邮箱；OV / EV 会用作联系人邮箱（下面填了以那边为准）"),

            # ---------------- 组织信息（OV / EV 必填） ----------------
            f("organizationId", "已有组织 ID", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]},
              helper="填了已有组织 ID 就直接复用（其余组织字段可留空）；"
                     "第一次申请请把下面填全，CA 审核通过后会记住这个组织"),
            f("organizationName", "组织名称", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]},
              helper="与营业执照上的名称一致"),
            f("organizationAddress", "组织地址", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("organizationCity", "城市", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("organizationState", "省份 / 地区", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("organizationZipCode", "邮编", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("organizationCountry", "国家代码", default="CN",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]},
              helper="两位国家代码，中国大陆填 CN"),
            f("organizationTelephone", "组织电话", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]},
              helper="CA 会打这个电话做组织核验，务必能接通"),
            f("organizationUscc", "统一社会信用代码", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]},
              helper="国内企业填营业执照上的统一社会信用代码，海外企业可留空"),
            f("contactFirstName", "联系人名", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("contactLastName", "联系人姓", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("contactJobTitle", "联系人职位", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("contactTelephone", "联系人电话", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),
            f("contactEmail", "联系人邮箱", default="",
              group="组织与联系人（OV / EV）",
              showWhen={"key": "productId", "values": [
                  "trustasia_ssl_ov_v2", "trustasia_ssl_ov_wildcard_v2", "trustasia_ssl_ov_sans_v2",
                  "trustasia_ssl_ev_v2", "trustasia_ssl_ev_sans_v2"]}),

            # ---------------- 申请成功通知 ----------------
            f("notifyOnSuccess", "申请成功后发通知", "switch", default=True,
              group="成功通知",
              helper="证书签发成功就通过通知渠道发一条（域名 + 有效期），不用再单独加「发送通知」任务"),
            f("notificationId", "通知渠道", "notification",
              group="成功通知",
              helper="留空则用「通知渠道」里设为默认的那一条；没有配置渠道时静默跳过"),

            # ---------------- 高级 ----------------
            f("pollInterval", "轮询间隔（秒）", "number", default=10, group="高级设置"),
            f("timeout", "超时时间（秒）", "number", default=1800, group="高级设置",
              helper="DV 通常几分钟；OV / EV 要人工审核，建议 3600 以上"),
            f("userExternalId", "终端用户标识", default="", group="高级设置",
              helper="多租户平台必须填稳定且唯一的值（用于隔离组织复用与长效验证绑定）；"
                     "单账号自用可留空"),

            # ---------------- 续期与跳过 ----------------
            f("renewDays", "提前续期天数", "number", default=20, min=1, max=90,
              group="续期策略", placeholder="20",
              helper="证书剩余天数少于这个值才真正去下单；重复执行不会重复申请"),
            f("forceUpdate", "强制续期", "switch", default=False, group="续期策略",
              helper="开启后忽略剩余有效期与已有证书，每次执行都重新下单"),
            f("skipIfCertificateExists", "证书已存在且未过期就跳过", "switch", default=True,
              group="续期策略",
              helper="证书库里已有同域名的有效证书时跳过申请，继续执行后面的部署 / 通知步骤"),
            f("skipRecentMinutes", "刚申请过就跳过（分钟）", "number", default=10, min=0, max=1440,
              group="续期策略", placeholder="10",
              helper="这套域名在这么多分钟内已签出过证书就不再下单；填 0 关闭"),
        ],
        "outputs": CERT_OUTPUTS,
    },
    # ------------------------------ 部署
    {
        "type": "DeployToHost",
        "category": "主机",
        "name": "部署到远程主机",
        "group": "deploy",
        "icon": "server",
        "desc": "通过 SSH 上传证书文件到服务器并执行重载命令",
        "inputs": [
            f("accessId", "主机授权", "access", accessCategory="host", required=True),
            f("certPath", "证书文件路径", default="/etc/nginx/ssl/{domain}.crt",
              helper="支持变量 {domain}"),
            f("keyPath", "私钥文件路径", default="/etc/nginx/ssl/{domain}.key"),
            f("pfxPath", "PFX 文件路径", default="", helper="可选，留空则不生成"),
            f("pfxPassword", "PFX 密码", "password", default=""),
            f("reloadCmd", "重载命令", "textarea", default="nginx -s reload"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToLocal",
        "category": "主机",
        "name": "复制到本机目录",
        "group": "deploy",
        "icon": "folder",
        "desc": "将证书复制到本服务所在服务器的指定目录",
        "inputs": [
            f("dir", "目标目录", required=True, default="./data/deploy"),
            f("certName", "证书文件名", default="{domain}.crt"),
            f("keyName", "私钥文件名", default="{domain}.key"),
            f("pfxName", "PFX 文件名", default="", helper="可选"),
            f("pfxPassword", "PFX 密码", "password", default=""),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToAliyunCdn",
        "category": "云 CDN",
        "name": "部署到阿里云 CDN",
        "group": "deploy",
        "icon": "cloud",
        "desc": "上传证书并绑定到阿里云 CDN 加速域名",
        "inputs": [
            f("accessId", "阿里云授权", "access", accessCategory="cloud", required=True),
            f("domain", "CDN 域名", "tags", required=True,
              helper="可以从账号下自动拉取加速域名，支持多选并按证书域名自动选中",
              remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToTencentCdn",
        "category": "云 CDN",
        "name": "部署到腾讯云 CDN",
        "group": "deploy",
        "icon": "cloud",
        "desc": "上传证书并绑定到腾讯云 CDN 加速域名",
        "inputs": [
            f("accessId", "腾讯云授权", "access", accessCategory="cloud", required=True),
            f("domain", "CDN 域名", "tags", required=True,
              helper="可以从账号下自动拉取加速域名，支持多选并按证书域名自动选中",
              remote="cdnDomains", remoteFrom="accessId", autoMatchDomains=True),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToTencentEdgeOne",
        "category": "云 CDN",
        "name": "部署到腾讯云 EdgeOne",
        "group": "deploy",
        "icon": "cloud",
        "desc": "上传证书到腾讯云 SSL，并绑定到 EdgeOne 站点的加速域名（与腾讯云 CDN 共用授权）",
        "inputs": [
            f("accessId", "腾讯云授权", "access", accessCategory="cloud", required=True),
            f("domain", "EdgeOne 加速域名", "tags", required=True,
              helper="自动拉取账号下所有 EdgeOne 站点的加速域名，支持多选并按证书域名自动选中",
              remote="edgeoneDomains", remoteFrom="accessId", autoMatchDomains=True),
            f("certName", "证书名称", default="{domain}-{timestamp}",
              helper="上传到腾讯云 SSL 证书中心时使用的名称"),
            f("certId", "已有证书 ID", default="",
              helper="留空则上传新证书；填了就直接复用 SSL 证书中心的 CertId"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToQiniu",
        "category": "云 CDN",
        "name": "部署到七牛云",
        "group": "deploy",
        "icon": "cloud",
        "desc": "上传证书到七牛云 SSL 并绑定域名",
        "inputs": [
            f("accessId", "七牛云授权", "access", accessCategory="cloud", required=True),
            f("domain", "加速域名", required=True),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToBaota",
        "category": "面板",
        "name": "部署到宝塔面板",
        "group": "deploy",
        "icon": "panel",
        "desc": "调用宝塔面板接口，将证书部署到指定站点",
        "inputs": [
            f("accessId", "宝塔授权", "access", accessCategory="panel", required=True),
            f("autoMatch", "自动匹配站点", "switch", default=True,
              helper="按证书域名自动匹配宝塔里的站点；关掉后手动选"),
            # 站点名支持多选：一个证书要同时装到多个宝塔站点时，不用建多条任务。
            # 选项由「宝塔授权」自动拉取，会带上站点下的域名，便于区分同名站点。
            f("siteName", "站点名称（可多选）", "tags", required=False,
              helper="选好授权后会自动拉取宝塔站点（含站点域名），按证书域名选中匹配项；"
                     "可多选，留空则使用证书主域名",
              remote="sites", remoteFrom="accessId", autoMatchDomains=True),
        ],
        "outputs": [],
    },
    {
        "type": "DeployTo1Panel",
        "category": "面板",
        "name": "部署到 1Panel",
        "group": "deploy",
        "icon": "panel",
        "desc": "调用 1Panel 接口，将证书部署到指定网站",
        "inputs": [
            f("accessId", "1Panel 授权", "access", accessCategory="panel", required=True),
            f("autoMatch", "自动匹配网站", "switch", default=True,
              helper="按证书域名自动匹配 1Panel 里的网站；关掉后手动选"),
            f("websiteId", "网站（可多选）", "tags", required=False,
              helper="选好授权后会自动拉取 1Panel 网站，按证书域名选中匹配项；"
                     "可多选，留空则只上传证书不绑定",
              remote="sites", remoteFrom="accessId", autoMatchDomains=True),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToSynology",
        "category": "面板",
        "name": "部署到群晖 DSM",
        "group": "deploy",
        "icon": "panel",
        "desc": "上传证书到群晖 NAS，并替换系统默认证书（专业版能力）",
        "pro": True,
        "inputs": [
            f("accessId", "群晖授权", "access", accessCategory="panel", required=True),
            f("asDefault", "设为默认证书", "switch", default=True,
              helper="替换 DSM 与套件默认使用的证书"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToQnap",
        "category": "面板",
        "name": "部署到威联通 QTS",
        "group": "deploy",
        "icon": "panel",
        "desc": "上传证书到威联通 NAS 系统证书库（专业版能力）",
        "pro": True,
        "inputs": [
            f("accessId", "威联通授权", "access", accessCategory="panel", required=True),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToProxmox",
        "category": "面板",
        "name": "部署到 Proxmox VE",
        "group": "deploy",
        "icon": "panel",
        "desc": "上传证书到 PVE 节点，替换 Web 控制台证书（专业版能力）",
        "pro": True,
        "inputs": [
            f("accessId", "PVE 授权", "access", accessCategory="panel", required=True),
            f("restart", "上传后重启 pveproxy", "switch", default=True),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToVolcengine",
        "category": "云 CDN",
        "name": "托管到火山引擎证书中心",
        "group": "deploy",
        "icon": "cloud",
        "desc": "把证书上传到火山引擎证书中心，供 CDN / CLB 直接引用",
        "inputs": [
            f("accessId", "火山引擎授权", "access", accessCategory="cloud", required=True),
            f("certName", "证书名称", default="{domain}-{timestamp}"),
        ],
        "outputs": [],
    },
    {
        "type": "DeployToWebhook",
        "category": "其它",
        "name": "推送到自定义接口",
        "group": "deploy",
        "icon": "webhook",
        "desc": "将证书内容 POST 到自定义 HTTP 接口，适合自建部署服务",
        "inputs": [
            f("url", "接口地址", required=True, placeholder="https://example.com/api/deploy-cert"),
            f("token", "鉴权 Token", "password", default="",
              helper="将通过 Authorization: Bearer 头传递"),
            f("extraBody", "附加参数", "textarea", default="{}",
              helper="JSON 对象，会合并到请求体中"),
        ],
        "outputs": [],
    },
    # ------------------------------ 部署：扩展
    *_EXT_DEPLOY_PLUGINS,
    *_EXTRA_DEPLOY_PLUGINS,
    # ------------------------------ 通知
    {
        "type": "Notify",
        "name": "发送通知",
        "group": "notify",
        "icon": "bell",
        "desc": "通过已配置的通知渠道发送流水线执行结果",
        "inputs": [
            f("notificationId", "通知渠道", "notification", required=True,
              helper="在「通知管理」中添加渠道；不选则使用默认渠道"),
            f("title", "通知标题", default="证书任务执行结果"),
            f("onlyOnError", "仅失败时通知", "switch", default=False),
        ],
        "outputs": [],
    },
]

# 有些插件是直接写在 TASK_PLUGINS 里的（没走 _deploy()），这里统一补上 logo/品牌色
#: 授权类型的 logo 图标名 → 品牌 key，部署任务据此复用同一张本地 SVG
_ICON_TO_BRAND: dict[str, str] = {}
for _key, (_logo_icon, _c, _s) in _ACCESS_VISUAL.items():
    if _logo_icon:
        _ICON_TO_BRAND.setdefault(_logo_icon, _key)


def _logo_file_of(icon: str, folder: str, key: str) -> str:
    """图标名 → 本地 logo 路径。

    能对上授权类型里同一品牌的直接复用那张（/logos/access/<品牌>.<ext>，
    后缀跟着实际文件走），对不上的落到自己的目录（/logos/issuer、/logos/cert）。
    """
    brand = _ICON_TO_BRAND.get(icon or "")
    if brand:
        return _brand_logo(brand)
    return f"/logos/{folder}/{key}.svg" if key else ""

for _plugin in TASK_PLUGINS:
    if _plugin.get("group") == "deploy":
        _logo, _color = _DEPLOY_VISUAL.get(_plugin["type"], ("", "#909399"))
        _plugin.setdefault("logo", _logo)
        _plugin.setdefault("color", _color)
        _plugin.setdefault("favicon", "")
        _plugin.setdefault("short", _DEPLOY_SHORT.get(_plugin["type"], ""))
        # 先看显式指定，再按图标名反查同一品牌，最后落到本任务自己的 SVG
        _brand = (_DEPLOY_LOGO_BRAND.get(_plugin["type"])
                  or _ICON_TO_BRAND.get(_plugin.get("logo") or ""))
        _plugin.setdefault(
            "logoFile",
            _brand_logo(_brand) if _brand else f"/logos/task/{_plugin['type']}.svg")
    else:
        _logo, _color = _TASK_VISUAL.get(_plugin["type"], ("", "#909399"))
        _plugin.setdefault("logo", _logo)
        _plugin.setdefault("color", _color)

# ---------------------------------------------------------------- 授权类型精确匹配
# 只按「分类」（cloud / host / panel）过滤是不够的：宝塔、1Panel、群晖、威联通、PVE、
# NPM、雷池全都属于「面板」，只按分类过滤时「部署到群晖」的授权下拉里会混进宝塔授权，
# 选错了要到部署时才报错。这里给每个部署任务声明它认的授权类型，前端下拉严格照此过滤，
# 引擎执行前再校验一遍。
_DEPLOY_ACCESS_TYPES: dict[str, list[str]] = {
    # 主机（SSH）
    "DeployToHost": ["ssh"], "DeployToNginx": ["ssh"], "DeployToApache": ["ssh"],
    "DeployToHaproxy": ["ssh"], "DeployToTomcat": ["ssh"], "DeployToIis": ["ssh"],
    "DeployToOpenwrt": ["ssh"], "DeployToScript": ["ssh"],
    "DeployRunCommand": ["ssh"], "DeployToFtp": ["ftp"],
    # 面板 / 集群
    "DeployToBaota": ["baota"], "DeployTo1Panel": ["1panel"],
    "DeployToSynology": ["synology"], "DeployToQnap": ["qnap"],
    "DeployToProxmox": ["proxmox"], "DeployToNpm": ["npm"],
    "DeployToK8sSecret": ["k8s"], "DeployToSafeline": ["safeline"],
    "DeployToK8sIngress": ["k8s"],
    # 云厂商
    "DeployToAliyunCdn": ["aliyun"], "DeployToAliyunOss": ["aliyun"],
    "DeployToAliyunDcdn": ["aliyun"], "DeployToAliyunLive": ["aliyun"],
    "DeployToAliyunVod": ["aliyun"], "DeployToAliyunSlb": ["aliyun"],
    "DeployToTencentCdn": ["tencentcloud"], "DeployToTencentCos": ["tencentcloud"],
    "DeployToTencentClb": ["tencentcloud"], "DeployToTencentEdgeOne": ["tencentcloud"],
    "DeployToHuaweiObs": ["huawei"],
    "DeployToVolcengine": ["volcengine"], "DeployToVolcengineTos": ["volcengine"],
    "DeployToVolcengineCdn": ["volcengine"], "DeployToVolcengineLive": ["volcengine"],
    "DeployToAwsS3": ["aws"], "DeployToAwsCloudfront": ["aws"],
    "DeployToAwsAcm": ["aws"],
    "DeployToS3": ["s3"], "DeployToCloudflareR2": ["r2"],
    "DeployToQiniu": ["qiniu"], "DeployToQiniuKodo": ["qiniu"],
    "DeployToFastly": ["fastly"], "DeployToCtyunCdn": ["ctyun"],
    "DeployToJDCloudCert": ["jdcloud"], "DeployToJDCloudCdn": ["jdcloud"],
    "DeployToBaiduCdn": ["baiducloud"],
    "DeployToDogeCdn": ["dogecloud"], "DeployToYidunCdn": ["yidun"],
    "DeployToKuocaiCdn": ["kuocaicdn"], "DeployToWoaiCdn": ["woai"],
    "DeployToUpyun": ["upyun"], "DeployToBaishanCdn": ["baishan"],
}

#: 申请类任务的授权字段：云厂商写死对应类型，DNS 授权按「有 DNS 能力」的类型过滤
_DNS_CAPABLE_TYPES = sorted(_DNS_CAPABLE)
_CERT_ACCESS_TYPES: dict[str, dict[str, list[str]]] = {
    "CertApply": {"eabAccessId": ["eab"], "dnsAccessId": _DNS_CAPABLE_TYPES,
                  "httpAccessId": ["ssh"]},
    "CertApplyVolcengine": {"accessId": ["volcengine"], "dnsAccessId": _DNS_CAPABLE_TYPES},
    "CertApplyAliyun": {"accessId": ["aliyun"], "dnsAccessId": _DNS_CAPABLE_TYPES},
    "CertApplyTencent": {"accessId": ["tencentcloud"], "dnsAccessId": _DNS_CAPABLE_TYPES},
    "CertApplyTrustAsia": {"accessId": ["trustasia"], "dnsAccessId": _DNS_CAPABLE_TYPES,
                           "httpAccessId": ["ssh"]},
}

for _plugin in TASK_PLUGINS:
    _allowed_map: dict[str, list[str]] = dict(_CERT_ACCESS_TYPES.get(_plugin["type"]) or {})
    if _plugin.get("group") == "deploy":
        _deploy_types = _DEPLOY_ACCESS_TYPES.get(_plugin["type"])
        if _deploy_types:
            _allowed_map.setdefault("accessId", _deploy_types)
    if not _allowed_map:
        continue
    for _input in _plugin.get("inputs") or []:
        if _input.get("component") != "access":
            continue
        _allowed = _allowed_map.get(_input["key"])
        if _allowed:
            _input["accessTypes"] = list(_allowed)


TASK_PLUGIN_MAP = {p["type"]: p for p in TASK_PLUGINS}

PLUGIN_GROUPS = [
    {"key": "cert", "name": "证书申请"},
    {"key": "deploy", "name": "证书部署"},
    {"key": "notify", "name": "通知"},
]

# ---------------------------------------------------------------- 通知渠道
NOTIFY_TYPES: dict[str, dict[str, Any]] = {
    "email": {
        "name": "邮件通知",
        "inputs": [
            f("smtpHost", "SMTP 服务器", required=True, placeholder="smtp.qq.com"),
            f("smtpPort", "端口", "number", default=465),
            f("ssl", "使用 SSL", "switch", default=True),
            f("username", "发件邮箱", required=True),
            f("password", "邮箱密码/授权码", "password", required=True),
            f("from", "发件人", default="", helper="留空则使用发件邮箱"),
            f("to", "收件人", "tags", required=True, helper="多个邮箱回车分隔"),
        ],
    },
    "webhook": {
        "name": "Webhook",
        "inputs": [
            f("url", "地址", required=True),
            f("method", "方法", "select", default="POST",
              options=[{"label": "POST", "value": "POST"}, {"label": "GET", "value": "GET"}]),
            f("headers", "请求头", "textarea", default="{}", helper="JSON 对象"),
        ],
    },
    "dingtalk": {
        "name": "钉钉机器人",
        "inputs": [
            f("webhook", "Webhook 地址", required=True),
            f("secret", "加签密钥", "password", default=""),
        ],
    },
    "feishu": {
        "name": "飞书机器人",
        "inputs": [
            f("webhook", "Webhook 地址", required=True),
            f("secret", "签名密钥", "password", default=""),
        ],
    },
    "wecom": {
        "name": "企业微信机器人",
        "inputs": [f("webhook", "Webhook 地址", required=True)],
    },
    "anpush": {
        "name": "AnPush",
        "pro": True,
        "inputs": [
            f("token", "Token", "password", required=True,
              helper="AnPush 应用 Token，可在其控制台获取"),
            f("channel", "通道 ID", default="", helper="留空则推送到默认通道"),
        ],
    },
    "serverchan": {
        "name": "Server 酱",
        "inputs": [f("sendKey", "SendKey", "password", required=True)],
    },
    "pushplus": {
        "name": "PushPlus",
        "inputs": [
            f("token", "Token", "password", required=True),
            f("topic", "群组编码", default=""),
        ],
    },
    "telegram": {
        "name": "Telegram",
        "inputs": [
            f("botToken", "Bot Token", "password", required=True),
            f("chatId", "Chat ID", required=True),
        ],
    },
    "bark": {
        "name": "Bark",
        "inputs": [
            f("url", "服务地址", default="https://api.day.app"),
            f("deviceKey", "Device Key", "password", required=True),
        ],
    },
}

# ---------------------------------------------------------------- ACME 服务商
ACME_PROVIDERS = {
    "letsencrypt": {
        "name": "Let's Encrypt",
        "directory": "https://acme-v02.api.letsencrypt.org/directory",
    },
    "zerossl": {
        "name": "ZeroSSL",
        "directory": "https://acme.zerossl.com/v2/DV90",
        "eab": True,
    },
    "google": {
        "name": "Google Trust Services",
        "directory": "https://dv.acme-v02.api.pki.goog/directory",
        "eab": True,
    },
    "litessl": {
        # FreeSSL.cn 的 ACME v2 服务（LiteSSL 公益项目，签发方 TrustAsia）。
        # 老地址 https://acme.freessl.cn/directory 已下线（域名不再解析），
        # 现行目录是 acme.litessl.com，且 meta.externalAccountRequired=true（必须带 EAB）。
        "name": "FreeSSL / LiteSSL",
        "directory": "https://acme.litessl.com/acme/v2/directory",
        "eab": True,
    },
    "buypass": {
        "name": "Buypass",
        "directory": "https://api.buypass.com/acme/directory",
    },
    "custom": {"name": "自定义 ACME", "directory": ""},
}

# ---------------------------------------------------------------- 支持的证书
# 概览页「支持的证书」卡片的数据源。
# 名称、密钥类型、域名验证方式全部从上面的注册表推导，这里只补充有效期、
# 适用场景这类纯展示信息 —— 以后接新的 CA，只加一条元数据即可，前端零改动。
# logo 是 Iconify 图标名（前端 ArtSvgIcon 联网加载）；没有官方 logo 的来源留空，
# 前端会退化成「品牌色 + 首字母」的字母牌，比硬塞一个不相干的图标更像样。
_CERT_SOURCE_META: dict[str, dict[str, Any]] = {
    "letsencrypt": {
        "desc": "公益 CA，DV 证书 90 天有效，到期前自动重签",
        "validity": "90 天",
        "logo": "logos:letsencrypt",
        "color": "#003a70",
    },
    "zerossl": {
        "desc": "免费单域名 DV 证书，首次使用自动换取 EAB 凭据",
        "validity": "90 天",
        # Iconify 没有 ZeroSSL 品牌图标：logo 是本地手绘矢量（logos/issuer/zerossl.svg）
        "logo": "",
        "color": "#1b6ee0",
    },
    "google": {
        "desc": "Google Trust Services，国内链路稳定，需 EAB 凭据",
        "validity": "90 天",
        "logo": "logos:google-icon",
        "color": "#4285f4",
    },
    "buypass": {
        "desc": "Buypass Go，半年有效期，续期频率更低",
        "validity": "180 天",
        "logo": "",
        "color": "#00979d",
    },
    "litessl": {
        "desc": "FreeSSL.cn 的 ACME 服务（LiteSSL 公益项目，TrustAsia 签发），"
                "在 FreeSSL「证书自动化 → ACME 账户管理」建 EAB 凭据后全自动申请",
        "validity": "90 天",
        "logo": "",
        "color": "#6a4dfd",
    },
    "custom": {
        "desc": "接入任意 ACME v2 兼容 CA，例如 ssl.com、自建 step-ca",
        "validity": "以 CA 为准",
        "logo": "mdi:shield-key-outline",
        "color": "#6b7280",
    },
}

# 非 ACME 来源的证书（云厂商签发 / 本地自签），按签发插件生成
_CERT_PLUGIN_META: dict[str, dict[str, Any]] = {
    "CertApplyVolcengine": {
        "name": "火山引擎免费证书",
        "kind": "云厂商",
        "desc": "火山引擎证书中心签发的免费 DV 证书，自动完成 DNS 验证",
        "validity": "以控制台为准",
        "challenge": "DNS 验证",
        "tags": ["免费", "DV"],
        "logo": "thesvg-color:volcengine",
        "color": "#1664ff",
    },
    "CertApplyAliyun": {
        "name": "阿里云免费证书",
        "kind": "云厂商",
        "desc": "阿里云数字证书管理服务的个人测试证书（DigiCert DV），自动写 DNS 验证",
        "validity": "3 个月",
        "challenge": "DNS 验证",
        "tags": ["免费", "DV", "国内 CA"],
        "logo": "thesvg-color:alibabacloud",
        "color": "#ff6a00",
    },
    "CertApplyTencent": {
        "name": "腾讯云免费证书",
        "kind": "云厂商",
        "desc": "腾讯云 SSL 的 TrustAsia C1 DV Free，自动写 DNS 验证",
        "validity": "3 个月",
        "challenge": "DNS 验证",
        "tags": ["免费", "DV", "国内 CA"],
        "logo": "thesvg-color:tencentcloud",
        "color": "#006eff",
    },
    "CertApplyTrustAsia": {
        "name": "TrustAsia 亚洲诚信",
        "kind": "商业 CA",
        "desc": "TrustAsia（CertCloud）下单签发，支持 DV / OV / EV、泛域名与多域名；"
                "自动写 DNS / CNAME 验证记录",
        "validity": "3 个月起（按产品）",
        "challenge": "DNS / CNAME / 文件验证",
        "tags": ["DV", "OV", "EV", "泛域名", "国内 CA"],
        "logo": "",
        "logoBrand": "trustasia",
        "color": "#c6272a",
    },
    "CertApplySelfSigned": {
        "name": "自签证书",
        "kind": "本地",
        "desc": "本地生成自签名证书，无需域名与网络，用于验证流水线流程",
        "validity": "自定义（默认 365 天）",
        "challenge": "无需验证",
        "tags": ["本地", "测试"],
        "logo": "mdi:file-certificate-outline",
        "color": "#8b5cf6",
    },
}


def _option_labels(plugin_type: str, key: str) -> list[str]:
    """取插件某个下拉字段的选项文案。

    注册表里的文案带说明，例如「ECC 256（推荐）」，展示时只留前半段。
    """
    plugin = TASK_PLUGIN_MAP.get(plugin_type) or {}
    for item in plugin.get("inputs") or []:
        if item.get("key") == key:
            return [str(o.get("label", "")).split("（")[0].strip()
                    for o in item.get("options") or []]
    return []


def _build_supported_certs() -> list[dict[str, Any]]:
    acme_key_types = _option_labels("CertApply", "keyType")
    acme_challenges = " / ".join(_option_labels("CertApply", "challengeType"))
    items: list[dict[str, Any]] = []

    for key, provider in ACME_PROVIDERS.items():
        meta = _CERT_SOURCE_META.get(key, {})
        # 自定义 ACME 的免费与否、能否签泛域名都取决于对接的 CA，不做承诺
        tags = ["自定义", "ACME v2"] if key == "custom" else ["免费", "DV", "泛域名"]
        if provider.get("eab"):
            tags.append("需 EAB")
        items.append({
            "key": f"acme:{key}",
            "name": provider["name"],
            "kind": "ACME CA",
            "desc": meta.get("desc", ""),
            "validity": meta.get("validity", ""),
            "challenge": acme_challenges if key != "custom" else "取决于 CA",
            "keyTypes": acme_key_types,
            "tags": tags,
            "taskType": "CertApply",
            "logo": meta.get("logo", ""),
            "favicon": "",
            "logoFile": _logo_file_of(meta.get("logo", ""), "issuer", key),
            "color": meta.get("color", ""),
        })

    for plugin_type, meta in _CERT_PLUGIN_META.items():
        if plugin_type not in TASK_PLUGIN_MAP:  # 插件被裁掉时不影响概览页
            continue
        items.append({
            "key": plugin_type,
            "name": meta["name"],
            "kind": meta["kind"],
            "desc": meta["desc"],
            "validity": meta["validity"],
            "challenge": meta["challenge"],
            "keyTypes": _option_labels(plugin_type, "keyType"),
            "tags": meta["tags"],
            "taskType": plugin_type,
            "logo": meta.get("logo", ""),
            "favicon": "",
            "logoFile": (_brand_logo(meta["logoBrand"]) if meta.get("logoBrand")
                         else _logo_file_of(meta.get("logo", ""), "cert", plugin_type)),
            "color": meta.get("color", ""),
        })

    # 不走「申请」的第三种来源：把已有的证书文件导入证书库
    items.append({
        "key": "import",
        "name": "上传自有证书",
        "kind": "导入",
        "desc": "其它渠道买来的证书，粘贴 PEM 直接入库，同样能部署和监控到期",
        "validity": "以证书为准",
        "challenge": "无需验证",
        "keyTypes": ["PEM（crt + key）", "PFX 导出后转 PEM"],
        "tags": ["免费", "自有证书"],
        "taskType": "",
        "logo": "mdi:file-upload-outline",
        "favicon": "",
        "logoFile": "/logos/cert/import.svg",
        "color": "#e6a23c",
    })
    return items


# 申请类任务：任务选择器与概览页共用同一张品牌 logo（授权类型里那份本地图）
for _plugin in TASK_PLUGINS:
    _cert_meta = _CERT_PLUGIN_META.get(_plugin["type"])
    if not _cert_meta:
        continue
    _plugin.setdefault("logo", _cert_meta.get("logo", ""))
    _plugin.setdefault("color", _cert_meta.get("color", ""))
    _plugin.setdefault(
        "logoFile",
        _brand_logo(_cert_meta["logoBrand"]) if _cert_meta.get("logoBrand")
        else _logo_file_of(_cert_meta.get("logo", ""), "cert", _plugin["type"]))


#: 证书来源按用途分组：group=apply 能签发，group=import 只能导入
_CERT_GROUP_BY_TYPE = {
    "import": "import",
}


def _cert_group(item: dict) -> str:
    return _CERT_GROUP_BY_TYPE.get(item["key"], "apply")


SUPPORTED_CERTS = _build_supported_certs()
for _item in SUPPORTED_CERTS:
    _item["group"] = _cert_group(_item)

#: 证书能部署到哪些平台（按插件分类汇总，概览页用来告诉用户「签完能装到哪」）
def _build_deploy_targets() -> list[dict]:
    """按分类汇总部署插件，并带上插件名与 logo——概览页要把「能装到哪」逐个列出来。"""
    order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for plugin in TASK_PLUGINS:
        if plugin.get("group") != "deploy":
            continue
        category = plugin.get("category") or "其它"
        if category not in grouped:
            grouped[category] = []
            order.append(category)
        grouped[category].append({
            "type": plugin.get("type", ""),
            "name": plugin.get("name") or plugin.get("type", ""),
            "logo": plugin.get("logo", ""),
            "logoFile": plugin.get("logoFile", ""),
            "short": plugin.get("short", ""),
            "color": plugin.get("color", ""),
        })
    return [{"name": name, "count": len(grouped[name]), "plugins": grouped[name]}
            for name in order]


DEPLOY_TARGETS = _build_deploy_targets()

DNS_PROVIDERS = {
    "aliyun": {"name": "阿里云 DNS", "accessType": "aliyun"},
    "tencentcloud": {"name": "腾讯云 DNSPod", "accessType": "tencentcloud"},
    "cloudflare": {"name": "Cloudflare", "accessType": "cloudflare"},
    "huawei": {"name": "华为云 DNS", "accessType": "huawei"},
    "godaddy": {"name": "GoDaddy", "accessType": "godaddy"},
    "namesilo": {"name": "NameSilo", "accessType": "namesilo"},
}
