/**
 * 插件元数据 store
 *
 * 后端是「元数据驱动」的（backend/app/plugins.py）：新增签发方式 / 部署目标 /
 * DNS 服务商 / 通知渠道只改后端，前端表单、下拉、任务选择器全部自动出现。
 * 这份缓存就是那个「自动出现」的来源，前端**不允许**硬编码插件清单。
 *
 * @module store/modules/certd
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchPluginMeta, type PluginMeta, type TaskPlugin } from '@/api/certd'

export const usePluginStore = defineStore('pluginStore', () => {
  const meta = ref<PluginMeta | null>(null)
  const loading = ref(false)
  /** 同一时间只发一次请求，多个页面同时挂载时不会打出重复请求 */
  let loadingTask: Promise<PluginMeta> | null = null

  const ensureLoaded = async (): Promise<PluginMeta> => {
    if (meta.value) return meta.value
    if (loadingTask) return loadingTask
    loading.value = true
    loadingTask = fetchPluginMeta()
      .then((data) => {
        meta.value = data
        return data
      })
      .finally(() => {
        loading.value = false
        loadingTask = null
      })
    return loadingTask
  }

  /** 按 type 取任务插件元数据 */
  const pluginOf = (type: string): TaskPlugin | undefined =>
    (meta.value?.plugins || []).find((p) => p.type === type)

  /** 任务插件按分组：cert / deploy / notify */
  const pluginsByGroup = computed<Record<string, TaskPlugin[]>>(() => {
    const grouped: Record<string, TaskPlugin[]> = { cert: [], deploy: [], notify: [] }
    for (const plugin of meta.value?.plugins || []) {
      const key = plugin.group || 'cert'
      ;(grouped[key] ||= []).push(plugin)
    }
    return grouped
  })

  /** 部署插件按分类：主机 / 面板 / 集群 / 云 CDN / 对象存储 / 其它 */
  const deployByCategory = computed<{ category: string; plugins: TaskPlugin[] }[]>(() => {
    const map = new Map<string, TaskPlugin[]>()
    for (const plugin of meta.value?.plugins || []) {
      if (plugin.group !== 'deploy') continue
      const category = plugin.category || '其它'
      if (!map.has(category)) map.set(category, [])
      map.get(category)!.push(plugin)
    }
    return [...map.entries()].map(([category, plugins]) => ({ category, plugins }))
  })

  const accessTypes = computed(() => meta.value?.accessTypes || {})
  const accessCategories = computed(() => meta.value?.accessCategories || [])
  const notifyTypes = computed(() => meta.value?.notifyTypes || {})
  const acmeProviders = computed(() => meta.value?.acmeProviders || {})
  const dnsProviders = computed(() => meta.value?.dnsProviders || {})

  /** 有远程资源拉取能力的字段用的资源类型中文名 */
  const remoteKindName = (kind: string): string => {
    const names: Record<string, string> = {
      domains: '域名',
      sites: '站点',
      certs: '证书',
      namespaces: '命名空间',
      namespacelist: '命名空间',
      buckets: '存储桶',
      cdndomains: '加速域名',
    }
    return names[kind] || '资源'
  }

  return {
    meta,
    loading,
    ensureLoaded,
    pluginOf,
    pluginsByGroup,
    deployByCategory,
    accessTypes,
    accessCategories,
    notifyTypes,
    acmeProviders,
    dnsProviders,
    remoteKindName,
  }
})
