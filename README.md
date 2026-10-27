# CertHub

基于 **Python（FastAPI）+ Art Design Pro 3.0.2（Vue3）** 的证书自动化管理系统。

> **完全免费、无任何付费/授权/套餐模块**，不含流水线数量、站点监控数量、通知渠道等任何限制。

---

## 一、开发规范（必读）

工程约定写在 [`AGENTS.md`](./AGENTS.md)，其中一条是**铁律**：

> **凭据一律明文查看。** 授权、通知渠道、证书私钥等字段后端明文返回，
> 不在接口层打码；密码框用「小眼睛」切换明文/星号；编辑时留空表示不修改，
> 后端负责还原旧值 —— 绝不把用户密钥写成空串。

其余约定：插件元数据驱动（加插件只改后端 `plugins.py`）、概览页必须逐个列出
所有支持的来源与部署平台并配 logo、业务异常不打堆栈、新增插件必须有冒烟覆盖。

---

## 二、技术栈

**后端**
- Python 3.11+ / FastAPI / SQLAlchemy 2 / SQLite（可切 PostgreSQL、MySQL）
- APScheduler（定时流水线、站点监控、到期提醒）
- cryptography（密钥、CSR、证书解析、PFX/P7B 导出）
- 自研 ACME v2 客户端（JWS 签名、订单、挑战、EAB）
- paramiko（SSH/SFTP 部署）

**前端**
- Art Design Pro 3.0.2（Vue 3.5 + TypeScript + Vite 7 + Element Plus + Pinia）
- 插件表单「元数据驱动」：后端声明 inputs，前端动态渲染

---

## 三、目录结构

```
certd-lite/
├── backend/
│   ├── app/
│   │   ├── main.py            # 入口、路由注册、静态托管
│   │   ├── config.py          # 配置（环境变量覆盖）
│   │   ├── db.py / models.py  # 数据库与模型
│   │   ├── security.py        # 密码哈希、JWT、AES-GCM 加密
│   │   ├── plugins.py         # ★ 插件元数据注册表（驱动前端表单）
│   │   ├── templates.py       # ★ 流水线模板（7 套常用组合）
│   │   ├── deps.py            # 依赖注入、统一响应
│   │   ├── routers/           # auth/user/pipeline/history/access/cert/...
│   │   └── services/
│   │       ├── acme.py        # ACME v2 客户端
│   │       ├── aliyun.py      # 阿里云 RPC 签名（CAS / 云解析共用）
│   │       ├── aliyun_cas.py  # 阿里云数字证书管理服务
│   │       ├── tencent_ssl.py # 腾讯云 SSL 免费证书
│   │       ├── dns.py         # 6 家 DNS 服务商适配
│   │       ├── deploy.py      # 9 类部署插件
│   │       ├── notify.py      # 9 种通知渠道
│   │       ├── engine.py      # 流水线执行引擎
│   │       ├── certutil.py    # 证书工具
│   │       └── scheduler.py   # 定时调度
│   ├── data/                  # SQLite、证书文件、密钥（运行时生成）
│   ├── requirements.txt
│   └── run.py
├── frontend/                  # Art Design Pro 3.0.2
│   └── src/
│       ├── api/certd.ts       # 全部接口封装
│       ├── router/modules/certd.ts
│       └── views/certd/       # 14 个页面
├── start.bat / start.sh
└── README.md
```

---

## 四、快速开始

> **一键启动**：Windows 双击 `start.bat`，Linux/macOS 执行 `bash start.sh`。
> 脚本会自动建虚拟环境、装依赖、构建前端（已有 `frontend/dist` 时跳过）并启动服务，
> 完成后访问 http://127.0.0.1:8000 即可。下面是手动步骤。

### 1. 后端

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

启动后：
- API 文档：http://127.0.0.1:8000/api/docs
- 健康检查：http://127.0.0.1:8000/api/health

### 2. 前端

```bash
cd frontend
pnpm install        # 或 npm install --legacy-peer-deps
pnpm dev
```

访问 http://localhost:3006

> 开发环境已通过 Vite 代理把 `/api` 转发到 `http://127.0.0.1:8000`。

### 3. 默认账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| admin | 123456 | 管理员 |

首次登录后请在「个人中心」修改密码。

---

## 五、生产部署

```bash
# 1. 构建前端
cd frontend
pnpm build            # 产物在 frontend/dist

# 2. 启动后端（自动托管 dist）
cd ../backend
python run.py
```

后端检测到 `frontend/dist` 存在时会自动托管静态资源，访问 http://127.0.0.1:8000 即可。

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CERTD_PORT` | 8000 | 监听端口 |
| `CERTD_SECRET_KEY` | 自动生成 | JWT / 配置加密密钥，**生产务必固定** |
| `CERTD_DB_URL` | sqlite:///data/certd.db | 数据库连接串 |
| `CERTD_ADMIN_USERNAME` / `CERTD_ADMIN_PASSWORD` | admin / 123456 | 首次初始化的管理员 |
| `CERTD_DATA_DIR` | backend/data | 数据目录 |
| `CERTD_DNS_WAIT` | 10 | DNS 记录生效等待基数（秒） |

---

## 六、核心流程说明

### 流水线模型

```json
{
  "stages": [
    {
      "id": "s1",
      "title": "申请证书",
      "tasks": [
        {
          "id": "t1",
          "type": "CertApply",
          "title": "证书申请",
          "input": {
            "domains": ["example.com", "*.example.com"],
            "provider": "letsencrypt",
            "email": "admin@example.com",
            "challengeType": "dns",
            "dnsAccessId": 1,
            "keyType": "ec256",
            "renewDays": 20
          },
          "continueOnError": false
        }
      ]
    },
    {
      "id": "s2",
      "title": "部署证书",
      "tasks": [
        {
          "id": "t2",
          "type": "DeployToHost",
          "input": {
            "accessId": 2,
            "certPath": "/etc/nginx/ssl/{domain}.crt",
            "keyPath": "/etc/nginx/ssl/{domain}.key",
            "reloadCmd": "nginx -s reload"
          }
        }
      ]
    }
  ],
  "triggers": [{ "id": "tr1", "type": "timer", "cron": "0 3 * * *", "enabled": true }]
}
```

- 阶段串行、任务串行；任务失败默认中断，`continueOnError` 可忽略错误
- 证书任务输出 `cert.crt` / `cert.key` / `cert.domain` / `cert.expiresTime`，后续任务用 `{{ cert.domain }}` 引用
- 未到续期时间（`renewDays`）时自动跳过，避免频繁申请触发 CA 限流

### 证书申请流程

1. 读取/创建 ACME 账户（密钥按 用户 + CA 隔离保存，加密存储）
2. 创建订单 → 逐个域名完成 dns-01 / http-01 挑战
3. 轮询授权状态 → 生成密钥与 CSR → finalize → 下载证书链
4. 保存证书（私钥 AES-GCM 加密入库）+ 写入 `data/certs/{userId}/`
5. 输出变量供部署任务使用

### 实时签发日志（SSE）

签发一次要几十秒到几分钟，等跑完再看日志等于黑盒。这里做成「点运行就弹日志」的体验：

- `POST /api/pipeline/{id}/run` **先建历史记录再提交线程池**，直接返回 `historyId`——
  前端拿到 id 立刻订阅，不用轮询列表去猜哪条是新记录
- `GET /api/history/{id}/stream` 是 SSE 接口，推三类消息：
  - 默认 `data: {"line": "..."}`：逐行日志
  - `event: tasks`：任务进度快照（含阶段、状态、耗时），前端渲染成任务条
  - `event: status` / `event: end`：状态变化与结束信号
- 记录跑完后频道仍保留 5 分钟，期间打开详情还能看；更早的记录直接**回放数据库里的日志**
  再发 `end`，所以「看历史」和「看实时」是同一个组件、同一条接口
- `POST /api/history/{id}/stop` 是**协作式停止**：任务之间、以及 ACME 轮询的每一轮检查标志位，
  正在飞的单次 HTTP 请求不会被打断
- 执行状态全在进程内存里，进程被强杀会留下 `status=running` 的记录。启动时
  `engine.cleanup_stale_runs()` 会把它们标成 `failed` 并在日志末尾补一句「服务重启，本次执行已中断」，
  否则前端会一直转圈等一个不会来的 `end` 事件

实现上是一个进程内发布/订阅（`services/logbus.py`）：runner 每写一行就 `publish`，
SSE 生成器按「从第 N 行开始」阻塞等待新行。用 `threading.Condition` 而不是 `asyncio.Queue`，
是因为 runner 在 `ThreadPoolExecutor` 里、同步生成器在线程池里，两边都是同步代码，
跨线程调度反而更容易出错。

> 频道是**进程内**的：多 worker 部署时 SSE 必须落在跑任务的那个进程上。
> 本项目默认单进程 uvicorn，如果要多 worker，需要把 logbus 换成 Redis pub/sub。

### ACME 账户与 EAB 凭据（都在授权管理里）

证书申请需要的两样东西都属于「凭据」，因此统一放在**授权管理 → 证书签发**分类下，
系统设置里不再出现任何 ACME / EAB 配置项：

| 授权类型 | 字段 | 说明 |
| --- | --- | --- |
| **ACME 账户** | 联系邮箱、账户私钥、账户 URL | 邮箱必填；私钥留空即可，首次申请时自动生成并**回写到这条授权**，
  |  |  | 注册失败（比如 EAB 过期）时也不会每次重试都换一把新 key |
| **EAB 凭据** | EAB 类型、KID、HMAC Key、邮箱 | Google 的 keyId / b64MacKey、SSL.com 的 Account Key；类型要和任务里选的 CA 一致 |

任务侧只引用授权 ID：`accountAccessId`（必填）与 `eabAccessId`（仅 Google / 自定义 CA 显示）。
换账号时改授权，所有引用它的流水线一起生效，不用逐条改流水线。
### 网络设置（HTTP 代理 + 反向代理域名）

国内机器直连 Google Trust Services / ZeroSSL 这类海外接口，经常超时、握手被打断，
或者直接 `WinError 10054` 被重置。这里用两层手段：**系统级 HTTP 代理** 与
**CA 反向代理域名**。

**系统设置 → 网络设置**（`sys_setting.network`）：

- `httpProxy` / `httpsProxy`：与 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量同一套语义——
  填了就默认所有出网请求都走代理；不填就直连。支持 `http://`、`https://`、`socks5://`
  （socks 依赖 `socksio`，已写进 `requirements.txt`）。
- `noProxy`：`NO_PROXY` 排除清单，逗号/空格/换行分隔，支持
  `localhost,127.0.0.1,.example.com,192.168.*` 这类写法，命中的请求直连。
- 调用方显式 `trust_env=False`（内网 MinIO、回环地址）时同样跳过代理。
- 「测试连通性」一次给你三条链路的结论：直连、走代理、走反代域名，各带耗时与错误原因。

**反向代理域名**：把 CA 端点域名换成反代域名，只替换实际传输地址，
JWS 里签名用的仍是 ACME 原始 URL（协议要求）：

| CA 端点 | 默认反代域名 |
| --- | --- |
| `acme-v02.api.letsencrypt.org` | `le.px.certd.handfree.work` |
| `dv.acme-v02.api.pki.goog` | `gg.px.certd.handfree.work` |

证书申请任务里还能单独控制：`useProxy`（「使用代理访问 CA」）与
`reverseProxy`（「自定义反代地址」）。不勾不填时按「先直连、连不上再自动切反代」执行；
填了就强制走你自己反代出来的域名。

执行日志里会写明实际走了哪条路：
`直连 dv.acme-v02.api.pki.goog 失败（ConnectError），自动改用反向代理：gg.px…`，
或者 `网络代理：127.0.0.1:7890（系统设置 → 网络设置）`。

实现上两个入口（`services/net.py`）：

| 场景 | 入口 | 做法 |
| --- | --- | --- |
| 一次性的 `httpx.get/post` | `net.get/post/request` | 按协议取 http/https 代理，命中 noProxy 或 `trust_env=False` 时直连 |
| 复用的 `httpx.Client`（ACME、DNS） | `net.client()` / `net.proxy_mounts()` | 按协议挂代理 transport，noProxy 命中的域名挂直连 transport |

### 编辑页内联日志与阶段标色

「流水线编辑」页（`pipeline/detail.vue`）里点「保存并运行」，日志不再弹抽屉，而是
**直接出现在阶段列表下方**，边跑边看：

- 日志面板高度 460px，可「收起日志 / 关闭」；关掉后阶段颜色仍然保留
- **逐行词法高亮**：时间戳、`===== 阶段 =====`、`[任务名]` 前缀、URL / 域名 / IP、
  PEM 标记、JSON 键名各用一种颜色；「成功 / 完成」绿、「失败 / 错误」红、「警告 / 跳过」黄。
  全部走 Vue 的文本节点渲染（不用 `v-html`），日志里的用户数据不会被当成 HTML 执行
- **阶段标色**：阶段里任一任务失败 → 整条红色左边框；全部跑完 → 绿色；还有任务在跑 → 黄色脉冲。
  数据来源是 SSE 的 `event: tasks`（每个任务带 `stage` 字段），跑完再刷一次 `lastRun`，
  所以关掉日志面板、刷新页面后颜色还在
- 网络类异常（`httpx` / `socket` / `ssl` 的异常）只写一行中文提示，不再把 Python 堆栈塞进日志

### 流水线模板与批量操作

- `GET /api/pipeline/templates` 返回 8 套模板骨架（Let's Encrypt + Nginx / SSH / 阿里云 CDN / 腾讯云 CDN / HTTP 验证 / 火山引擎免费证书 + CDN / 仅申请 / 自签测试）
- `POST /api/pipeline/from-template` 按模板创建，创建后跳到编辑页补充域名与授权
- `POST /api/pipeline/batch` 批量 `run` / `enable` / `disable` / `delete` / `notify` / `cron`，**逐条执行、单条失败不影响其余**，返回 `{success: [], failed: []}`

模板只提供结构，**不含任何凭据**（`accessId` 一律为空）——授权是每个账号私有的，硬编码没有意义。

批量改定时（`notify` / `cron`）时，服务端会**立即重算 `nextRunTime`**，不用等调度器下一轮 tick；
停用会清空下次执行时间，重新启用会按当前 cron 再算一遍。

### 多级菜单

菜单树是递归渲染的（`SidebarSubmenu.vue` 自调用），层级不设上限：

- 目录节点只写 `children`、不写 `component`，vue-router 会当作透明路由，子页面直接渲染到上层 `router-view`
- 默认跳转由 `MenuProcessor.resolveDefaultRedirect()` 递归推导，取第一个可访问的叶子节点
- 缩进通过 CSS 变量 `--menu-indent` 下发（`12 + level * 16`），而不是写死 padding —— 这样每深一层自动重算，不需要预设层数
- 折叠态统一复位为 20px，避免深层缩进把图标挤出 64px 宽的窄条

**不显示一级菜单**：根节点 `/cert` 只是路由容器，在 `meta` 上标记 `isMenuRoot: true`，
由 `menu store` 的 `flattenMenuRoots()` 把它的子项提升到一级，侧边栏就不会出现一个点不进去的空壳菜单。

> 这里有个坑：`MenuProcessor.getMenuList()` 的返回值**同时用于注册路由**，
> 所以展开只能放在 menu store（纯展示层）做。如果直接在 MenuProcessor 里展开，
> 顶层节点会丢失父级容器，动态路由注册失败，全站跳 500。

当前菜单：概览 / 证书签发（证书流水线、执行历史）/ 证书资产（证书库、站点监控）/
配置中心（授权、域名、通知）/ 系统管理（用户、审计、系统设置、开发者 → 开放接口）/ 个人中心。
面包屑会同步跳过 `isMenuRoot` 节点。

### 火山引擎免费证书

`app/services/volcengine.py` 实现了火山引擎的 HMAC-SHA256 签名（结构同 AWS SigV4）：

- 服务名 `certificate_service`，域名 `certificate-service.volcengineapi.com`，版本 `2024-10-01`
- `QuickApplyCertificate` 申请免费 DV 证书，`CertificateGetInstance` 轮询状态
- DNS 验证记录通过 `get_dcv_param()` 取回后，交给流水线的 DNS 授权自动写入，签发完成后自动清理
- `ImportCertificate` 把证书上传到证书中心，供 CDN / CLB 引用

**注意**：免费证书依赖账号的免费额度，额度用尽会直接返回业务错误；免费证书为单域名 DV，泛域名需要走 ACME。

### 阿里云 / 腾讯云免费证书

两家的免费 DV 证书各有一套 API，但流程和火山引擎一致（申请 → 写 DNS 验证 → 轮询 → 入库），
所以引擎里合成一个 `_apply_cloud_free()`，按插件类型分派：

| 厂商 | 客户端 | 关键接口 |
| --- | --- | --- |
| 阿里云 | `services/aliyun.py` + `services/aliyun_cas.py` | `CreateCertificateForPackageRequest`（`ProductCode=digicert-free-1-free` 即 3 个月个人测试证书）→ `DescribeCertificateState`（`domain_verify` / `certificate`，DNS 记录在 `RecordDomain`/`RecordValue`） |
| 腾讯云 | `services/tencent_ssl.py` | `ApplyCertificate`（`PackageType=83`）→ `DescribeCertificate`（`Status=1` 已签发，`DvAuthDetail` 给验证记录）→ `DownloadCertificate`（ZIP + base64，解出 crt/key） |

阿里云 RPC 签名复用 `services/aliyun.py`：**SignatureNonce 必须每次重新生成**。
阿里云对 15 分钟内重复的 nonce 直接判 `SignatureNonceUsed`（"Specified signature nonce was used already"），
早先授权测试里写死常量，表现为「第一次测试成功、之后每次都 400」。

腾讯云 SSL 的 TC3-HMAC-SHA256 与 `deploy.py` 里 CDN 那份是同构的（都签了 `x-tc-action`），改签名时两边要一起改。
两家的错误都先过「预检」再申请，**预检失败只记日志不中断** —— 常见情况是 AK 只有部署权限、没有列证书的读权限。

> 说明：这两条链路没有真实云账号可验证，只能确认「签名被对端接受」——
> 假凭据时拿到的是 `InvalidAccessKeyId.NotFound`（阿里云）与 `AuthFailure.SecretIdNotFound`（腾讯云），
> 而不是签名错误，说明签名/请求格式是对的。真正签发仍需自备账号与免费额度。

### 导入自有证书

`POST /api/cert/import` 接收 PEM（证书链 + 私钥），入库前校验两件事：
PEM 头是否齐全、证书与私钥是否成对（比较 SubjectPublicKeyInfo）。
导入的证书 `pipeline_id=0`，与流水线签发的证书完全等价 —— 因为部署与到期提醒读的都是证书库。

### 证书格式导出

`GET /api/cert/{id}/download?format=pem|der|pfx|p7b|jks|nginx&type=cert|key&password=xxx`

JKS 是 Sun 私有格式，无纯 Python 写入实现，服务端会先生成 PKCS#12 再调用 JDK `keytool` 转换。
服务端定位 `keytool` 的顺序：`PATH` → `JAVA_HOME` → `java -XshowSettings:properties` 解析出的 `java.home`
（Windows 的 javapath 目录里只有 `java.exe`，没有 `keytool`，所以第三步是必须的）。
未安装 JDK 时接口会返回明确提示，并建议改用 PFX —— Java 同样可以直接加载 PKCS#12。

### 通知渠道的返回码

钉钉、企业微信、飞书、Server酱、PushPlus 这些渠道有个共同的坑：**token 错了、机器人被移出群、
被限流时，它们依然返回 HTTP 200**，只在响应体里给一个非成功的 `errcode` / `code`。
只看 HTTP 状态码会把「没发出去」记成「执行成功」——证书到期提醒静默丢失，比报错更难发现。

所以每个渠道发送后都要过一次业务码校验（`notify._check_biz`）：

| 渠道 | 成功值 |
| --- | --- |
| 钉钉 / 企业微信 | `errcode == 0` |
| 飞书 | `code == 0` |
| PushPlus / Bark | `code == 200` |
| Server酱 | `code == 0` |
| Telegram | `ok == true` |

另外错误信息里只保留主机名（`notify._safe_url`）：钉钉/飞书把 token 放在 query，
Telegram/Bark 放在 path，整条 URL 打进执行日志等于把密钥写进历史记录。

---

## 七、部署插件一览

部署插件按**交付方式**归成四类，同类共用一套代码——同类插件的差别只是默认路径、
endpoint 和几个参数：

| 分类 | 数量 | 共同点 | 代码位置 |
| --- | --- | --- | --- |
| 对象存储 | 8 | 都是「PUT 一个文件」，差别在签名算法与 endpoint | `deploy_ext.py` |
| 主机 | 7 | 都是「传文件 + 执行重载命令」 | `deploy.py` / `deploy_ext.py` |
| 面板 | 8 | 调各自 HTTP 接口或 SSH | `deploy.py` / `deploy_ext.py` / `deploy_more.py` |
| 集群 | 1 | K8s Secret（API Server + Bearer Token） | `deploy_ext.py` |
| 云 CDN | 21 | 上传证书 + 绑定域名 | `deploy.py` / `deploy_ext.py` / `deploy_cn.py` / `deploy_more.py` |
| 其它 | 3 | Webhook / 邮件 / 远程脚本 | `deploy.py` / `deploy_ext.py` |

合计 **48 个部署插件**，与概览页「支持的证书 → 证书部署」里的数字一致。

### 对象存储（8）

| 插件 | Endpoint | 签名算法 |
| --- | --- | --- |
| 阿里云 OSS | `{bucket}.{region}.aliyuncs.com` | OSS V1（HMAC-SHA1） |
| 腾讯云 COS | `{bucket}.cos.{region}.myqcloud.com` | COS v5（q-sign-algorithm=sha1） |
| 华为云 OBS | `{bucket}.obs.{region}.myhuaweicloud.com` | AWS SigV4 |
| 火山引擎 TOS | `{bucket}.tos-{region}.volces.com` | AWS SigV4 |
| AWS S3 | `{bucket}.s3.{region}.amazonaws.com` | AWS SigV4 |
| Cloudflare R2 | `{bucket}.{accountId}.r2.cloudflarestorage.com` | AWS SigV4 |
| 七牛 Kodo | `{bucket}.s3-{region}.qiniucs.com` | AWS SigV4 |
| S3 兼容（MinIO / Ceph） | 自定义 | AWS SigV4 |

内网 endpoint（127./10./192.168./172.16-31.）会自动绕开系统代理，否则宿主机配了
`HTTP_PROXY` 时连本地 MinIO 会报一个看不出原因的 502。

### 主机（7）

远程主机（自定义路径/命令）、本机目录、Nginx、Apache、HAProxy、Tomcat、IIS。

- **HAProxy** 要的是「证书+私钥合并」的单文件 PEM，插件会自动拼好；
- **Tomcat** 用 PKCS#12，插件按 `pfxPassword` 现场生成 `.pfx`，需与 `server.xml` 的 `keystorePass` 一致；
- **IIS** 没有「证书文件」的概念，插件上传 PFX 后用 PowerShell `Import-PfxCertificate` 导入
  `LocalMachine\My`，再 `netsh http update sslcert` 绑定站点。

### 面板（8）与集群（1）

宝塔、1Panel、群晖 DSM、威联通 QTS、Proxmox VE、Nginx Proxy Manager、OpenWrt / iStoreOS，
以及**长亭雷池 WAF**（更新控制台与防护站点的证书）；
Kubernetes 单列一类：写 `kubernetes.io/tls` Secret，可顺带给 Ingress 打时间戳注解触发重载
（Nginx Ingress 只监听 Ingress 变化，只改 Secret 有时候要等十几分钟才生效）。

### 云 CDN（21）

阿里云 CDN / DCDN / 直播 / 点播 / SLB 证书库、腾讯云 CDN、七牛云、火山引擎
证书中心 / CDN / 直播、AWS CloudFront、Fastly，以及国内一批中小 CDN：

| 插件 | 接口 | 鉴权方式 |
| --- | --- | --- |
| 天翼云 CDN | `open.ctcdn.cn` | `x-alogic-app/timestamp/signature`（HMAC-SHA256 两段，签名含 uri） |
| 京东云 CDN | `ssl` / `cdn.jdcloud-api.com` | `JDCLOUD2-HMAC-SHA256`（结构同 AWS SigV4） |
| 多吉云 CDN | `api.dogecloud.com` | `Authorization: TOKEN ak:HMAC-SHA1(path + \\n + body)` |
| 易盾 DCDN | `user.yiduncdn.com` | `api-key` / `api-secret` 头 |
| 括彩云 CDN | `kuocaicdn.com` | 账号密码换 Token + JSESSIONID Cookie |
| 我爱云 CDN | `console.edeg.ttzi.cn` | 账号密码换 Token，请求带 `Token` 头 |
| 白山云 | `cdn.api.baishan.com` | token 走 query |
| 又拍云 CDN / USS | `console.upyun.com` | 控制台账号登录换 Cookie |
| 腾讯云 CLB | `ssl.tencentcloudapi.com` + `clb.tencentcloudapi.com` | TC3-HMAC-SHA256；先 `UploadCertificate` 再 `ModifyCertificate` |

这几家都是「先上传/创建证书，再绑定到域名」的两步流程，差异只在签名与字段名：

- **天翼云** 的签名第二段用的密钥是**第一段结果的 base64url 字符串**，而 Node 的
  `Buffer.from(s,'base64')` 会把 `-` `_` 直接丢掉 —— Python 侧必须照做（见 `_node_b64decode`），
  否则签名永远对不上；
- **京东云** 先传 `/v1/sslCert:upload` 拿 `certId`，再用 `sslCertId + certFrom=ssl` 调
  `/v1/domain/{domain}/httpType`，不能直接把证书内容塞给 CDN 接口（会报证书已存在）；
- **多吉云** 绑定完会顺手删掉「已过期且没绑定域名」的旧证书，避免证书列表越堆越长；
- **易盾 / 括彩云 / 我爱云 / 白山云** 需要先在控制台建好站点或证书，插件按证书 ID / 域名 ID 覆盖内容。

### 验证状态

| 标记 | 含义 |
| --- | --- |
| ✅ | 端到端验证（本地 mock 服务或真实接口跑通） |
| ◐ | 接口名/签名算法已用假密钥探测确认，请求体未经真机验证 |
| ○ | 按官方文档实现，未验证 |

| 插件 | 状态 | 说明 |
| --- | --- | --- |
| 全部对象存储 | ✅ | 三种签名算法与 botocore / oss2 / 腾讯云官方 SDK 交叉校验；S3 兼容路径有本地 mock 端到端用例 |
| 国内 CDN 七家（天翼/京东/多吉/易盾/括彩/我爱/白山） | ✅ | 本地 mock 断言 URL、鉴权头、请求体；天翼云/多吉云/京东云的签名在测试里独立复算，天翼云还有一条走完整流水线的用例 |
| Kubernetes Secret | ✅ | mock 覆盖「新建 Secret」与「已存在则更新（带 resourceVersion）」两条路径，以及 Ingress 重载 PATCH |
| Nginx / Apache / HAProxy / Tomcat | ✅ | 预设路径、PEM 合并、PFX 生成均有断言 |
| 群晖 / 威联通 / PVE | ✅ | mock 面板验证账号、Token、节点名、证书内容都到了对端 |
| 宝塔 / 1Panel | ◐ | 接口按官方文档，未连真机 |
| 阿里云 DCDN / 直播 / 点播 / SLB | ◐ | action 已探测存在（返回 `InvalidAccessKeyId.NotFound` 而非 `InvalidAction`） |
| 火山引擎 CDN / 直播 | ◐ | 同上 |
| 腾讯云 CDN | ✅ | `UpdateDomainConfig` 已修正（原来写的 `UpdateCertificate` 不存在） |
| AWS CloudFront / Fastly | ○ | 流程为「上传证书 → 回写配置」，无账号未验证 |
| NPM / K8s Secret / OpenWrt / IIS | ○ | 按官方接口实现，未连真机 |
| 邮件 / 脚本 / Webhook | ✅ | 本地可验证 |

### 没有覆盖的长尾

业界还有大量单厂商插件（多吉云、又拍云、百度云、京东云、优刻得、移动云、
CacheFly、Gcore、Zenlayer、网宿、雷池 WAF、爱快、飞牛 fnOS、Plesk、ESXi……）。
这些接口各有独立的签名方案，且多数厂商文档不公开细节，**没有真实账号时无法验证**，
与其塞一堆「看起来能跑」的代码，不如不写。

需要接这类目标时用「推送到自定义接口」：把证书 POST 到自建中转服务，
再在服务里调厂商 API。这样至少出错时你能看到自己的代码在报什么。

---

## 八、二次开发：新增插件

### 新增部署插件（3 步）

1. `backend/app/services/deploy.py` 中实现函数：

```python
def deploy_to_xxx(ctx: CertContext, config: dict, log: Callable) -> None:
    log("开始部署 ...")
    # ctx.crt / ctx.key / ctx.pfx / ctx.domain / ctx.domains
    # 使用 ctx.render("...{domain}...") 替换变量
```

2. 注册到 `DEPLOY_HANDLERS`：

```python
DEPLOY_HANDLERS["DeployToXxx"] = deploy_to_xxx
```

3. 在 `backend/app/plugins.py` 的 `TASK_PLUGINS` 中登记元数据（名称、描述、inputs），前端会自动渲染表单。

两个约定，新增插件时务必遵守：

- **`config` 里已经有授权内容**。任务表单只存 `accessId`，引擎在执行前会把授权里的
  地址、账号、密钥合并进 `config`（授权为底稿、任务入参覆盖），所以函数里直接读
  `config["url"]` / `config["username"]` 即可，不要再自己去查授权表。
- **内网面板统一用 `_panel_request()` 发请求**。它会关掉 `trust_env`——宿主机上若配了
  `HTTP_PROXY`，httpx 默认会把 `192.168.x.x` 的内网请求也丢给代理，表现成「连不上」却
  看不出原因；同时它把连接类异常翻成中文，用户不会看到 `ConnectError` 这种原文。
  公网云厂商（阿里云、腾讯云、火山等）的接口不要用它，那些场景反而需要走代理。

### 新增 DNS 服务商

1. 继承 `BaseDnsProvider`，实现 `add_txt` / `remove_txt`
2. 注册到 `dns.PROVIDERS`
3. 在 `plugins.py` 的 `ACCESS_TYPES` 增加授权类型、`DNS_PROVIDERS` 增加条目

### 新增通知渠道

1. `notify.py` 实现 `send_xxx(config, title, content)`
2. 注册到 `SENDERS`
3. `plugins.py` 的 `NOTIFY_TYPES` 增加配置项

---

## 九、接口冒烟测试

改完代码想快速确认「有没有把别的地方改坏」，跑一遍全量接口测试：

```bash
# 先启动后端，再执行
python tests/smoke.py

# 自定义地址 / 账号
python tests/smoke.py --base http://127.0.0.1:8000 --user admin --password 123456
```

覆盖 73 项断言：登录鉴权、插件与模板、流水线 CRUD / 运行 / 复制 / 批量、执行历史、
授权与通知 CRUD、域名、站点监控、证书 7 种格式导出、开放 API 鉴权、设置、审计、概览，
以及三块「光看接口返回 200 查不出来」的功能验证：

- **面板部署插件的端到端验证**：群晖 / 威联通 / Proxmox；
- **通知渠道的失败识别**：钉钉、Bark、Webhook 用假密钥发送，必须判为失败；
- **部署失败的报错可读性**：连不上主机时，报错要中文、要带主机端口、不带堆栈。

设计上的两点：

- **自带清理**：测试会删除自己创建的流水线、授权、通知、域名、监控站点，
  以及自签流水线产出的证书，跑完库里不留垃圾，可反复执行。
- **按业务码断言**：本项目统一用 `HTTP 200 + body.code` 表达业务结果，
  所以断言看 `code == 200`；JKS 在无 JDK 的机器上会标记 SKIP 而不是 FAIL。

面板部署那段会在本地随机端口起一个 mock 服务冒充 DSM / QTS / PVE，然后断言
「账号密码有没有真的传过去」「证书和私钥有没有上传」「PVE 的 Token 头和节点名对不对」——
这类「参数没传到底」的问题光看接口返回 200 是查不出来的。

---

## 十、安全说明

- 所有授权（AK/SK、SSH 密码、邮箱授权码）与证书私钥均使用 **AES-GCM** 加密存储，密钥由 `CERTD_SECRET_KEY` 派生
- 接口按规范**明文回显**凭据（见 AGENTS.md 第一条），由前端的「小眼睛」决定显示与否；编辑时未修改的字段自动还原旧值
- 支持登录失败锁定、TOTP 两步验证、审计日志
- 建议生产环境：
  1. 固定 `CERTD_SECRET_KEY`，并做好 `backend/data` 目录备份与权限控制
  2. 通过 Nginx/Caddy 配置 HTTPS 反向代理
  3. 定期升级依赖

---

## 十一、常见问题

**Q：为什么运行后提示「未到续期时间」？**
A：默认剩余 20 天以上不重复申请，避免触发 CA 限流。可在证书申请任务中调整「到期前多少天续期」或开启「强制续期」。

**Q：DNS 验证失败怎么办？**
A：确认授权 AK/SK 有 DNS 解析权限、域名托管在该账号下；部分服务商需要等待 DNS 生效（默认等待 60 秒，可通过 `CERTD_DNS_WAIT` 调整）。

**Q：ZeroSSL / Google 需要 EAB 吗？**
A：需要一个 EAB 凭据。它是 CA 发给你的注册凭据，所以放在**授权管理 → 证书签发**里维护：
新建一条「EAB 凭据」（Key ID + HMAC Key），然后在证书申请任务的「EAB 凭据」里选它。
**Google 的 EAB key 创建后 7 天失效**，过期后只要在授权里更新一次，所有引用它的流水线立刻生效。
想确认还灵不灵，在「授权管理」的 EAB 卡片上点「测试」：它会拿这条凭据去 CA 注册一个临时账户，
成功即代表可用，失败会直接告诉你「Key 已过期」而不是等到流水线跑到一半才报错。
邮箱仍在任务上填（「联系邮箱」），ACME 账户私钥首次申请时由引擎自动生成并写回该任务，续期直接复用。

**Q：能商用吗？**
A：本项目用于学习与自建使用，若需商用请自行评估，并遵守所涉及开源组件的相应协议。

---

## 十二、前端实现（Art Design Pro 3.0.2）

前端是一个纯 CertHub 业务前端，**删掉了 art-design-pro 自带的模板页**
（dashboard 演示 / template / widgets / examples / article / safeguard …），
只保留业务路由 + 静态异常页，菜单里没有干扰项。

### 菜单按「流程阶段」分四块

| 分组 | 页面 | 说明 |
| --- | --- | --- |
| 工作台 | `certd/dashboard` | 一屏看清：流水线 / 有效证书 / 30 天内到期 / 成功率、近 7 天趋势、即将到期、最近执行、**支持的证书与可部署平台逐个列出** |
| 证书流程 | `certd/flow/pipeline`、`history`、`cert`、`domain` | 签发 → 部署 → 入库 → 续期的完整链路；流水线编辑页是「阶段 → 任务」卡片式可视化 |
| 接入资源 | `certd/resource/access`、`notification` | 被流程引用的凭据与通知渠道，按云厂商 / 主机 / 面板 / 证书签发分标签页 |
| 站点监控 · 系统管理 | `certd/monitor`、`certd/system/*`、`certd/profile` | 站点证书监控、用户、系统设置、审计日志、开放接口、个人中心 |

流水线列表与详情页都会用颜色区分环节：**证书申请=蓝、证书部署=绿、发送通知=橙**
（阶段卡片左边框与结果描边、列表里的分类标签都由后端 `kinds` 字段驱动）。

### 全部复用 Art Design Pro 的现成资源

| 场景 | 使用的组件 |
| --- | --- |
| 列表页 | `useTable` + `ArtTable` + `ArtTableHeader` + `ArtSearchBar` |
| 表单 | `ArtForm`（栅格 / 响应式 / 标签排版）里嵌 `PluginField` |
| 统计与图表 | `ArtStatsCard` / `ArtLineChart` / `ArtRingChart` |
| 图标与操作 | `ArtSvgIcon`（Iconify）、`ArtButtonTable` |
| 布局与主题 | Layout + `art-card` / `art-table-card` / `art-full-height` 与主题变量 |

唯一自己写的是三个业务组件（`src/views/certd/components/`）：

- `plugin-field.vue`：把后端一条字段元数据渲染成对应控件（含 `access` / `notification` /
  `tags` / `password`（小眼睛）/ 远程资源下拉 / 「从 DNS 授权带出域名」）；
- `plugin-form.vue`：在 `ArtForm` 之上把字段清单铺开，**新增插件不用改前端**；
- `log-panel.vue`：SSE 执行日志（`EventSource` 带不了 Authorization 头，所以用
  `fetch` + `ReadableStream` 自己解析），日志只用文本节点渲染，禁 `v-html`；
- `brand-avatar.vue`：本地 logo 文件 → Iconify → 品牌色字母牌三级兜底。

### 响应式

- 栅格全部走 `el-row/el-col` 的 `xs/sm/md/lg/xl` 五档：手机单列、平板两列、桌面三到四列；
- 卡片墙用 `grid-template-columns: repeat(auto-fill, minmax(..., 1fr))`，窗口拉窄自动换行；
- 表单窄屏（< 768px）自动改成标签在上；
- 日志面板高度用 `clamp()`，不会在矮窗口里把按钮挤出屏幕。

实测 1600 / 1280 / 1024 / 768 / 414 五档宽度下 `documentElement.scrollWidth` 均等于视口宽度，
没有横向滚动条；14 个页面控制台零报错（用 CDP 无头浏览器核对）。

### 构建与验证

```bash
cd frontend
node node_modules/vite/bin/vite.js build      # 产物 dist/，由后端同源托管
```

> `.env.production` 的 `VITE_API_URL` 必须是相对路径 `/`：构建产物由 FastAPI 托管，
> 写死域名会让换端口 / 反向代理部署直接失效。开发环境 `.env.development` 的
> `VITE_API_PROXY_URL` 指向 `http://127.0.0.1:8000`。

---

## 十三、开源协议

本项目（后端 `backend/` 与前端 `frontend/`）整体采用 **GNU General Public License v3.0（GPL-3.0-only）**，
许可证全文见仓库根目录 [`LICENSE`](./LICENSE)。

```
CertHub  Copyright (C) 2026  HtmACG

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
```

分发、修改或以网络服务形式提供本项目时，请保留版权声明与许可证文本，并向接收方提供对应源码。

### 第三方组件

| 组件 | 许可证 | 位置 |
| --- | --- | --- |
| Art Design Pro 3.0.2（前端模板） | MIT | [`frontend/LICENSE`](./frontend/LICENSE) |
| 其余 Python / npm 依赖 | 各自原许可证 | `backend/requirements.txt`、`frontend/package.json` |

> 说明：上游 [Certd](https://github.com/certd/certd) 采用 AGPL-3.0。本项目为独立实现，
> 若你在此之上引入上游代码，则该部分仍需遵循 AGPL-3.0（AGPL-3.0 与 GPL-3.0 单向兼容）。
