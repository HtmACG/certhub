import { useEffect } from 'react'

const EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'wheel'] as const

/**
 * 闲置自动退出：用户在 N 分钟内没有任何鼠标 / 键盘 / 触摸 / 滚动操作，就调用 onIdle。
 * minutes <= 0 表示关闭。定时器只在 AppShell 里挂一次，事件都是 passive，不影响滚动性能。
 */
export function useIdleLogout(minutes: number, onIdle: () => void) {
  useEffect(() => {
    if (!minutes || minutes <= 0) return undefined

    let timer = 0
    const reset = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => onIdle(), minutes * 60_000)
    }

    EVENTS.forEach((name) => window.addEventListener(name, reset, { passive: true }))
    // 切回标签页也算一次操作，避免刚回来就被踢
    document.addEventListener('visibilitychange', reset)
    reset()

    return () => {
      window.clearTimeout(timer)
      EVENTS.forEach((name) => window.removeEventListener(name, reset))
      document.removeEventListener('visibilitychange', reset)
    }
  }, [minutes, onIdle])
}
