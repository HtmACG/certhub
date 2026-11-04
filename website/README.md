# CertHub 官网与帮助文档（VitePress）

`certhub.htmacg.com` 的源码。用 **VitePress 1.x** 重写了原来手写的 `index.html` + `docs.html`：

- 首页是产品落地页（Hero / 数据 / 核心能力 / 界面演示 / 生态集成 / 五步流程 / FAQ / CTA）
- 帮助文档拆成多页（开始使用 / 配置 / 运维 / 开发），带侧边栏、目录、全文搜索、深浅色主题
- 「生态集成」「常见问题」「更新日志」是独立页面

## 目录

```text
website/
├─ index.md                  # 首页（layout: page，内容由下面的组件拼）
├─ ecosystem.md              # 生态集成（53 项集成 + 75 部署插件 + 41 授权类型）
├─ faq.md                    # 常见问题
├─ changelog.md              # 更新日志
├─ docs/                     # 帮助文档（13 篇）
├─ .vitepress/
│  ├─ config.mts             # 导航、侧边栏、搜索、SEO（sitemap / canonical / OG）
│  ├─ data/ecosystem.ts      # ★ 产品数据（插件清单、CA、通知渠道、统计数字）
│  └─ theme/
│     ├─ index.ts            # 扩展默认主题、注册全局组件
│     ├─ custom.css          # 品牌色与首页样式（白底 + #1a73e8 + 等宽字标签）
│     └─ components/         # HomeHero / DemoShowcase / EcoSection / PluginGroups …
├─ public/                   # 原样复制的静态资源（favicon、logo、截图、厂商图标）
├─ scripts/deploy.mjs        # 构建产物同步到 GitHub Pages 仓库
└─ _tools/shot.mjs           # 用系统 Edge 给产品界面拍截图（免安装浏览器）
```

## 开发

```bash
cd certd-lite/website
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物 .vitepress/dist
npm run preview    # 预览构建结果
```

## 数据从哪来

首页与「生态集成」页的数量、清单都读 `.vitepress/data/ecosystem.ts`，它对应后端
`backend/app/plugins.py` 的注册表（`TASK_PLUGINS` / `ACCESS_TYPES` / `NOTIFY_TYPES` / `ACME_PROVIDERS`）。
**后端加了插件，在这里补一条**，数量由数组长度算出来，不要写死。

## 换产品截图

`_tools/shot.mjs` 用系统自带的 Edge（headless + CDP）截图，不需要装 Playwright：

```bash
# 后端与 webui dev server 先跑起来（8000 / 5174）
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"userName":"admin","password":"123456"}' | ...)   # 取 data.token

cd website
TOKEN=$TOKEN BASE_URL=http://127.0.0.1:5174 node _tools/shot.mjs _tools/pages.json public/assets/shots 1440
```

`pages.json` 里配页面（HashRouter 路由写成 `/#/certs` 这种），TOKEN 会注入 `localStorage` 的
`certhub.token`，免登录直接进后台。

## 发布

产物同步到旧官网仓库（GitHub Pages，`certhub.htmacg.com`）：

```bash
npm run deploy      # = vitepress build + node scripts/deploy.mjs
```

`deploy.mjs` 只做两件事：清掉目标目录里的旧站点文件 → 复制 `dist`。
它**不动** `.git` / `CNAME` / `.nojekyll` / `LICENSE`，也**不会** commit 或 push —— 同步完自己
`git status` 看一眼再提交。目标目录默认 `F:/certdsystem/website`，可用 `PAGES_DIR` 覆盖。

## 约定

- **不引外链字体 / CDN 图标**：内网和离线环境下会变成空白块。图标全部放在 `public/logos/`。
- 新增组件记得在 `.vitepress/theme/index.ts` 里注册（首页与文档页共用）。
- 文档里要写 <code v-pre>{{ }}</code> 这类模板语法时，用 `<code v-pre>…</code>` 包起来，
  否则 Vue 会把它当成插值去求值，构建直接报错。
