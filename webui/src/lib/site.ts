import { useQuery } from '@tanstack/react-query'
import { fetchSiteConfig } from './api'

/** 站点公开配置（名称 / logo / 登录背景），登录页、侧边栏、浏览器标题共用一份缓存 */
export function useSiteConfig() {
  return useQuery({
    queryKey: ['site-config'],
    queryFn: fetchSiteConfig,
    staleTime: 5 * 60_000,
    retry: 0,
  })
}
