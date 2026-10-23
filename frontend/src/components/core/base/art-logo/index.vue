<!--
  系统 Logo
  =========================================================
  系统设置 → 站点信息里填了 Logo（图片地址或上传后的内联图）就用它，
  没填（或填的地址加载失败）退回内置图标，不会出现空白块。
-->
<template>
  <div class="flex-cc">
    <img
      :src="logoSrc"
      :style="logoStyle"
      alt="logo"
      class="h-full w-full object-contain"
      @error="onError"
    />
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import defaultLogo from '@imgs/common/logo.webp'
  import { useSiteStore } from '@/store/modules/site'

  defineOptions({ name: 'ArtLogo' })

  interface Props {
    /** logo 大小 */
    size?: number | string
  }

  const props = withDefaults(defineProps<Props>(), {
    size: 36
  })

  const siteStore = useSiteStore()

  // 自定义 logo 加载失败标记
  const broken = ref(false)

  const logoStyle = computed(() => ({ width: `${props.size}px` }))

  const logoSrc = computed(() => {
    const custom = siteStore.logoUrl
    return custom && !broken.value ? custom : defaultLogo
  })

  /**
   * 地址写错 / 外网图挂了就退回内置图标
   */
  const onError = (): void => {
    if (siteStore.logoUrl) broken.value = true
  }

  watch(
    () => siteStore.logoUrl,
    () => {
      broken.value = false
    }
  )

  onMounted(() => {
    siteStore.ensureLoaded()
  })
</script>
