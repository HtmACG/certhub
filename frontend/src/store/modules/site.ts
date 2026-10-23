/**
 * 站点信息 store
 *
 * 系统设置里能改的「站点名称 / 副标题 / Logo / 浏览器标题」都是后端存在
 * sys_setting.site 里的（公开接口 /api/site/config，无需登录），
 * 侧边栏标题、顶部栏标题、Logo 全部从这里取，改完刷新即可生效。
 *
 * 约定：
 * - 取不到值（接口失败 / 还没请求回来）时一律退回 AppConfig.systemInfo.name，
 *   页面不会出现空标题；
 * - ensureLoaded() 并发去重，顶部栏与侧边栏同时挂载也只发一次请求。
 *
 * @module store/modules/site
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import AppConfig from '@/config'
import { fetchSiteConfig } from '@/api/certd'
import { setAppNameSuffix } from '@/utils/router'

interface SiteConfig {
  name: string
  subtitle: string
  title: string
  logo: string
}

export const useSiteStore = defineStore('siteStore', () => {
  const name = ref('')
  const subtitle = ref('')
  const title = ref('')
  const logo = ref('')
  const loaded = ref(false)

  /** 同一时间只发一次请求 */
  let loadingTask: Promise<void> | null = null

  /** 把后端返回的站点配置写进 store（保存设置后也会直接调它） */
  const apply = (data: Partial<SiteConfig> | null | undefined): void => {
    if (!data) return
    name.value = String(data.name || '').trim()
    subtitle.value = String(data.subtitle || '').trim()
    title.value = String(data.title || '').trim()
    logo.value = String(data.logo || '').trim()
    loaded.value = true
    // 浏览器标题的后缀跟着站点信息走（「浏览器标题」优先，没填用站点名称）
    setAppNameSuffix(title.value || name.value)
  }

  const ensureLoaded = async (): Promise<void> => {
    if (loaded.value) return
    if (loadingTask) return loadingTask
    loadingTask = fetchSiteConfig()
      .then((data) => apply(data as Partial<SiteConfig>))
      .catch(() => {
        // 接口不可用时不阻塞渲染，标题回退到内置默认值
        loaded.value = true
      })
      .finally(() => {
        loadingTask = null
      })
    return loadingTask
  }

  /** 强制重新拉一次（保存系统设置后调用） */
  const reload = async (): Promise<void> => {
    loaded.value = false
    await ensureLoaded()
  }

  /** 菜单 / 顶部栏显示的名称，空则回退内置默认值 */
  const displayName = computed(() => name.value || AppConfig.systemInfo.name)

  /** 副标题，没填就是空串（模板里据此决定要不要渲染那一行） */
  const displaySubtitle = computed(() => subtitle.value)

  /** 自定义 Logo 地址，空串表示用内置图标 */
  const logoUrl = computed(() => logo.value)

  return {
    name,
    subtitle,
    title,
    logo,
    loaded,
    displayName,
    displaySubtitle,
    logoUrl,
    apply,
    ensureLoaded,
    reload
  }
})
