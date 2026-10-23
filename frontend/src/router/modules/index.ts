import { AppRouteRecord } from '@/types/router'
import { certdRoutes } from './certd'

/**
 * 导出所有模块化路由
 *
 * 只挂 CertHub 业务路由：art-design-pro 自带的模板页（dashboard/template/widgets/
 * examples/article/...）与本系统无关，留在菜单里只会干扰操作。
 * 403 / 404 / 500 由 staticRoutes 直接提供（不需要进菜单）。
 */
export const routeModules: AppRouteRecord[] = [...certdRoutes]
