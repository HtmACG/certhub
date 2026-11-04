<!-- 顶部快速入口面板 -->
<template>
  <ElPopover
    ref="popoverRef"
    :width="700"
    :offset="0"
    :show-arrow="false"
    trigger="hover"
    placement="bottom-start"
    popper-class="fast-enter-popover"
    :popper-style="{
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)'
    }"
  >
    <template #reference>
      <div class="flex-c gap-2">
        <slot />
      </div>
    </template>

    <div class="grid grid-cols-[2fr_0.8fr]">
      <div>
        <div class="grid grid-cols-2 gap-1.5">
          <!-- 应用列表：图标统一中性灰（hover 才到 foreground），不给每个入口配一个高饱和色 -->
          <div
            v-for="application in enabledApplications"
            :key="application.name"
            class="mr-3 c-p flex-c gap-3 rounded-md p-2 hover:bg-hover-color hover:[&_.app-icon]:!text-g-900"
            @click="handleApplicationClick(application)"
          >
            <div
              class="app-icon size-12 flex-cc rounded-md bg-g-200/70 text-g-600 transition-colors"
            >
              <ArtSvgIcon class="text-xl" :icon="application.icon" />
            </div>
            <div>
              <h3 class="m-0 text-sm font-medium text-g-900">{{ application.name }}</h3>
              <p class="mt-1 text-xs text-g-600">{{ application.description }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="border-l-d pl-6 pt-2">
        <h3 class="mb-2.5 text-base font-medium text-g-900">快速链接</h3>
        <ul>
          <li
            v-for="quickLink in enabledQuickLinks"
            :key="quickLink.name"
            class="c-p py-2 hover:[&_span]:text-g-900"
            @click="handleQuickLinkClick(quickLink)"
          >
            <span class="text-g-600 no-underline transition-colors">{{ quickLink.name }}</span>
          </li>
        </ul>
      </div>
    </div>
  </ElPopover>
</template>

<script setup lang="ts">
  import { useFastEnter } from '@/hooks/core/useFastEnter'
  import type { FastEnterApplication, FastEnterQuickLink } from '@/types/config'

  defineOptions({ name: 'ArtFastEnter' })

  const router = useRouter()
  const popoverRef = ref()

  // 使用快速入口配置
  const { enabledApplications, enabledQuickLinks } = useFastEnter()

  /**
   * 处理导航跳转
   * @param routeName 路由名称
   * @param link 外部链接
   */
  const handleNavigate = (routeName?: string, link?: string): void => {
    const targetPath = routeName || link

    if (!targetPath) {
      console.warn('导航配置无效：缺少路由名称或链接')
      return
    }

    if (targetPath.startsWith('http')) {
      window.open(targetPath, '_blank')
    } else {
      router.push({ name: targetPath })
    }

    popoverRef.value?.hide()
  }

  /**
   * 处理应用项点击
   * @param application 应用配置对象
   */
  const handleApplicationClick = (application: FastEnterApplication): void => {
    handleNavigate(application.routeName, application.link)
  }

  /**
   * 处理快速链接点击
   * @param quickLink 快速链接配置对象
   */
  const handleQuickLinkClick = (quickLink: FastEnterQuickLink): void => {
    handleNavigate(quickLink.routeName, quickLink.link)
  }
</script>
