# CertHub 开发规范

本文件是项目的硬性约定，改代码前先读一遍。**与代码冲突时以本文件为准，并回头把代码改对。**

## 一、凭据必须可明文查看（铁律）

1. **接口层禁止打码。** 授权（Access）、通知渠道、证书私钥等所有凭据字段，
   一律**明文**返回给前端。不要返回 `******`，也不要按字段名（含 secret/key/password）
   猜着打码。
2. **显示与否由前端「小眼睛」决定。** 密码类输入框统一用 Element Plus 的
   `ElInput type="password" show-password`，默认星号、点击小眼睛立刻显示明文。
   其它字段（AccessKeyId、账号、Endpoint、Region…）本来就明文展示。
3. **编辑时留空不覆盖。** 前端提交里值为空串（或历史遗留的 `******`）表示「这一项没改」，
   后端 `security.merge_secret()` 负责还原旧值。**绝不允许把用户的密钥写成空串。**
   这条是上一版的教训：打码让用户以为「没保存」，清空密码框再保存直接把密钥写没了。
4. **保存前 trim。** 粘贴凭据最常带首尾空格/换行，会导致签名失败且极难排查。
   后端 `_clean_config()` 与前端都在提交前 trim。
5. **必填项要校验。** 必填字段为空时返回「请填写「XXX」」，不要静默存一条空授权。

## 二、元数据驱动

- 新增签发方式 / 部署目标 / DNS 服务商 / 通知渠道，**只改后端** `app/plugins.py`
  的注册表（`TASK_PLUGINS` / `ACCESS_TYPES` / `NOTIFY_TYPES`），前端表单、授权下拉、
  任务选择器全部自动出现。不要在前端硬编码插件清单。
- 字段的敏感属性由 `component == "password"` 声明；不要靠字段名猜。
- **授权字段必须声明「精确类型」（accessTypes）**：`accessCategory` 只是能力分类
  （cloud / host / panel），宝塔 / 1Panel / 群晖 / 威联通 / PVE / NPM / 雷池 全属于 panel，
  只按分类过滤会让「部署到群晖」的下拉里出现宝塔授权。所以：
  - 部署插件的 `accessId`、申请插件的 `dnsAccessId` / `eabAccessId` 都要带
    `accessTypes: ["synology"]` 这样的精确类型（注册表见 `plugins.py` 的
    `_DEPLOY_ACCESS_TYPES` / `_CERT_ACCESS_TYPES`）；
  - 接口 `GET /api/access/options?types=a,b` 按类型过滤（`access.py` 的
    `_filter_types()`），前端 `plugin-field.vue` 只列允许的类型；
  - 引擎 `_check_access_types()` 在执行前再校验一次，选错给中文结论
    （「这个任务需要「群晖 DSM」类型的授权，当前选的是「宝塔面板」」）；
  - 老数据里带着不匹配的授权时，字段下方要显示红色提示，不要静默显示一个数字 ID。
- **授权字段必须覆盖 handler 真正读的配置**：部署 handler 里 `config.get("xxx")` 用到的键，`ACCESS_TYPES` 的 inputs
  里都要有对应字段，否则用户根本填不了、只能吃写死的默认值。
  群晖就是典型漏项：handler 早就读 `asDefault`，但表单里没有这个开关，`certDesc` / `otpSecret` 也缺，
  用户反馈「群晖需要的授权配置信息不完善」。检查方法：把 handler 里所有 `config.get` 的键抄出来，
  和 inputs 的 key 对齐；同时给每个字段写清楚去哪找（例如两步验证密钥在 DSM → 个人设置 → 双重验证）。
- **面板类授权要能长期跑**：两步验证别只留「验证码」字段（30 秒就过期），要留 Base32 密钥，
  部署时用 `pyotp` 现算（见 `deploy._totp_code()`）；
  「测试」按钮必须真登录一次（`deploy.synology_probe()`），把 2FA / 权限 / 端口问题当场暴露出来。
- **字段可以声明动作按钮（`action`）**：元数据里写 `action={"type": ..., "label": ...}`，
  前端 `plugin-field.vue` 会在该字段下方渲染按钮，点开做一件事并把结果写回这个字段。
  目前唯一实现的是群晖「获取设备ID」（`synology-device-id`），流程和 certd 对齐：
  填好地址 / 账号 / 密码 → 输一次双重认证 APP 上的 6 位码 → 调
  `POST /api/access/synology/device-id` 换 DSM 的受信设备令牌（certd 的 `deviceId` / did）→
  之后登录只带 `device_id`，不再需要验证码。
  - 前置条件（DSM 侧）：控制面板 → 安全性 → 勾选「允许网页浏览器的用户通过信任设备来跳过双重验证」；
    信任设备列表里会多一条记录，删了设备 ID 立刻失效。
  - 设备 ID 约 30 天过期：部署时若带设备 ID 登录失败、且授权里配了「验证密钥」，
    会自动回退成验证码登录并把新的 did 写回授权（`deploy._synology_login`），别删这段兜底。
  - 加新的动作按钮：后端声明 `action` + 前端在 `plugin-field.vue` 加一个分支；
    不要为某个插件写死表单。
- 插件元数据里可以带展示信息：`logo`（Iconify 图标名）、`favicon`（官网 ico 地址）、
  `color`（品牌色）、`domainFrom`（域名嗅探来源字段）。
- **厂商 logo 必须本地化，不许前端直连 CDN。** 授权类型的图标由
  `backend/tools/fetch_access_logos.py` 从 `_ACCESS_VISUAL` / `_ACCESS_FAVICON`
  下到 `frontend/public/logos/access/<type>.svg|png|ico`，元数据里给前端的是
  相对路径 `logoFile`；前端只用 `<img>` 加载，加载不到才退回字母牌。
  内网、离线环境下 CDN 是取不到的，卡片会变成空白块。
  - 优先 SVG：Iconify 上的图标直接下 `<prefix>/<name>.svg`。**单色图标集
    （`simple-icons:` / `mdi:`）必须带 `?color=%23<品牌色>`**，否则 SVG 里留着
    `currentColor`，暗色模式下就是一片死黑。
  - 常见坑：`logos:cloudflare` / `logos:aws` / `logos:fastly` 是超宽「字标」
    （6.74em 等），当方块图标用会被裁掉；换成 `simple-icons:` 的方形 mark。
  - Iconify 上没有的品牌（宝塔 / 多吉云 / 白山云 / 又拍云 / 京东云 / 括彩云 /
    易盾 / 我爱云）只有 favicon：用 `icon.horse` / `favicon.im` 拿 PNG，
    宝塔两家都只给 ICO。下载后要校验魔数，别把占位图当 logo 存下来。
  - 改了图标映射就重跑脚本，校验失败会非零退出，不会留半成品。
  - **重跑脚本前先看一眼 `_ACCESS_LOGO_EXT`**：宝塔 / 群晖 / 京东云 / 多吉云 / 易盾 /
    又拍云 / 白山云 / 括彩云 / 我爱云 / 天翼云这 10 家用的是仓库里的官网位图（.png），
    脚本不会重新下载。脚本里「清掉非 SVG」的逻辑必须跳过这些文件，
    否则一跑就把它们删光，表现是「厂商图标全都不显示了」（已踩过，已修）。

## 三、概览页「支持的证书」展示规则

- **所有支持的来源和平台都要逐个列出来**，不能只给数量。目前分三块：
  1. 证书申请（可签发）：ACME CA / 云厂商 / 本地自签；
  2. 证书部署（可安装到）：按分类（主机 / 面板 / 集群 / 云 CDN / 对象存储 / 其它）
     列出**每一个插件名**；
  3. 其它来源：上传自有证书（只入库）。
- **每家都要有 logo**，取值顺序：
  1. Iconify 图标名（`logo`）—— 名称必须先用
     `https://api.iconify.design/search?query=xxx` 搜出来、再用
     `https://api.iconify.design/<prefix>/<name>.svg` 校验 200 才能写进注册表，
     禁止凭记忆写。彩色品牌图标优先 `logos:` / `thesvg-color:` 集合。
  2. Iconify 没有该品牌时用官网 favicon（`favicon`），前端 `<img>` 加载并处理 `@error`。
     **favicon 必须验证内容是真的**：状态码 200 不代表拿到图（可能是 0 字节或占位 PNG）。
     判断方法：对一张已知不存在的域名（`example-unknown-domain-xyz.com`）请求同一服务，
     比对返回内容的 md5，相同即为占位图。实测 `favicon.im` 对京东云/易盾/括彩云/我爱云
     返回占位图，`icon.horse` 才是真实 logo。
  3. 都没有时退化成「品牌色底 + 首字母」字母牌，不能留空白块。
- 数字（可签发 N 种 / 可部署到 M 个平台）必须来自注册表实时计算，不许写死。

## 四、错误文案与日志

- 业务性异常（PipelineError / DeployError / AcmeError / NotifyError / VolcError /
  DnsError / AliyunError / AliyunCasError / TencentSslError）不进执行日志的堆栈，
  只打一行中文；新增异常类时记得登记到 `engine._EXPECTED_NAMES`。
- 云厂商错误压成 `[Code] Message` 一行，不要甩原始 JSON + RequestId。

## 四·补〇、凭据只放授权管理，资源必须自动拉取

- **EAB 凭据放「授权管理 → 证书签发」，任务里只选不填**：
  任务表单里只有「EAB 凭据」（`eabAccessId`，`component="access"` +
  `accessCategory="cert"`，`showWhen` 为 Google / 自定义 ACME），
  **不要再把 Key ID / HMAC Key 放回任务表单**。理由是它是凭据：
  Google 的 EAB key **创建后 7 天失效**，放授权里只要更新一条授权，
  放任务里就得逐条流水线改，改漏一条就永远签不出来。
  - 授权类型 `eab` 的字段是 `provider`（标识用）+ `kid` + `hmacKey`（password）。
  - 引擎 `_eab_credentials()` 负责解析：优先 `eabAccessId`，
    兼容老流水线里直接写的 `eabKid` / `eabHmacKey`（别删这段兼容，老数据还在）。
- **FreeSSL.cn（LiteSSL）走 ACME v2 + EAB，已经内置成一个 CA 选项**（`litessl`）：
  - 老地址 `https://acme.freessl.cn/directory` **已下线**（`acme.freessl.cn` 域名不再解析），
    现行目录是 `https://acme.litessl.com/acme/v2/directory`，别照着旧博客填旧地址。
  - 该目录的 `meta.externalAccountRequired` 是 `true`：**必须带 EAB**。
    EAB 在 FreeSSL「证书自动化 → ACME 账户管理 → 新增凭证」里建，拿到 Key ID + HMAC Key 后
    填到「授权管理 → 证书签发」（`eab` 类型，所属 CA 选 FreeSSL / LiteSSL），任务里选它即可。
  - **EAB 值必须先清洗再用**：`acme.normalize_eab_pair()` 会去掉标签前缀（「HMAC Key：」）、
    换行 / 空格 / 零宽字符，整段粘贴时按标签各取各的值；实在抠不出 base64 就给一句中文结论
    （「EAB HMAC Key 里有中文 / 全角字符…只复制标签后面的值」）。
    引擎在 `_eab_credentials()` 里调它（清理过会写一行日志），`_eab()` 里还有最后一道兜底，
    **别让 `base64.b64decode` 的 `UnicodeEncodeError` 直接冒到日志里**：
    真实踩过，用户看到的是一串 `string argument should contain only ASCII characters` + 堆栈。
  - **EAB 可能是一次性的，注册成功一次就作废**（FreeSSL / LiteSSL 实测：再注册回
    `externalAccountRequired: External account binding has already been used`）。所以：
    - `acme.register_eab_account()` 是「注册或复用」：传了 `account_key_pem` 就只确认账户还在，
      **不再提交 EAB**；
    - 首次注册成功后，账户私钥 + 账户 URL 要**同时**写回**任务**（`acmeAccountKey` / `accountUrl`）
      和 **EAB 授权**（`engine._store_eab_account()`）：其它流水线复用同一份 EAB 时不会再注册；
    - 「授权管理」里的「测试」按钮也走同一条路，注册出来的账户写回授权（`routers/access.py`），
      **点测试不会把用户的 EAB 烧掉**；
    - 存的账户地址在 CA 侧没了（换 CA / 账户被删）时，引擎会改用 EAB 重新注册一次。
  - 报错文案：`External account binding has already been used` → 中文「这条 EAB 已经用过了…去轮换 EAB」，
    别只甩英文。
  - CAA 身份是 `trustasia.com`：域名有严格 CAA 记录时要把 `trustasia.com` 放进去。
  - EAB 填错时 LiteSSL 回的是英文 `The bound account does not exist`，
    已经在 `acme.friendly_problem()` 里翻成「EAB 凭据对不上…重新取一份 EAB」；
    新增 CA 时同样要补一条中文映射，别把英文原样甩给用户。
  - **CA 的名字 / 目录地址 / 是否要 EAB 只有 `plugins.ACME_PROVIDERS` 一份**：
    引擎里以前手抄过 `_CA_NAMES` + 目录字典，新增 FreeSSL 时漏改，
    表现就是「选了 FreeSSL 却报『自定义 ACME 需要填写 ACME 目录地址』」。
    现在引擎统一走 `_ca_name()` / `_ca_directory()` / `_ca_needs_eab()`，
    冒烟里有一条「每个内置 CA 的目录地址，引擎都能解析到」的回归断言，别再另抄一份。
  - 老版 FreeSSL 的脚本（`freessl.cn/api/get.acme.sh?token=…`）依赖他们改造过的 acme 客户端，
    **不要照它做**：我们按标准 ACME v2 走，dns-01 / http-01 都是通用实现。
- **ACME 账户（邮箱 + 账号私钥）仍然不建授权**：邮箱填在任务上，
  账号私钥首次申请时由引擎自动生成，并用 `_persist_task_input()` 写回该任务的
  `acmeAccountKey`，续期直接复用；**授权管理里没有 acmeAccount 类型**。
- **EAB 相关报错必须翻成中文结论**：CA 返回的
  `Unknown external account binding (EAB) key ... expiring` 这类英文原文只进
  `AcmeError.detail`，执行日志里只留「EAB 凭据无效或已过期 + 该点哪里」
  （见 `services/acme.py` 的 `friendly_problem()`）。
- **有 Key / Token 的授权必须能自动拉取对端资源**：DNS 域名、面板站点（宝塔 / 1Panel）、
  WAF 证书（雷池）、CDN 加速域名（阿里云 / 腾讯云 / 天翼云 / 京东云 / 多吉云 / 括彩云 / 又拍云）、
  K8s 命名空间。实现放在 services/resources.py，每个解析器返回 (items, error)，
  失败只给一句中文原因，不抛异常。
- 表单里的资源字段用元数据 remote="<kind>" + remoteFrom="<授权字段 key>" 声明，
  前端 PluginForm 自动渲染成可搜索下拉并调用
  POST /api/pipeline/plugin/{type}/options/{field}；**不要在前端硬编码资源清单**。
- 新增厂商时：先在 resources.py 加解析器并在 _RESOLVERS 登记，再给字段加 remote。
- **资源一律全量展示，不分页不截断**：这些是管理员自己账号下的东西，藏着掖着只会让人以为没同步全。

## 四·补、网络设置（HTTP 代理 + 反向代理域名）

国内服务器访问 Google / ZeroSSL 等海外接口要靠代理，规则：

- **代理语义与环境变量一致**：`httpProxy` / `httpsProxy` / `noProxy`（`sys_setting.network`）。
  填了代理就默认全部出网请求走代理，noProxy 命中的直连；不要自己发明「只代理某些域名」的白名单。
- 所有出网请求必须走 `services/net.py`：一次性调用用 `net.get/post/request`，
  复用 `httpx.Client`（ACME / DNS）用 `net.client()` 或 `mounts=net.proxy_mounts()`。
  **不要再直接 `httpx.get(...)`**，否则代理会漏。内网 / 回环地址传 `trust_env=False` 绕开代理。
- **反向代理域名**只改传输地址，JWS 里的 `url` 必须是 ACME 原始地址；
  任务级 `reverseProxy` 优先于系统配置，再往下才是内置默认。
- 新增海外接口时，把端点域名补进 `services/net.py` 的 `DEFAULT_REVERSE_PROXIES`（有公共反代才行）。
- 凭据（代理账号密码）同样**明文存、明文回显**，前端用小眼睛控制显示。

## 四·补四、亚洲诚信（TrustAsia CertCloud）证书申请

- 走的是 **CertCloud OpenAPI v3**（https://docs.trustasia.com/certcloud/openapi/v3/），
  不是 ACME：CertCloud 的 ACME EAB 是「先下单再换 EAB」的二次流程，
  直接用 OpenAPI 一条龙更省事。客户端在 `services/trustasia.py`。
- **鉴权只有两个头**：`X-CC-Key-ID` / `X-CC-Auth-Key`，明文传，
  **不需要自己算 HMAC**（官方明确说 HTTPS 已加密，服务端只做 SHA256 比对）。
  正式 `https://api.certcloud.cn/openapi/v3`，测试 `https://api-uat.certcloud.cn/openapi/v3`。
  授权里留了 `apiBase` 可选字段：只有走自建代理 / 联调本地 mock 时才填（冒烟就是靠它命中本地 mock）。
- **申请顺序不能颠倒**：下单 → 拿 `dcv_val[]` → 写验证记录 → 
  `PUT /orders/{id}/dcv-completed` 通知 CA → 轮询 `GET /orders/{id}` 到 `issued` → 
  `GET /certs/{id}` 取 `pem` + `ica_pem`。
  写完记录要**先等一下再通知 CA**，立刻通知它去查会拿到空记录（和 ACME 的传播问题是同一个坑）。
- **私钥只在本机**：CSR 本地生成（`certutil.build_csr`），提交给 CA 的只有 CSR，
  拿回来的证书和本地私钥拼成链入库。别改成让 CA 生成私钥。
- 验证方式四种，记录类型由 CA 决定：`dns` → TXT、`cname` → CNAME、
  `file` → 写网站根目录（和 ACME http-01 共用 `engine._write_http_file()`）、`email` → 只能人工点邮件。
  所以引擎里用的是 `_make_dcv_writer()`（TXT + CNAME 都支持），
  **不要拿只支持 TXT 的 `_make_dns_writer()` 去接 CNAME**。
- **产品能力要先本地拦一道**（`trustasia.PRODUCTS`）：单域名产品不能填泛域名、不能填多个域名、
  OV / EV 必须把组织与联系人填全，验证方式要与产品支持列表匹配。
  这些在本地直接给一句中文（「还缺：组织电话、联系人邮箱」），比等 CA 回 `invalid_organization_info` 好懂。
- **错误统一一行中文**：`_error_text()` 拼「HTTP 码 + 错误码 + 说明 + X-CC-Request-ID」，
  再按 `ERROR_HINTS` 补一句该干什么（`unauthenticated_request` → Key ID / API Key 不对…）；
  `TrustAsiaError` 已登记到 `engine._EXPECTED_NAMES`，执行日志里不会出现堆栈。
  缺密钥这类**配置错误不要被「连接失败」包起来**：鉴权头在 try 之前就取好。
- 订单状态到人话的映射在 `trustasia.STATUS_TEXT`（issued / domain_verifing / auditing / failed …），
  `auditing` 是 OV / EV 的人工审核，别当失败；`FAILED_STATUS` 里的才算失败。
- logo：官方只有宽幅字标，这里存的是从官方 SVG 里裁出来的方形 mark
  `frontend/public/logos/access/trustasia.svg`，并在 `fetch_access_logos.py` 的 `KEEP_LOCAL` 里登记，
  免得脚本按 Iconify 找不到图标时把它清掉。
- 冒烟 `section_trustasia()` 用本地 mock（`_trustasia_mock()`）核对：鉴权头、
  订单体（CSR / CN / SAN / dcv_method / validity_months / alternative_order_id）、
  TXT 与 CNAME 两种验证记录、dcv-completed、CA 拒签文案，以及**一条完整流水线**
  （用文件验证，这样不依赖真实 DNS 账号）。

## 四·补五、证书未到期 / 已存在 / 刚申请过 → 只跳过这一步，不中断流水线

- 申请类任务（`CertApply` / 云厂商 / CertificateTrustAsia / 自签）在真正下单前统一走
  `PipelineRunner._precheck_apply()`，三条判据命中任意一条就跳过：
  1. 本流水线已有证书，剩余天数 > 「提前续期天数」（`renewDays`，默认 20）；
  2. 证书库里已有**同域名集合**且未过期的证书（`skipIfCertificateExists`，默认开）；
  3. 同一套域名在 `skipRecentMinutes` 分钟内刚签出过（默认 10，防止重复运行 / 多环境同时触发）。
  证书本身有效期比续期阈值还短时（90 天 LE 配 100 天阈值），阈值自动减半（最少 2 天），
  否则会变成「每次运行都续期」。`forceUpdate`（强制续期）一律跳过这些判断。
- **跳过的语义是「这一步不干，后面继续干」**：抛 `TaskSkipped`，任务循环里记
  `status=skipped` 后 `continue`；以前抛 `SkipPipeline` 会把整条流水线中止，
  部署和通知也跟着不跑了 —— 用户要的是「未到期就跳过申请，但证书该下发还要下发」。
  流水线整体状态仍是 `success`（跳过不是失败）。
- **跳过时必须把证书交给后续步骤**：`_cert_ctx_from_row()` 把证书库里那张证书塞进
  `_cert_ctx`，否则后面的部署任务会报「没有可部署的证书」。日志写一句
  「后续步骤将使用证书库里这张证书（到期 …）」。
- 前端：任务状态新增 `skipped`（「已跳过」）/ `disabled`（「已停用」）两种，
  在 `utils/certd.ts` 的 `runStatusMeta` 里映射；跳过的卡片用蓝色虚线描边（`.is-skipped`），
  **阶段成败判断要排除 skipped / disabled**，否则「跳过申请」会把整个阶段画成失败。

## 四·补三、ACME 签发的四条硬规则（每条都踩过）

1. **反向代理只能改传输地址，不能改协议地址。**
   `AcmeClient._origin_url()` 负责把反代域名还原成 CA 原始域名，
   `kid` 走 setter 强制还原，订单 / 授权 / 挑战 / finalize / 证书 URL 也一并还原。
   不还原的话 CA 会回 `malformed / "Invalid or unrecognized host."`，
   看起来像域名问题，其实是 kid 里带了反代域名。

2. **先让 DNS 记录生效，再通知 CA 来验证。**
   顺序反了 CA 立刻去查，查到空记录就判
   `incorrectResponse / "Did not find challenge value in TXT record"`。
   传播判断优先问**权威 NS**（见 `dns.py` 的 `_authoritative_servers()`），
   系统 resolver 有 TTL 缓存（阿里云免费版最短 600 秒），会假报「没生效」。

3. **泛域名与其主域名共用一条 `_acme-challenge.<主域名>` 记录。**
   一条一条「加→验→删」会互相覆盖，必须
   「所有域名先加记录 → 等全部生效 → 再逐个通知 CA → 逐个轮询」。
   引擎 `_apply_cert()` 里的 pending 列表就是干这个的，不要改回串行内联。

4. **同名同值记录已存在 = 成功。**
   阿里云回 `DomainRecordDuplicate`、DNSPod 回 `ResourceUnavailable.RecordExist`，
   重复申请或上轮没清干净都会撞上；`BaseDnsProvider._tolerate_duplicate()`
   把这些当成功，否则整条流水线会以「记录已存在」失败，看着像授权坏了。


## 五、测试规范

- 后端改动跑 `python tests/smoke.py --base http://127.0.0.1:8000`（服务需已启动）。
- 新增部署插件必须有 handler + 元数据，冒烟会断言两者一一对应。
- 没有真实云账号的插件，用 `_cdn_mock_server()` 类的本地 mock 断言 URL / 鉴权头 /
  请求体，签名类还要在测试里**独立复算**签名。
- 前端改动后用 CDP 无头浏览器核对：DOM 数量、间距、暗色对比度、控制台无报错。

## 五·补、UI 改造前先确认「哪一页」

用户给的参考截图未必能读（当前模型不支持读图时），**不要靠猜**：
先问清楚是「列表页」还是「点进去的详情/编辑页」，再动手改。
本项目的分工是：**列表页用表格**（ArtTable，信息密度高），
**流水线的可视化展示在编辑页**（`pipeline/detail.vue` 的阶段/任务卡片）。

## 五·补二、分页与列表接口

- 前端 `useTable` 发 `current`/`size`，后端列表接口必须用 `page: int = Depends(page_no)`
  （`deps.page_no` 同时接受 `page` 与 `current`）。**新加列表接口别再写 `Query(1)`**，
  否则分页器点了不生效（历史踩坑：9 个接口全中）。
- 改样式块时用整段替换要小心：先确认区间里没有别的选择器，否则会连带删掉
  兄弟组件的样式（本项目的「选择任务类型」弹窗就因此铺成了一列）。

## 六、前端约定

- Element Plus 组件 + `<script setup lang="ts">`，Vue API 走自动导入。
- 样式写在 `<style scoped>` 里，颜色用主题变量（`--default-box-color`、
  `--art-card-border`、`--art-gray-500` …），**不要写死背景色**，否则暗色模式会白底白字。
- 纯 CSS 块里注释用 `/* */`，不要用 `//`（PostCSS 会报错）。

## 六·补、生产构建看不到 console（排障必读）

- 生产构建开了 `terserOptions.compress.drop_console`，**所有 `console.*` 都被删掉**，
  连 Vue 的 `[VueError]` 也一起没了 —— 组件 `setup()` 抛异常时页面表现是「整块空白 /
  只有一个 `<!---->` 注释」，控制台一片安静。
- 排查办法：临时往 `window` 上挂调试数组（`(window as any).__dbg`）分段打点，或
  `window.addEventListener('error')` 兜底；查完记得删掉。
- 踩过的坑：`new RegExp()` 里手写命名分组 `(?<x>...)` 少写一个右括号，构建期不报错，
  运行期整块组件消失。拼正则时刻意数括号，改完拿构建产物
  `node -e "eval('...')"` 验一下能不能编译。

## 六·补二、执行日志的展示规范
- 编辑页（`pipeline/detail.vue`）跑流水线时，日志**内联在阶段列表下方**，不用抽屉；
  抽屉只留给列表页的「运行」。
- 日志行要高亮：时间戳 / 阶段分隔 / `[任务名]` / URL / 域名 / PEM / JSON 键，
  成败关键字上色。**用文本节点渲染，禁止 `v-html`**（日志里含用户填的域名、密钥路径）。
- 阶段卡片要能看出结果：失败=整卡红描边（四条边，不是只描左边）、全部成功=绿、在跑=黄。
  数据来自 SSE 的 `event: tasks`（任务项带 `stage` 字段），别自己去猜阶段。

## 六·补三、流水线画布（Vue Flow）

详情页（`pipeline/detail.vue`）默认是**画布视图**，列表视图保留（窄屏 / 逐项核对时切换）。
画布用 [`@vue-flow/core`](https://github.com/bcakmakoglu/vue-flow)（MIT，React Flow 的 Vue 版）
+ `@vue-flow/background|controls|minimap`，组件在 `pipeline/components/pipeline-canvas.vue`。

- **映射**：阶段 = group 节点（浅色虚线容器，任务用 `parentNode` 挂进去）；任务 = 卡片节点。
- **阶段外框可拖，任务卡片不可拖。** 阶段节点 `draggable: true`，任务卡片永远 `draggable: false`
  且 `parentNode` 挂在阶段上 —— 拖动阶段时卡片跟着整体走，单独拖卡片不改变任何坐标。
  卡片在阶段内的位置由「阶段内顺序」决定（`autoTaskPos`），所以结构永远不会被摆乱。
  阶段坐标存 `content.layout.stages`，任务坐标不落库（`layout.tasks` 只用于拖动过程中的临时记录）。
- **连线只表达「先后」，不搬任务。** 从 A 拖到 B 只做两件事：把 B 标成已连线、把它接进执行链；
  **不 splice、不换阶段、不删空阶段**。早先的实现会把目标任务搬到源任务的阶段里，
  跨阶段一拖就把用户的结构「合并」掉了 —— 这是明确要避免的行为。
  顺序永远由「阶段顺序 + 阶段内顺序」决定，所以连线不可能成环，后端结构也不用改。
  反向连线（指向排在自己前面的任务）直接拒绝并提示。
- **没连线 = 不执行。** `task.linked === false` 的任务：画布不给它画线、卡片右上角标「未连线」、
  引擎跳过它并记 `unlinked` 状态（日志「还没有连线，跳过这一步」）。
  新建任务默认 `linked: false`，从别的卡片拖一条蓝线过来才激活。
  链上的边是「按顺序取相邻两个已连线任务」，所以中间夹着未连线任务时，前后两个会直接连起来。
- **阶段开关 = 整段跳过。** 阶段卡片头部最右侧常驻一个开关（`stage.enabled`，缺省 / true 都算启用）。
  关掉后 `engine.run()` 拍平执行序列时整段 `continue`（日志「已停用，整段跳过」），
  画布上阶段灰化、序号变灰、运行按钮禁用，里面的任务卡片一起降饱和（`is-stage-off`）；
  列表视图有同一个开关和「整段已停用」标记。和任务级 `task.enabled` 的差别只是粒度。
  三个必须守住的点：开关**不要塞进 hover 浮层**（它是状态指示）、必须带 `nodrag`
  （否则按住开关会拖动整个阶段框）、`.stage-node-actions` 的 `right` 要给它让位（42px）。
- **序号徽标是「硬币」样式**：实心圆 + 3px `--g-surface` 白边 + 双层投影（中性灰 + 掺阶段色的光晕）。
  白边取 `--g-surface` 而不是写死 `#fff`，暗色下才会自动变深；暗色 `--g-blue` 是浅蓝，
  序号文字要跟着翻成深色。尺寸写死 26px 且 `box-sizing: border-box`（白边算在里面），
  否则徽标会撑大、把阶段名挤走。
- **点连线可以删除。** 顺序线删掉 → 目标任务变「未连线」、不再执行；「失败后」线删掉 → 清 `onErrorTaskId`。
  两种都先弹确认框说明后果（`ElMessageBox`，按钮文案分别是「断开」「删除」）。
  删除只改数据、不动任务归属 —— 任务仍留在原来的阶段里。
- **每个阶段最多 5 个任务**（`MAX_TASKS_PER_STAGE`，在 `canvas-types.ts`）。
  `openPicker` 和 `choosePlugin` 各拦一次（弹窗开着的时候也可能被别处加满）。
  满了以后画布上的「添加任务」条变成灰色「本阶段已满 5 个任务」，
  列表视图的 `.task-add` 变 `.is-limit` + `disabled`。
- **坐标不再落库**：`content.layout` 这套机制保留在组件里（`CanvasLayout` / `layout` prop），
  但详情页不传也不存 —— 位置既然固定，存坐标只会让不同流水线的视觉不一致。
- **画布高度跟视口走**：`clamp(440px, calc(100vh - 286px - bottomOffset), 1200px)`，
  底部日志终端展开时靠 `bottomOffset` 让位；宽度 100% 跟随容器。
  尺寸一变（窗口缩放、终端展开）由 `ResizeObserver` 触发 `fitAll` 重新对准。
- **四个必须遵守的坑**（都踩过）：
  1. 卡片**不能**写 `overflow: hidden`。锚点挂在左右边缘、中心点落在边框上，一裁切
     `pointerdown` 就打到卡片本体，Vue Flow 收不到 handle 事件，表现是「拖不出连线」。
  2. 锚点放大只能用独立的 `scale` 属性，**不要覆盖 `transform`** —— Vue Flow 用
     `translate(-50%, -50%)` 定位，覆盖后锚点被推出卡片，同样拖不出线。
  3. 视图对准自己按节点几何算（`fitAll` + `setViewport`），**不要用 `fitView`**：
     它读 Vue Flow 缓存的容器尺寸，底部终端展开/收起导致高度刚变时会用旧值，
     内容就偏在画布下半部分。容器尺寸变化用 `ResizeObserver` 兜住。
  4. **节点不可拖 / 不可选时，Vue Flow 会给节点容器写内联 `pointer-events: none`。**
     `NodeWrapper` 的判定是
     `hasPointerEvents = isSelectable || isDraggable || 有 nodeClick 等钩子`，
     我们把 `draggable` / `selectable` 都设成 false（需求「位置固定」），它就直接判定
     这个节点不需要指针事件 —— 节点里所有按钮、卡片双击、连线锚点**全部点不到**。
     表现极具迷惑性：元素在 DOM 里、`opacity: 1`、`cursor: pointer` 都在，
     就是点不动（「画布模式下加不了任务」的真凶，同一个根因也让拖线一起坏掉）。
     解法：CSS 里对 `.vue-flow__node` 显式写 `pointer-events: none`，
     再把 `.stage-node-head` / `.stage-node-actions` / `.stage-node-add` / `.stage-node-limit`
     / `.task-node` / `.flow-handle:not(.is-ghost)` 逐个写回 `auto`。
     **不要图省事把整个 `.vue-flow__node` 设成 auto** —— 那样节点矩形内全部吃掉指针，
     在阶段空白处就拖不动画布了。`pointer-events` 可继承，父级 none 时子级 auto 仍能命中。
     现在阶段节点是 `draggable: true`，Vue Flow 会给它内联写 `pointer-events: auto`（内联优先于 CSS），
     所以在阶段空白处按下鼠标是**拖阶段**、不是平移画布；想平移画布用背景空白处或空格拖动。
- 节点高度是固定值（`NODE_H=160`），改卡片样式要同步改 `canvas-types.ts` 的 `CANVAS_METRICS`，
  否则阶段容器高度和连线端点会错位。阶段高度里要给底部「添加任务」条留位置
  （`stageHeight()` 里的 `addZone`），漏了按钮会压到最后一张卡片上。
- **「添加阶段」按钮在顶部操作条、紧挨「保存」**（`detail-head-right`），画布 / 列表两个视图共用；
  不要再在内容区底部加一个，两个入口会让人以为功能不同。
- **「添加任务」是阶段底部常驻的虚线按钮**（`添加任务 N/5`），不要塞进头部 hover 浮层：
  浮层平时 `opacity: 0`，24px 图标藏在角落，实测用户根本找不到、也点不到。
  空阶段文案自动变「添加第一个任务」。
- **一个入口、两个出口**：左侧唯一的 `in` 是整张卡片的输入（顺序线和失败后线都从这里进）；
  右侧上点 `out` = 「成功后」、右侧下点 `err` = 「失败后」。
  两个出口都带常驻文字标签（`.flow-port-label.is-out` / `.is-err`），放在
  `CANVAS_METRICS.stagePadRight` 留出的右侧留白里，不压卡片内容、也不压端口出来的线；
  进口只有一个，不写标签。红点常驻半透明（`opacity: .45`），配过跳转后 `.is-on` 常亮。
- **「失败后」连线和顺序连线是同一套线型**：贝塞尔曲线 + 中点圆点、蓝色实线 2px，
  语义只由出口（位置 + 标签）表达；**不要**再改回红色虚线 + 中点「失败后」胶囊。
  两条线都进同一个 `in` 口，末端重合是预期行为（错误线 `zIndex: 1`，重合处优先命中它）。
- **Vue Flow 只在离锚点 `connectionRadius`（我们设 28px）以内才发 `connect` 事件。**
  卡片有一两百像素宽，用户按提示「把失败后端口拖到卡片上」时落点在卡片中间，离左侧 `in` 锚点很远，
  连线直接作废 —— 表现就是「拖不动」。解法是 `@connect-start` 记住源锚点，
  `@connect-end` 时若这一趟没触发过 `connect`（用 `dragConnected` 标记），
  就用 `document.elementsFromPoint` 找落点下的 `.vue-flow__node-task[data-id]` 自己补一条。
  **不要靠调大 `connectionRadius` 解决**：半径一大会吸附到相邻卡片的错误锚点上。
- **edge 的描边样式是 `style` prop，必须声明并转发给 `BaseEdge`。**
  `EdgeWrapper` 把 `style: edgeStyle.value` 当 prop 传进自定义 edge 组件；不声明就会被
  当成普通属性丢掉 —— 表现是「明明设了 `stroke` + `strokeDasharray`，画出来还是默认色」。
  写法：`defineProps<{ style?: Record<string, any> }>()` + `<BaseEdge ... :style="style" />`。
- **连线层压在阶段容器上方（`z-index: 2`），任务卡片再压在连线上面（`z-index: 3`）。**
  阶段容器有一层不透明底色，连线层留在下面会把线整段盖住，跨阶段失败线就只剩阶段之间两小段。
  `.vue-flow__edges` 上是 Vue Flow 写死的内联 `z-index: 0`，必须用 `!important` 压过；
  卡片 z-index 也必须高于连线层，否则端口和卡片内容会被线的点击区域挡住。
- **「失败后」连线跨阶段也直接走贝塞尔，不绕底部通道。**
  用户明确要求它和上方普通连线看起来一样。代价是它会从中间阶段的任务卡片背后穿过
  （卡片在上层，遮住中段），这是接受的取舍：不要再加 `laneY` 之类的绕行通道，
  也不要把线提到卡片上面（会挡住端口拖拽和卡片双击）。
  注意 `captureScreenshot` 的 `clip` 只认 `width`/`height`，写成 `w`/`h` 会静默失败。

## 六·补四、登录图形验证码（密码错几次之后要填）

- 服务端生成，**不落库、不用会话**：`services/captcha.py` 画 SVG（108×40，随机旋转 + 干扰线 + 噪点），
  令牌是 `HMAC(SECRET_KEY, "CODE.EXP")` 取前 32 位，拼成 `exp.sig` 交给前端。
  校验时按用户提交的字符重算签名比对，所以多进程 / 重启都不影响，也不用建表。
- 两个开关在 **系统设置 → 安全 → 登录安全策略**：`captchaEnabled`（默认开）、
  `captchaAfter`（默认 1）。语义是「失败 N 次后，**下一次**登录必须先过验证码」，
  即设 1 = 错一次，下次就要填；设 4 = 错满 4 次，第 5 次才要填。
- **不存在的账号也要计数**（`_anon_fails`，键 `用户名|IP`，TTL 1 小时，容量上限 5000），
  否则「拿别人的用户名试密码」这条路径就绕过验证码了。注意：进入「要求验证码」分支后
  会直接返回，**不再累加计数**，所以卡在验证码这一步不会把账号一路推向锁定。
- 登录接口的错误响应刻意**不用 `fail()`**（`fail()` 的 `data` 恒为 `None`），
  而是手写 `{"code": 400, "msg": ..., "data": {"needCaptcha": true}}`。
  前端 `utils/http/index.ts` 的响应拦截器把 `data` 一并塞进 `HttpError`，
  登录页读 `error.data.needCaptcha` 决定是否把验证码行露出来。
- 前端 `views/auth/login/index.vue`：验证码行 `v-if="captchaNeeded"`，图片点击换一张；
  提交时只在 `captchaNeeded` 为真才带 `captchaCode` / `captchaToken`。

## 七、构建与验证

```bash
# 前端（先挪走 dist，避免批量删除保护拦截）
mv frontend/dist _quarantine/dist-old-$(date +%s)
cd frontend && node node_modules/vite/bin/vite.js build

# 后端
cd backend && ../.venv/Scripts/python.exe run.py      # 或 python run.py

# 冒烟
cd certd-lite && python tests/smoke.py --base http://127.0.0.1:8000
```

- `index.html` 必须带 `Cache-Control: no-cache, must-revalidate`：
  否则重新构建后浏览器还在跑旧 bundle，表现为「新功能没出现」。
- **无头验证（系统 Edge + CDP，脚本放 `_tmp/cdp-*.mjs`）有两个必踩的坑**：
  1. 路由是 **hash 模式**，地址必须写成 `http://localhost:5173/#/certd/pipeline/detail/5`；
     写成 `/certd/pipeline/detail/5` 会被重定向到工作台，然后你会以为「页面没渲染」。
  2. 登录态存在 **`sys-v3.0.2-user`**（键名带前端版本号，`art-design-pro` 的存储迁移会
     把 `sys-v0.0.0-user` 搬过去）。注入旧键虽然能靠迁移生效，但直接写新键更稳。
  另外「按钮点不到」这类问题**不要用 `el.click()` 验证** —— 它会绕过命中测试，
  遮罩 / `pointer-events: none` 全都测不出来。要用 `Input.dispatchMouseEvent` 发真实
  鼠标事件，再用 `document.elementFromPoint()` 断言命中的是不是目标元素。
- **测「任务配置抽屉」的「确定」要用没有必填项的任务类型。**
  `confirmTask` 会校验插件必填项，空参数的 `CertApply` 点确定只会弹
  「请填写「xxx」」、抽屉不关 —— 看起来非常像「按钮点不到」，很容易白查半小时。
  用 `DeployWait`（等待）或 `DeployBackupCerts`（数据备份），它们没有任何必填项。
- **Element Plus 的禁用态不在根元素上。** 判断 `el-select` 是否禁用要看
  `.el-select__wrapper.is-disabled` 或内部 `input.disabled`；
  根节点 `.el-select` 上**不带** `is-disabled`，只查根节点会得出「没禁用」的错误结论。

---

## 八、前端：分类、复用与响应式（CertHub 前端约定）

### 8.1 菜单必须按流程分类，不能平铺

一级菜单固定为四块：**工作台 / 证书流程 / 接入资源 / 站点监控 · 系统管理**。
新增页面先想清楚它属于哪个阶段（签发、部署、入库、接入、监控、系统），
再往对应分组里放；**不要**为单个功能再起一个一级菜单（单页功能直接挂一级，
比如「站点监控」就是直达页面，不做「监控 → 站点」两级）。

### 8.1·补、站点品牌（名称 / 副标题 / Logo）只有一处来源

- 「系统设置 → 站点信息」里的 name / subtitle / logo 存在 `sys_setting.site`，
  公开接口是 `GET /api/site/config`（免登录，登录页也要用）。
- 前端一律经 `store/modules/site.ts`（`useSiteStore`）：侧边栏标题、顶部栏标题、
  登录页左侧标题、`ArtLogo` 全部读它，**不要再直接读 `AppConfig.systemInfo.name`**，
  否则系统设置里改了名字菜单栏不跟着变。
- `ArtLogo` 在自定义 logo 加载失败时退回内置图标（不留空白块）；
  上传的 logo 由前端转 data URI 存进设置，不引入上传目录 / 图床依赖。
- 副标题留空 = 不渲染那一行；宽度靠 `text-overflow: ellipsis` 收，
  窄屏（≤800px）侧边栏收起时整块 `brand-text` 一起隐藏。

流水线的环节颜色是全局约定，页面里不要各自发明：
**证书申请 = 蓝(#409eff)、证书部署 = 绿(#67c23a)、发送通知 = 橙(#e6a23c)**，
取值统一走 `src/utils/certd.ts` 的 `STAGE_KIND_META`。
列表页的「申请 / 部署 / 通知」标签来自后端 `/api/pipeline/list` 的 `kinds` 字段
（后端解析 content 得出），**前端不要自己按 stepCount 猜**。

### 8.2 不造轮子：先找 art-design-pro 的现成组件

- 列表页：`useTable` + `ArtTable` + `ArtTableHeader` + `ArtSearchBar`；
- 表单：优先 `ArtForm`（自带栅格、响应式、标签排版、reset/submit），
  业务字段用 `views/certd/components/plugin-field.vue` 渲染；
- 统计 / 图表：`ArtStatsCard`、`ArtLineChart`、`ArtRingChart`、
  `ArtGaugeChart`（车速表仪表：弧线刻度 + 指针 + 中央/底部数字读数，
  `value` / `max` / `unit` 三个 prop 就够，配色按 70% / 90% 自动分档）；
- 图标：`ArtSvgIcon`（Iconify）与 `brand-avatar.vue`（本地文件优先）；
- 样式：用 `art-card` / `art-table-card` / `art-full-height` 与主题变量。

**插件表单只能是元数据驱动**：`PluginForm` 的字段来自后端插件元数据，
新增签发方式 / 部署目标 / 授权类型 / 通知渠道时，前端一行都不用改。
给某个插件写死表单 = 破坏约定，评审直接打回。

### 8.2·补、远程资源按证书域名自动匹配并显示

部署类任务的「站点名称 / 加速域名」不要让用户去面板里抄：

- 后端在字段元数据上声明 `remote="sites" | "cdnDomains"` + `remoteFrom="accessId"`
  + **`autoMatchDomains=True`**；加新插件照抄这三件套即可，前端不用改。
- **面板站点要支持多选**：宝塔 `siteName`、1Panel `websiteId`、NPM `proxyHostId` 一律用
  `component="tags"`（后端 handler 同时兼容老数据的单个字符串；1Panel 证书只上传一次，
  再循环绑定多个网站）。引擎 `_auto_match_resource` 会拿**所有证书 SAN** 去匹配，
  多选字段把所有命中项一次性选中，不要压回单个。
- NPM 代理主机用 `remote="npmProxyHosts"` 拉取（`resources.npm_proxy_hosts`），
  与站点/加速域名共用同一套「自动匹配 + 多选」逻辑。
- 前端 `plugin-field.vue` 负责：选好授权后立刻拉对端资源 → 按
  「证书申请任务的 domains」匹配（`*.x.com` 去掉 `*.` 后按后缀比）→ 自动选中并
  显示「按证书域名自动匹配：xxx」；匹配不到提示「可以从列表里手动选择」；
  用户手动改过就清掉「自动」标记，不再被覆盖。
- 证书域名由 `pipeline/detail.vue` 汇总后作为 `certDomains` 传进 `PluginForm` →
  `PluginField`；不在字段里硬编码域名来源。
- 卡片摘要里「站点名称 / 加速域名」排第一行；还没匹配时显示
  「运行时按证书域名自动匹配」，不要留空。
- 引擎侧 `_auto_match_resource()` 是兜底：任务里没填站点时按域名现场匹配并写日志。

**宝塔面板拉站点要注意参数**：`POST /data?action=getData` 必须带齐
`request_time / request_token / table=sites / limit / p / type / order / sort / search / tojs`，
少一个就回 `{"status": false, "msg": "指定参数无效!"}`——看着像接口密钥错了，
其实只是缺参数。站点名不一定是域名（宝塔允许自定义名），
所以备注 `ps` 也放进 `extra` 一起参与匹配。

### 8.2·补二、流水线编辑页的排版约定

- 页面顺序固定为：**操作条（标题 / 保存 / 定时任务 / 运行）→ 阶段列表 → 运行准备日志**。
  **顶部不放「日志」按钮、也不放启用/停用开关**：
  - 日志统一在底部固定终端（进页面时自动接上上次执行，阶段标题和任务卡图标也是日志入口，
    关掉后从那两个入口再打开）；
  - 启用/停用放在**「证书流水线」列表的表格里**（一列 `ElSwitch`，点了立刻生效，不用再保存一次）。
  「触发方式与执行设置」**收进抽屉**（由操作条上的「定时任务」按钮呼出），
  按钮角标显示人话时间（`每天 03:00` / `每周一 02:00` / `未设置`），原始 cron 放 tooltip。
  不要再把它做成占满整屏的卡片放回页面里。
- **开关里不许放文字**（不要 `inline-prompt` + `active-text`）：开关里塞字会把滑块压小、
  窄屏更难点。状态用开关旁边的文案（`已启用 / 已停用`）或 tooltip 表达。
- **元素变多不许互相挤压**：
  - 按钮 / 开关 / 标签在 flex 行里一律 `flex: 0 0 auto`；
  - 输入框保底 `min-width`（`.setting-row` 里 140px、标题 180px）；
  - 卡片摘要的值允许换两行（`-webkit-line-clamp: 2` + `word-break`），
    长域名 / 证书路径不靠省略号硬挤；
  - 标题允许两行，标签列 `max-width: 42%`，不要用「标签列无限变宽」去挤值列。
- 验收：CDP 分别按 1500 / 1100 / 820 / 430 四档宽度断言
  `documentElement.scrollWidth === innerWidth`、`.el-switch__inner` 文本为空、
  卡片顺序（HEADER → 触发方式 → STAGE）正确。

### 8.2·补三、日志与定时（执行过程的交互）

**日志只有一套渲染器**：`components/log-terminal.vue`（黑底 + 分词高亮）。

- 背景恒为黑色（不跟主题）：白底看 PEM / JSON 太累，这是产品约定。
- **不放复制 / 清空按钮，也不放「跟随」开关**：跟着最新行滚动是默认行为，
  用户往上翻自动暂停、滚回底部自动继续。日志只读，要带走内容自己选中复制。
- 高亮**靠分词渲染**（每段一个 span），**禁止 v-html**——日志里有用户填的域名与密钥路径。
  着色规则：时间戳灰、`===== 阶段：xxx =` 紫、`[任务名]` 蓝、URL 下划线蓝、
  PEM 紫、JSON 键绿、IP 橙、成功绿、失败红、警告黄。
- SSE 解析与「按阶段拆分」在 `composables/use-run-log.ts`，一次连接三种用法：
  整条流水线 / 按阶段 / 按任务过滤。不要在页面里再写第二份 SSE 解析。
- 流水线编辑页：
  - **每个阶段卡片下方显示该阶段自己的日志**（running 时描边变黄并标「执行中」），
    第一个阶段标记之前的行为「运行准备」单独一块；
  - **不同阶段的日志终端必须长得不一样**：终端传 `accent`（= 阶段色），
    左边框 3px + 标题着色，标题里写「阶段 N · 阶段名 日志」；
    两个阶段的终端颜色一样 = 没做完（申请蓝 / 部署绿 / 通知橙）；
  - **执行中任务卡图标换成带动画的执行者图标**（`.task-icon.is-running` 转圈 + `ri:robot-2-line` 呼吸），
    **点图标弹出该任务的日志弹窗**（阶段「放大」也走同一个弹窗）；
  - 日志弹窗只读：黑底 + 高亮 + 关闭，不放复制 / 清空。
- 列表页 / 历史页的「运行 / 日志」抽屉复用同一个 `LogPanel`（内部就是 `useRunLog` + `LogTerminal`）。

**定时用日历选，不让人背 cron**：

- 触发方式与执行设置**是抽屉，不是页面上的卡片**：入口是操作条上「保存」旁边的
  **「定时任务」按钮**（按钮上带当前 cron 角标），抽屉里放定时 / Webhook / 保留历史，
  底部「保存」直接落库并关闭。别再把这坨配置铺回页面里；
- 抽屉里提供 **每天 / 每周 / 每月 / 指定日期（日历）/ 自定义** 五档，
  时间用 `ElTimePicker`、指定日期用 `ElDatePicker type="datetime"`；
- 选择结果实时换算成 cron 并显示，同时给出「下次执行」预览；
- 打开已有流水线时用 `parseCron()` 把 cron 反推成日历状态，
  **不要出现「界面显示每天、实际 cron 是别的」**；
- 点常用预设标签也要同步日历状态（`applyPreset()`）。

**拉取域名必须可多选**：

- DNS 授权的域名用弹窗多选（主域名 / 泛域名分组标注，支持搜索、全选、只选泛域名），
  确认后**合并**进输入框（已有值不重复、不覆盖用户手填的域名）；
- 默认勾选泛域名（大多数证书要的就是 `*.example.com`）。

### 8.2·补四、工作台的资源仪表（CPU / 内存 / 系统盘）

- 「系统信息」卡片固定三块车速表（`ArtGaugeChart`）：CPU 使用率 / 内存使用率 /
  系统盘使用率，**硬盘只展示系统盘**，数据盘不铺在这里（接口仍返回全部 `disks`）。
- 系统盘由后端 `services/system_info.py` 判定：Windows 取 `SystemDrive`（通常是 `C:\`），
  类 Unix 取 `/`，结果放在 `systemDisk`，每块盘同时带 `system` 布尔位；
  前端只在老接口没有这两个字段时才自己兜底（C 盘 → 根目录 → 第一块盘）。
- 使用率分档（正常 / 偏高 / 告警）走 `utils/certd.ts` 的
  `usageLevel` / `usageColor` / `usageText`，阈值 70% / 90%，**页面里不要各自写一遍**。
- 仪表是 canvas，读不到 CSS 变量：暗色配色在 `ArtGaugeChart` 内部按 `isDark` 各给一套，
  换主题时 `useChartComponent` 会自动重绘。

### 8.2·补五、DNS 记录页（原「CNAME 记录」）

- 这个页面同时管两类行，靠后端的 `source` 区分：
  `manual`（手动登记的 CNAME，可同步 / 校验 / 编辑）与
  `acme` / `cloud`（证书申请自动写入的验证记录，**只读**，页面上只留「删除留痕」）。
  页面里不要自己判断「这条能不能同步」，一律看 `source`。
- 自动登记是引擎干的：写 / 删 `_acme-challenge.<域名>` 验证记录时调用
  `services/dns_log.py` 的 `remember()` / `forget()`；
  同一条记录（user + 记录名 + 类型）反复写入只更新一行并累加 `write_count`，
  清理后状态变 `cleaned` 但行保留 —— 用户由此能看出「这个域名走没走过 DNS 记录」。
- 记录名必须来自 `provider` 的真实写入结果（`engine._full_record_name()`），
  它是带 `record_prefix` 和子域名托管的；不要用 `root_domain()` 自己算，
  否则页面上的记录名和 DNS 后台对不上。
- 这些字段是后加的：`db.init_db()` 里的 `_COLUMN_PATCHES` 负责给老库幂等补列，
  以后再给老表加字段记得登记进去（SQLite 的 `create_all` 不会改已有表）。

### 8.2·补六、流水线分组（失败后转备用）

- 一个分组 = 一串「按顺序试一试」的流水线，菜单入口是**证书流水线**下面的
  **流水线分组**（`/certd/pipeline-group`，页面 `views/certd/pipeline/group.vue`）。
  数据表 `pi_pipeline_group`（成员存在 `items` JSON：`[{pipelineId, onFailurePipelineId}]`）
  与 `pi_pipeline_group_run`（一次分组执行 = 一行，`steps` JSON 记每一步）。
- **语义固定为「顺序尝试 + 失败转移」**，不要改成并行、也不要改成「全部跑一遍」：
  跑第一条 → 成功就结束；失败就跳它这一行配的 `onFailurePipelineId`；
  没配就直接判分组失败。典型场景是「主 CA 失败自动转备用 CA」。
- **同一条流水线在一次分组里只跑一次**（`group_runner._execute()` 里的 `visited` 集合）。
  这是硬规则：A 的失败转移指向 B、B 又指回 A 时，没有这个集合就是死循环。
  命中时记一条 `skipped` 步骤，界面上能看出「跳过是因为跑过了」。
- **分组不自己跑证书任务**，只调 `engine.run_pipeline_async()`，所以每次执行在
  「执行历史」里都有一条独立的 `History`，分组记录里的 `historyId` 指向它 ——
  界面上的「日志」按钮就跳到 `/certd/history`。不要另造一套执行日志。
- 分组在自己的线程里轮询执行历史等结果（`_wait_history()`，2 秒一次、最长 6 小时），
  **不要占用 engine 的线程池**，否则并发流水线会被分组卡住。
- 成员校验在 `routers/pipeline_group.py` 的 `_clean_items()`：流水线必须存在且属于当前用户、
  不能重复添加、`onFailurePipelineId` 不能指向自己。新增字段一并在这里校验，错误统一回一句中文。
- 列表接口要回填标题（`pipelineTitle` / `onFailurePipelineTitle`），前端不许多查一遍；
  列表行还带 `lastRun`（最近一次分组执行的状态与时间）。
- 执行页交互：运行后前端轮询 `GET /api/pipeline-group/run/{runId}` 直到状态变化，
  再提示成功 / 失败；「执行记录」抽屉按步骤列状态、失败转移目标和日志入口。

### 8.2·补七、阶段里每个步骤可单独启停

- 每个任务（步骤）都带 `enabled` 字段，**缺省 / true = 启用，false = 停用**；
  停用的步骤运行时**整段跳过**：不发请求、不算失败、不影响后续步骤
  （引擎 `PipelineRunner.run()` 里进任务循环第一件事就判 `enabled is False`）。
  历史里这一步的状态记 `disabled`（不是 failed / skipped），日志写「「XXX」已停用，跳过这一步」。
- **界面上开关不做成二级菜单**：任务卡头部右侧一个 `ElSwitch`（`size=small`，
  不塞文字），点了**立刻落库**（调 `save(true)`，失败回滚开关状态），
  并在卡片右上角显示「已停用」标签；整卡 `opacity: .62` + 虚线边框 + 图标去色，一眼看出这次不跑它。
  顶部摘要与阶段标题都要写「N 步已停用」，否则「4 个任务」和实际执行数对不上。
- **统计口径跟着走**：列表接口 `stepCount` 只算启用的步骤，另给 `taskCount` 与
  `stepDisabledCount`；`_content_kinds()` 也要跳过停用任务，
  否则「申请 + 部署」标签会写着一个这次根本不会执行的部署步骤。
- 单跑某个阶段时，`has_apply` 判断（决定要不要从证书库补证书上下文）同样要忽略停用的申请任务。
- 新建任务默认 `enabled: true`；老流水线内容里没有这个键，按启用处理，不用迁移数据。

### 8.2·补八、已经合并掉的页面（别再建独立菜单）

有两处「功能重叠的独立页」已经并进主页面，老路由保留成 redirect，菜单项一律删掉：

- **「账号与安全」→ 系统设置 → 安全**。原来的 `views/certd/profile/index.vue` 整体搬成
  `views/certd/system/components/account-security.vue`（基本资料 / 修改密码 / 两步验证），
  在 `system/setting.vue` 的「安全」页签里渲染。这个页签**所有登录用户都能看**
  （自己的账号自己改），而同一页签下的「登录安全策略」表单 `v-if="isAdmin"`。
  路由 `/certd/profile` → redirect `/certd/setting?tab=security`（`isHide: true`）。
  `config/modules/fastEnter.ts` 的「账号与安全」快捷入口也要跟着改 `routeName`。
- **「流水线分组」→ 证书流水线 → 分组页签**。`views/certd/pipeline/index.vue` 顶部加
  `.page-switch` 双页签（流水线 / 分组），列表内容包在 `v-if="activeTab === 'pipeline'"` 里，
  否则 `<PipelineGroup />`。页签与 URL 同步：`?tab=group` ⇄ 分组。
  路由 `/certd/pipeline-group` → redirect `/certd/pipeline?tab=group`。
  分组页原本按整页高度写死（`art-full-height` = `height: var(--art-full-height)`），
  嵌进页签后会多撑出页签条那 30px。**不能只写 `height: auto`** —— 高度变成内容驱动后
  表格没有可用高度，`el-table` 只剩 98px、空状态插画被裁成一条。正确写法是占满剩余空间：
  `.certd-pipeline :deep(.certd-group) { flex: 1 1 auto; height: auto; min-height: 0; }`。
- 合并时容易踩的两个小坑：
  1. `setting.vue` 原来把「安全」页签也 `v-if="isAdmin"` 了，合并后必须去掉，
     否则普通用户点进来只有一个「项目信息」页签。
  2. 非管理员默认落在哪个页签要兜底：`activeTab` 先读 `route.query.tab`，
     `onMounted` 里若当前页签对普通用户不可见，退回 `security`。

### 8.3 响应式是验收项

- 栅格必须有 `xs/sm/md/lg/xl` 降级，禁止写死列宽导致窗口变窄就横向滚动；
- 卡片墙用 `grid auto-fill + minmax`；
- 表单窄屏（< 768px）标签在上（`ArtForm` 的 `labelPosition` 按 `useWindowSize` 切换）；
- 验收方法：CDP 无头浏览器分别按 1600 / 1280 / 1024 / 768 / 414 五档宽度截图，
  断言 `document.documentElement.scrollWidth === innerWidth`，且控制台零报错。

### 8.3·补、路由导航与 loading 的硬规则（「卡在转圈」就是这些坑）

- **全屏 loading 只在 `handleDynamicRoutes` 里显示**（`loadingService.showLoading()`，
  `lock: true`，会挡住整页点击）。它只由 `closeLoading()` 或 `afterEach` 关闭。
- **守卫里不要用 `next(false)` 取消导航**：被取消的导航不会触发 `afterEach`，
  `pendingLoading` 就永远是 true，用户看到的就是「整页转圈点不动，只能刷新」。
  并发导航（初始化还没跑完又点了一次菜单）要等 `routeInitPromise` 结束再重新
  `next({ ...to, replace: true })`，见 `guards/beforeEach.ts`。
- **看门狗兜底**：`utils/ui/loading.ts` 里 12 秒没关就强制关掉；
  `utils/sys/error-handle.ts` 在全局异常 / 未处理 Promise 上也会先关 loading。
  这两个是最后一道保险，别删。
- **重新构建后老标签页必然拿到 404 的 chunk**（哈希变了、旧文件已删）：
  `guards/routerError.ts` 负责 `router.onError` → 先把 loading 关掉 → 识别出
  chunk 加载失败就带着目标路由刷新一次（`sessionStorage` 标记防死循环，
  `afterEach` 成功后解除标记）。新页面 / 新路由用了动态 import 也自动受这套逻辑保护。
- 排障顺序：卡在转圈 → 先看 `document.querySelectorAll(".el-loading-mask")` 是否还有；
  有就是守卫漏关（查导航是否被取消）；没有就是页面自己的 `v-loading` 卡住（查 finally）。

### 8.4 排障提醒（生产构建看不到 console）

`vite.config.ts` 里 terser 的 `drop_console` 是写死的，`.env` 里的 `VITE_DROP_CONSOLE` 不起作用，
所以**组件没导入时页面只会少一块，控制台一声不响**（真实踩坑：工作台漏 import
`BrandAvatar`，59 个图标位全空）。自查办法：

1. 组件一律显式 `import`（`views/certd/**` 不在 `unplugin-vue-components` 的自动导入目录里）；
2. 用 dev server（`vite --port 3006`）抓控制台 `[Vue warn]`，再看生产构建；
3. 用 CDP 断言关键 DOM 数量（`.brand-avatar`、`.task-card`、表格行数），不要只看「页面没白屏」。