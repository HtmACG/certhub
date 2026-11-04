/**
 * 官网截图工具：用系统 Edge（headless + CDP）给 CertHub WebUI 拍整页长图。
 *
 * 用法：
 *   node _tools/shot.mjs _tools/pages.json public/assets/shots 1440
 *
 * 环境变量：
 *   BASE_URL  默认 http://127.0.0.1:5174（webui dev server）
 *   TOKEN     certhub.token，注入 localStorage 免登录
 *   EDGE_PATH 默认 C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe
 *   VIEWPORT_H 默认 900
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'

const EDGE = process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const PORT = Number(process.env.CDP_PORT || 9333)
const MAX_H = Number(process.env.MAX_H || 4000) // 产品界面是应用壳，不需要超长图

const pagesFile = process.argv[2]
const outDir = process.argv[3]
const WIDTH = Number(process.argv[4] || 1440)
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5174'
const HEIGHT = Number(process.env.VIEWPORT_H || 900)
const TOKEN = process.env.TOKEN || ''

if (!pagesFile || !outDir) {
  console.error('用法: node shot.mjs <pagesJson> <outDir> [width]')
  process.exit(1)
}
fs.mkdirSync(outDir, { recursive: true })
const pages = JSON.parse(fs.readFileSync(pagesFile, 'utf8'))

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const userDataDir = path.join(os.tmpdir(), 'edge-shot-' + Date.now())
const edge = spawn(
  EDGE,
  [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${userDataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=1',
    '--disable-features=Translate,AcceptCHFrame',
    'about:blank'
  ],
  { stdio: 'ignore' }
)

let ws
let msgId = 0
const pending = new Map()

function send(method, params = {}) {
  const id = ++msgId
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
}

async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl)
      if (page) return page.webSocketDebuggerUrl
    } catch {
      /* 还没起来 */
    }
    await sleep(300)
  }
  throw new Error('CDP 连接失败：Edge 未在 ' + PORT + ' 暴露调试端口')
}

async function evalJs(expression, awaitPromise = true) {
  const r = await send('Runtime.evaluate', {
    expression,
    awaitPromise,
    returnByValue: true,
    timeout: 30000
  })
  if (r.exceptionDetails) throw new Error('页面脚本异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 300))
  return r.result?.value
}

const READY_JS = `(async () => {
  const step = 600
  for (let y = 0; y < document.body.scrollHeight; y += step) {
    window.scrollTo(0, y)
    await new Promise((r) => setTimeout(r, 120))
  }
  window.scrollTo(0, 0)
  await Promise.race([
    Promise.all([...document.images].filter((i) => !i.complete)
      .map((i) => new Promise((res) => { i.onload = i.onerror = res }))),
    new Promise((r) => setTimeout(r, 6000))
  ])
  await new Promise((r) => setTimeout(r, 400))
  return { h: document.body.scrollHeight }
})()`

/** 关掉可能挡住页面的弹层（React 版：dialog / toast） */
const CLEAN_JS = `(async () => {
  let closed = 0
  document.querySelectorAll('[role="dialog"] button[aria-label="关闭"], [role="dialog"] button[aria-label="Close"]')
    .forEach((b) => { b.click(); closed++ })
  document.querySelectorAll('[data-sonner-toaster] li').forEach((n) => n.remove())
  await new Promise((r) => setTimeout(r, 300))
  return { closed }
})()`

async function main() {
  const wsUrl = await connect()
  ws = new WebSocket(wsUrl)
  await new Promise((res, rej) => {
    ws.onopen = res
    ws.onerror = () => rej(new Error('WebSocket 错误'))
  })
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data)
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id)
      pending.delete(m.id)
      m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
    }
  }

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Network.enable')

  if (TOKEN) {
    await send('Page.addScriptToEvaluateOnNewDocument', {
      source: `try { localStorage.setItem('certhub.token', ${JSON.stringify(TOKEN)}); } catch (e) {}`
    })
  }
  await send('Emulation.setDeviceMetricsOverride', {
    width: WIDTH,
    height: HEIGHT,
    deviceScaleFactor: 1,
    mobile: false
  })

  const report = []
  for (const p of pages) {
    const url = p.url.startsWith('http') ? p.url : BASE + p.url
    const rec = { file: p.file, name: p.name, url, ok: false }
    try {
      await send('Page.navigate', { url })
      for (let i = 0; i < 50; i++) {
        const st = await evalJs('document.readyState', false).catch(() => '')
        if (st === 'complete') break
        await sleep(200)
      }
      await sleep(p.wait ?? 2200)
      if (!p.keepDialog) await evalJs(CLEAN_JS)
      await evalJs(READY_JS)
      await sleep(300)

      const { contentSize } = await send('Page.getLayoutMetrics')
      const w = Math.min(Math.ceil(contentSize.width), WIDTH)
      const h = Math.min(Math.ceil(contentSize.height), MAX_H)
      const shot = await send('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: w, height: h, scale: 1 }
      })
      const out = path.join(outDir, p.file + '.png')
      fs.writeFileSync(out, Buffer.from(shot.data, 'base64'))
      rec.ok = true
      rec.width = w
      rec.height = h
      rec.bytes = fs.statSync(out).size
      console.log(`OK   ${p.file.padEnd(22)} ${w}x${h}  ${p.name}`)
    } catch (e) {
      rec.error = e.message
      console.log(`FAIL ${p.file.padEnd(22)} ${e.message}`)
    }
    report.push(rec)
  }

  fs.writeFileSync(path.join(outDir, '_report.json'), JSON.stringify(report, null, 2))
  console.log(`\n完成 ${report.filter((r) => r.ok).length}/${report.length}`)

  ws.close()
  edge.kill()
  await sleep(600)
  try {
    fs.rmSync(userDataDir, { recursive: true, force: true })
  } catch {}
  process.exit(0)
}

main().catch((e) => {
  console.error('致命错误:', e.message)
  try {
    edge.kill()
  } catch {}
  process.exit(1)
})
