/**
 * 路由错误兜底
 *
 * 两个真实会把页面"锁死"的场景，都在这里收口：
 *
 * 1. **重新构建前端后，老标签页还在跑旧 bundle。**
 *    旧 bundle 里的动态 import 指向的是已经删掉的哈希文件，点菜单必然失败，
 *    用户看到的是「点了没反应 / 一直转圈」。这里识别出 chunk 加载失败后
 *    强制刷新一次拿新 bundle（用 sessionStorage 标记防止无限刷新）。
 * 2. **导航报错时全屏 loading 没人关。**
 *    loading 是 lock: true 的遮罩，漏关就是整页点不动；这里统一关掉。
 *
 * @module router/guards/routerError
 */
import type { Router } from 'vue-router'
import { loadingService } from '@/utils/ui'

/** 已经为 chunk 加载失败刷新过一次的标记（同一次会话只刷一次，避免死循环） */
const CHUNK_RELOAD_FLAG = 'sys-chunk-reloaded'

/** 判断是不是「chunk 加载失败」（换构建 / 网络抖动都可能） */
export function isChunkLoadError(error: unknown): boolean {
  const text = String((error as any)?.message || error || '')
  return (
    /Failed to fetch dynamically imported module/i.test(text) ||
    /error loading dynamically imported module/i.test(text) ||
    /Unable to preload CSS/i.test(text) ||
    /Importing a module script failed/i.test(text) ||
    /Loading chunk [\w-]+ failed/i.test(text) ||
    /dynamically imported module/i.test(text)
  )
}

/** 导航成功之后解除标记，下次换构建还能自动刷新 */
export function clearChunkReloadFlag(): void {
  try {
    sessionStorage.removeItem(CHUNK_RELOAD_FLAG)
  } catch {
    // 隐私模式下 sessionStorage 可能不可用，忽略
  }
}

export function setupRouterErrorHandler(router: Router): void {
  router.onError((error, to) => {
    // 先把遮罩关掉：报错时最忌讳留一个锁死的全屏 loading
    loadingService.hideLoading()

    if (!isChunkLoadError(error)) {
      console.error('[Router] 导航失败：', error)
      return
    }

    let reloaded = '0'
    try {
      reloaded = sessionStorage.getItem(CHUNK_RELOAD_FLAG) || '0'
    } catch {
      reloaded = '0'
    }
    if (reloaded === '1') {
      // 已经刷过一次还失败：多半是后端没起来 / 资源被删了，不要再刷
      console.error('[Router] 静态资源加载失败，且本会话已自动刷新过一次：', error)
      return
    }

    try {
      sessionStorage.setItem(CHUNK_RELOAD_FLAG, '1')
    } catch {
      // 忽略
    }

    // 刷新后要回到用户刚才点的那一页：hash 变了，重载后应用就会直接导航过去
    const target = (to as any)?.fullPath
    if (target && target !== '/' && !String(target).startsWith('/auth/')) {
      try {
        window.location.hash = '#' + target
      } catch {
        // 忽略
      }
    }

    console.warn('[Router] 前端资源已更新，自动刷新以加载新版本')
    window.location.reload()
  })
}
