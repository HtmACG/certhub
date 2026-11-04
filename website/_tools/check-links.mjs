/**
 * 站内链接自检：扫描构建产物里的 href / src，确认目标文件真的存在。
 *
 *   node _tools/check-links.mjs                 # 检查 .vitepress/dist
 *   node _tools/check-links.mjs ../website      # 检查已发布目录（GitHub Pages 仓库）
 *
 * 只查站内绝对路径与相对路径；外链（http/https/mailto）跳过。
 * 退出码非 0 表示有死链，可直接挂在 CI 或 deploy 前面。
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(process.argv[2] || path.join(here, '..', '.vitepress', 'dist'))

if (!fs.existsSync(root)) {
  console.error(`目录不存在：${root}`)
  process.exit(1)
}

/** 递归收集 html */
function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    const stat = fs.statSync(full)
    if (stat.isDirectory()) walk(full, out)
    else if (name.endsWith('.html')) out.push(full)
  }
  return out
}

/** 站内路径 → 磁盘文件；不存在返回 null */
function resolveTarget(refPath, pageFile) {
  const clean = decodeURIComponent(refPath.split('#')[0].split('?')[0])
  if (!clean) return '' // 纯锚点

  // 绝对路径从站点根算，相对路径（./ ../ foo.html）从当前页面所在目录算
  const base = clean.startsWith('/') ? root : path.dirname(pageFile)
  const target = path.resolve(base, clean.replace(/^\//, ''))

  const candidates = [target, path.join(target, 'index.html'), `${target}.html`]
  for (const c of candidates) {
    if (fs.existsSync(c) && fs.statSync(c).isFile()) return c
  }
  return null
}

const files = walk(root)
const problems = []
let checked = 0

for (const file of files) {
  const html = fs.readFileSync(file, 'utf8')
  const page = '/' + path.relative(root, file).split(path.sep).join('/')

  for (const m of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const ref = m[1]
    if (!ref || ref.startsWith('http') || ref.startsWith('//')) continue
    if (ref.startsWith('mailto:') || ref.startsWith('data:') || ref.startsWith('javascript:')) continue
    if (ref.startsWith('#')) continue

    checked++
    if (resolveTarget(ref, file) === null) problems.push({ page, ref })
  }
}

const uniq = new Map()
for (const p of problems) uniq.set(`${p.page} -> ${p.ref}`, p)

if (uniq.size === 0) {
  console.log(`✓ 链接自检通过：${files.length} 个页面，${checked} 个站内引用，无死链`)
  process.exit(0)
}

console.error(`✗ 发现 ${uniq.size} 条死链（共 ${checked} 个站内引用）：`)
for (const { page, ref } of uniq.values()) console.error(`  ${page}  ->  ${ref}`)
process.exit(1)
