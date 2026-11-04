/**
 * 把 webui 的构建产物放到后端托管的目录里（certd-lite/frontend/dist）。
 * 旧产物先改名备份，不做删除 —— 出问题时可以直接换回来。
 */
import { cpSync, existsSync, renameSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, '..', 'dist')
const target = resolve(here, '..', '..', 'frontend', 'dist')

if (!existsSync(dist)) {
  console.error('没有 dist，先跑 npm run build')
  process.exit(1)
}

if (existsSync(target)) {
  const backup = `${target}.bak-${Date.now()}`
  renameSync(target, backup)
  console.log(`旧产物已备份到 ${backup}`)
}

rmSync(target, { recursive: true, force: true })
cpSync(dist, target, { recursive: true })
console.log(`已复制到 ${join('frontend', 'dist')}，刷新 http://127.0.0.1:8000 即可看到新界面`)
