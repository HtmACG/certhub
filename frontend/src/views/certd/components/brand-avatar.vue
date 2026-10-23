<!--
  品牌图标
  =========================================================
  取值优先级（与 AGENTS.md 第三条一致）：
    1. 本地 SVG（后端 tools/fetch_access_logos.py 下到 public/logos/，全部矢量）
    2. Iconify 图标名（ArtSvgIcon，离线时可能拉不到）
    3. 按类型给一个近似的内联矢量图标（brand-fallback-icon.vue，离线可用）

  只用 logo 图标、不用 favicon：favicon 是 PNG/ICO 位图，大小不一、边缘发虚，
  跟矢量图标放一起很违和；而且它同样依赖在线服务，内网 / 离线就成了空白块。
-->
<template>
  <div class="brand-avatar" :style="boxStyle">
    <img
      v-if="imageSrc && !imageFailed"
      :src="imageSrc"
      :alt="name"
      class="brand-img"
      @error="imageFailed = true"
    />
    <ArtSvgIcon
      v-else-if="icon && !iconFailed"
      ref="iconRef"
      :icon="icon"
      :style="{ color: color, fontSize: Math.round(size * 0.56) + 'px' }"
    />
    <!-- 本地文件与 Iconify 都拿不到时，按类型给一个近似的矢量图标（内联 SVG，离线可用）。
         不再退化成「品牌色底 + 首字母」的文字牌。 -->
    <BrandFallbackIcon v-else :kind="iconKind" :style="{ color }" />
  </div>
</template>

<script setup lang="ts">
  import BrandFallbackIcon from './brand-fallback-icon.vue'

  defineOptions({ name: 'BrandAvatar' })

  /**
   * 名称 → 兜底图标类别。
   * 顺序有讲究：先判「面板 / 主机」再判「云」，否则「宝塔面板」会被云规则抓走。
   */
  const KIND_RULES: [RegExp, string][] = [
    [/面板|1Panel|宝塔|群晖|威联通|DSM|QTS|Proxmox|PVE|Lucky|Plesk|NPM|雷池|Safeline|OpenWrt/i, 'panel'],
    [/主机|服务器|SSH|命令|脚本|Command|Script/i, 'host'],
    [/证书|ACM|SSL|EAB/i, 'cert'],
    [/通知|邮件|邮箱|Notify|Mail/i, 'notify'],
    [/等待|延时|备份|Wait|Backup/i, 'script'],
    [/CDN|CDN|DCDN|加速|云|OSS|COS|OBS|TOS|S3|R2|Kodo|存储|DNS|域名|解析/i, 'cloud'],
  ]

  interface Props {
    /** 本地图标路径，如 /logos/access/aliyun.svg */
    logoFile?: string
    /** Iconify 图标名（本地文件缺失时的兜底） */
    logo?: string
    /** 品牌色 */
    color?: string
    /** 首字母（后端 short 字段） */
    short?: string
    /** 名称（alt / 首字母兜底） */
    name?: string
    /** 尺寸（px） */
    size?: number
  }

  const props = withDefaults(defineProps<Props>(), {
    logoFile: '',
    logo: '',
    color: '#909399',
    short: '',
    name: '',
    size: 36,
  })

  const imageFailed = ref(false)
  /** Iconify 图标拉不到（离线 / 该品牌没图标）时回退字母牌，不留空白块 */
  const iconFailed = ref(false)
  const iconRef = ref<any>(null)
  let iconTimer: ReturnType<typeof setTimeout> | null = null

  const imageSrc = computed(() => props.logoFile || '')
  const icon = computed(() => (imageSrc.value ? '' : props.logo))

  /** 兜底图标类别（名称关键词推断，不依赖后端新增字段） */
  const iconKind = computed(() => {
    const text = props.name || ''
    for (const [pattern, kind] of KIND_RULES) {
      if (pattern.test(text)) return kind
    }
    return 'generic'
  })

  /**
   * Iconify 图标是异步拉取的：轮询一小会儿等它出现，
   * 超时（离线 / 该品牌没有图标）就回退字母牌，不留空白块。
   */
  const watchIcon = () => {
    if (iconTimer) clearTimeout(iconTimer)
    if (!icon.value) return
    let waited = 0
    const tick = () => {
      const host = iconRef.value?.$el as HTMLElement | undefined
      if (host && host.querySelector('svg')) return
      waited += 300
      if (waited >= 6000) {
        iconFailed.value = true
        return
      }
      iconTimer = setTimeout(tick, 300)
    }
    iconTimer = setTimeout(tick, 300)
  }

  const boxStyle = computed(() => ({
    width: props.size + 'px',
    height: props.size + 'px',
    borderRadius: props.size > 30 ? '10px' : '8px',
    backgroundColor: hexToSoft(props.color),
  }))

  /** 品牌色做 12% 透明底，暗色模式下不会糊成一片 */
  function hexToSoft(hex: string): string {
    const value = (hex || '#909399').replace('#', '')
    if (value.length !== 6) return 'rgba(144,147,153,0.12)'
    const r = parseInt(value.slice(0, 2), 16)
    const g = parseInt(value.slice(2, 4), 16)
    const b = parseInt(value.slice(4, 6), 16)
    return 'rgba(' + r + ',' + g + ',' + b + ',0.12)'
  }

  watch(
    () => [props.logoFile, props.logo],
    () => {
      imageFailed.value = false
      iconFailed.value = false
      watchIcon()
    }
  )

  onMounted(watchIcon)
  onUnmounted(() => {
    if (iconTimer) clearTimeout(iconTimer)
  })
</script>

<style scoped>
  .brand-avatar {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }

  .brand-img {
    width: 68%;
    height: 68%;
    object-fit: contain;
  }

</style>
