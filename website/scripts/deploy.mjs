/**
 * 把 VitePress 构建产物发布到旧官网仓库（GitHub Pages 用的那个目录）。
 *
 * 用法：
 *   npm run deploy                 # 构建 + 同步到 ../website（默认）
 *   PAGES_DIR=D:/site npm run deploy
 *
 * 只做三件事：清掉目标目录里的旧站点文件 → 复制 dist → 打印提示。
 * **不动** .git / CNAME / .nojekyll / LICENSE，也**不会**自动 commit 或 push。
 */
import { cpSync, existsSync, readdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, '..', '.vitepress', 'dist')
const target = resolve(process.env.PAGES_DIR || join(here, '..', '..', '..', 'website'))

/** 目标目录里必须保留的东西（仓库元信息与域名配置） */
const KEEP = new Set(['.git', 'CNAME', '.nojekyll', 'LICENSE', '.gitignore', 'README.md'])

if (!existsSync(dist)) {
  console.error('没有 .vitepress/dist，先跑 npm run build')
  process.exit(1)
}

if (!existsSync(join(target, '.git'))) {
  console.error(`目标目录不是 git 仓库：${target}`)
  console.error('确认 PAGES_DIR 指向 GitHub Pages 仓库（例如 F:/certdsystem/website）')
  process.exit(1)
}

// 1. 清掉旧站点文件
let removed = 0
for (const name of readdirSync(target)) {
  if (KEEP.has(name)) continue
  rmSync(join(target, name), { recursive: true, force: true })
  removed++
}

// 2. 复制新产物（cpSync 会自己建目录；注意 .nojekyll / CNAME 是文件，不能先 mkdir）
let copied = 0
for (const name of readdirSync(dist)) {
  const from = join(dist, name)
  const to = join(target, name)
  cpSync(from, to, { recursive: true, force: true })
  copied++
}

const size = (p) => {
  const s = statSync(p)
  return s.isDirectory() ? 'dir' : `${(s.size / 1024).toFixed(0)} KB`
}

console.log(`已清理旧文件 ${removed} 项，复制新产物 ${copied} 项 → ${target}`)
console.log(`入口：${join(target, 'index.html')}（${size(join(target, 'index.html'))}）`)
console.log('\n下一步：cd 到目标目录，git status 看一眼，确认后自行 commit / push。')
