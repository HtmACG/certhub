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
 *
 * 路由 `meta.title` 允许写三种形态，这里统一收敛成「当前语言下的展示文本」：
 *
 * 1. **i18n key**（`certd.menu.pipeline` 或老脚手架的 `menus.xxx`）
 *    —— 用 `te()` 判断词条是否存在，存在就翻译；不存在则把 key 当字面量返回，
 *    这样历史路由即使词条漏写也不会出现空白菜单。
 * 2. **后端下发的动态标题**（菜单从数据库来、按当前语言已翻译好）
 *    —— 不在词条里，原样返回。
 *
 * ⚠️ 这里**不能**只认 `menus.` 前缀：certd 业务路由用的是 `certd.*` 命名空间。
 *
 * ⚠️ 本函数是「命令式取词」，返回的是**快照字符串**。放在 `computed` 里会有响应式依赖
 * （调用链上读了 `i18n.global.locale`），切语言后自动重算；
 * 但如果是在 `setup` 里直接调用一次并存进普通 ref，就不会跟着变。
 * 所以业务侧做「语言切换后要跟随」的文案，一律走 `computed(() => formatMenuTitle(...))`。
 *
 * @param title 菜单标题（i18n key 或纯文本）
 * @returns 当前语言下的展示文本
 */
export const formatMenuTitle = (title: string): string => {
  if (!title) return ''
  // 读一次 locale，建立响应式依赖：切语言时外层 computed 会重算
  // （legacy: false 下 locale 是 WritableComputedRef，类型上可能是 string，这里统一按 ref 取）
  void (i18n.global.locale as unknown as { value: string }).value
  if (title.indexOf('.') > 0 && i18n.global.te(title)) {
    return $t(title)
  }
  return title
}
