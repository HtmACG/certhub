/**
 * 路由工具函数
 *
 * 提供路由相关的工具函数
 *
 * @module utils/router
 */
import { RouteLocationNormalized, RouteRecordRaw } from 'vue-router'
import AppConfig from '@/config'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import i18n, { $t } from '@/locales'

/** 扩展的路由配置类型 */
export type AppRouteRecordRaw = RouteRecordRaw & {
  hidden?: boolean
}

/** 顶部进度条配置 */
export const configureNProgress = () => {
  NProgress.configure({
    easing: 'ease',
    speed: 600,
    showSpinner: false,
    parent: 'body'
  })
}

/**
 * 标题后缀（系统名称 / 浏览器标题）
 *
 * 默认取内置配置，站点信息接口返回后会由 store/modules/site.ts 调
 * setAppNameSuffix() 覆盖 —— 这样「系统设置 → 站点信息」里改的名字
 * 浏览器标题也跟着变，不用刷新。
 */
let appNameSuffix = AppConfig.systemInfo.name

/** 最近一次渲染过的页面名（用于站点信息后到时重拼标题） */
let lastPageTitle = ''

/**
 * 更新标题后缀（站点信息加载 / 保存后调用）
 * @param name 系统名称或浏览器标题
 */
export const setAppNameSuffix = (name: string): void => {
  appNameSuffix = (name || '').trim() || AppConfig.systemInfo.name
  if (lastPageTitle) {
    document.title = `${lastPageTitle} - ${appNameSuffix}`
  }
}

/**
 * 设置页面标题，根据路由元信息和系统信息拼接标题
 * @param to 当前路由对象
 */
export const setPageTitle = (to: RouteLocationNormalized): void => {
  const { title } = to.meta
  if (title) {
    lastPageTitle = formatMenuTitle(String(title))
    setTimeout(() => {
      document.title = `${lastPageTitle} - ${appNameSuffix}`
    }, 150)
  }
}

/**
 * 格式化菜单标题
 * @param title 菜单标题，可以是 i18n 的 key，也可以是字符串
 * @returns 格式化后的菜单标题
 */
export const formatMenuTitle = (title: string): string => {
  if (title) {
    if (title.startsWith('menus.')) {
      // 使用 te() 方法检查翻译键值是否存在，避免控制台警告
      if (i18n.global.te(title)) {
        return $t(title)
      } else {
        // 如果翻译不存在，返回键值的最后部分作为fallback
        return title.split('.').pop() || title
      }
    }
    return title
  }
  return ''
}
