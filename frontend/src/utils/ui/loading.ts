/**
 * 全局 Loading 加载管理模块
 *
 * 提供统一的全屏加载动画管理
 *
 * ## 主要功能
 *
 * - 全屏 Loading 显示和隐藏
 * - 自动适配明暗主题背景色
 * - 自定义 SVG 加载动画
 * - 单例模式防止重复创建
 * - 锁定页面交互
 *
 * ## 使用场景
 *
 * - 页面初始化加载
 * - 大量数据请求
 * - 路由切换过渡
 * - 异步操作等待
 *
 * ## 特性
 *
 * - 自动检测当前主题并应用对应背景色
 * - 使用自定义 SVG 动画（四点旋转）
 * - 单例模式确保同时只有一个 Loading
 * - 提供便捷的显示/隐藏方法
 *
 * @module utils/ui/loading
 * @author Art Design Pro Team
 */
import { fourDotsSpinnerSvg } from '@/assets/svg/loading'

/**
 * 获取当前主题对应的loading背景色
 * @returns 背景色字符串
 */
const getLoadingBackground = (): string => {
  const isDark = document.documentElement.classList.contains('dark')
  return isDark ? 'rgba(7, 7, 7, 0.85)' : '#fff'
}

const DEFAULT_LOADING_CONFIG = {
  lock: true,
  get background() {
    return getLoadingBackground()
  },
  svg: fourDotsSpinnerSvg,
  svgViewBox: '0 0 40 40',
  customClass: 'art-loading-fix'
} as const

interface LoadingInstance {
  close: () => void
}

/**
 * 兜底超时：loading 是 lock: true 的全屏遮罩，一旦没人关它，整个应用就"卡死"了
 * （只能刷新）。路由守卫里任何一条被取消的导航都可能漏掉关闭，所以这里加个看门狗：
 * 超过这个时间还没被关掉就强制关闭，宁可少遮一次也不能把页面锁死。
 */
const AUTO_HIDE_MS = 12000

let loadingInstance: LoadingInstance | null = null
let autoHideTimer: number | null = null

/** 清掉兜底定时器 */
function clearAutoHideTimer(): void {
  if (autoHideTimer !== null) {
    clearTimeout(autoHideTimer)
    autoHideTimer = null
  }
}

export const loadingService = {
  /**
   * 显示 loading
   * @returns 关闭 loading 的函数
   */
  showLoading(): () => void {
    if (!loadingInstance) {
      // 每次显示时获取最新的配置，确保背景色与当前主题同步
      const config = {
        ...DEFAULT_LOADING_CONFIG,
        background: getLoadingBackground()
      }
      loadingInstance = ElLoading.service(config)
    }
    clearAutoHideTimer()
    autoHideTimer = window.setTimeout(() => {
      console.warn('[loading] 超过 ' + AUTO_HIDE_MS + ' ms 仍未关闭，已自动关闭（导航可能被取消）')
      this.hideLoading()
    }, AUTO_HIDE_MS)
    return () => this.hideLoading()
  },

  /**
   * 隐藏 loading
   */
  hideLoading(): void {
    clearAutoHideTimer()
    if (loadingInstance) {
      loadingInstance.close()
      loadingInstance = null
    }
  }
}
