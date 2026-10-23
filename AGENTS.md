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
- 统计 / 图表：`ArtStatsCard`、`ArtLineChart`、`ArtRingChart`；
- 图标：`ArtSvgIcon`（Iconify）与 `brand-avatar.vue`（本地文件优先）；
- 样式：用 `art-card` / `art-table-card` / `art-full-height` 与主题变量。

**插件表单只能是元数据驱动**：`PluginForm` 的字段来自后端插件元数据，
新增签发方式 / 部署目标 / 授权类型 / 通知渠道时，前端一行都不用改。
给某个插件写死表单 = 破坏约定，评审直接打回。

### 8.2·补、远程资源按证书域名自动匹配并显示

部署类任务的「站点名称 / 加速域名」不要让用户去面板里抄：

- 后端在字段元数据上声明 `remote="sites" | "cdnDomains"` + `remoteFrom="accessId"`
  + **`autoMatchDomains=True`**；加新插件照抄这三件套即可，前端不用改。
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
  「触发方式与执行设置」**收进抽屉**（由操作条上的「定时任务」按钮呼出），
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

### 8.3 响应式是验收项

- 栅格必须有 `xs/sm/md/lg/xl` 降级，禁止写死列宽导致窗口变窄就横向滚动；
- 卡片墙用 `grid auto-fill + minmax`；
- 表单窄屏（< 768px）标签在上（`ArtForm` 的 `labelPosition` 按 `useWindowSize` 切换）；
- 验收方法：CDP 无头浏览器分别按 1600 / 1280 / 1024 / 768 / 414 五档宽度截图，
  断言 `document.documentElement.scrollWidth === innerWidth`，且控制台零报错。

### 8.4 排障提醒（生产构建看不到 console）

`vite.config.ts` 里 terser 的 `drop_console` 是写死的，`.env` 里的 `VITE_DROP_CONSOLE` 不起作用，
所以**组件没导入时页面只会少一块，控制台一声不响**（真实踩坑：工作台漏 import
`BrandAvatar`，59 个图标位全空）。自查办法：

1. 组件一律显式 `import`（`views/certd/**` 不在 `unplugin-vue-components` 的自动导入目录里）；
2. 用 dev server（`vite --port 3006`）抓控制台 `[Vue warn]`，再看生产构建；
3. 用 CDP 断言关键 DOM 数量（`.brand-avatar`、`.task-card`、表格行数），不要只看「页面没白屏」。