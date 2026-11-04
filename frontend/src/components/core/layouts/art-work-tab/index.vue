<!-- 标签页 -->
<template>
  <div
    v-if="showWorkTab"
    class="g-tabbar box-border flex-b w-full px-5 mb-3 select-none max-sm:px-[15px]"
    :class="[
      tabStyle === 'tab-card' ? 'py-1 border-b border-[var(--art-card-border)]' : '',
      tabStyle === 'tab-google' ? 'pt-1 pb-0 border-b border-[var(--art-card-border)]' : ''
    ]"
  >
    <div class="w-full overflow-hidden" ref="scrollRef">
      <ul
        class="float-left whitespace-nowrap !bg-transparent flex"
        :class="[tabStyle === 'tab-google' ? 'pl-1' : '']"
        ref="tabsRef"
        :style="{
          transform: `translateX(${scrollState.translateX}px)`,
          transition: `${scrollState.transition}`
        }"
      >
        <li
          v-for="(item, index) in list"
          :key="item.path"
          :ref="item.path"
          :id="`scroll-li-${index}`"
          class="work-tab"
          :class="[
            { 'is-active': item.path === activeTab },
            tabStyle === 'tab-google' ? 'google-tab' : ''
          ]"
          @click="clickTab(item)"
          @contextmenu.prevent="(e: MouseEvent) => showMenu(e, item.path)"
        >
          <ArtSvgIcon v-show="item.icon" :icon="item.icon" class="work-tab-icon" />
          <span class="work-tab-title">{{ item.customTitle || formatMenuTitle(item.title) }}</span>
          <span
            v-if="list.length > 1 && !item.fixedTab"
            class="work-tab-close"
            title="关闭"
            @click.stop="closeWorktab('current', item.path)"
          >
            <ArtSvgIcon icon="ri:close-large-fill" />
          </span>
        </li>
      </ul>
    </div>

    <div class="flex">
      <div class="work-tab-more" title="页签操作" @click="(e: MouseEvent) => showMenu(e, activeTab)">
        <ArtSvgIcon icon="iconamoon:arrow-down-2-thin" class="text-xl" />
      </div>
    </div>

    <ArtMenuRight
      ref="menuRef"
      :menu-items="menuItems"
      :menu-width="140"
      :border-radius="10"
      @select="handleSelect"
    />
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch, nextTick, onUnmounted } from 'vue'
  import { LocationQueryRaw, useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { storeToRefs } from 'pinia'

  import { useWorktabStore } from '@/store/modules/worktab'
  import { useUserStore } from '@/store/modules/user'
  import { formatMenuTitle } from '@/utils/router'
  import { useSettingStore } from '@/store/modules/setting'
  import { MenuItemType } from '../../others/art-menu-right/index.vue'
  import { useCommon } from '@/hooks/core/useCommon'
  import { WorkTab } from '@/types'

  defineOptions({ name: 'ArtWorkTab' })

  // 类型定义
  interface ScrollState {
    translateX: number
    transition: string
  }

  interface TouchState {
    startX: number
    currentX: number
  }

  type TabCloseType = 'current' | 'left' | 'right' | 'other' | 'all'

  // 基础设置
  const { t } = useI18n()
  const store = useWorktabStore()
  const userStore = useUserStore()
  const route = useRoute()
  const router = useRouter()
  const { currentRoute } = router
  const settingStore = useSettingStore()
  const { tabStyle, showWorkTab } = storeToRefs(settingStore)

  // DOM 引用
  const scrollRef = ref<HTMLElement | null>(null)
  const tabsRef = ref<HTMLElement | null>(null)
  const menuRef = ref()

  // 状态管理
  const scrollState = ref<ScrollState>({
    translateX: 0,
    transition: ''
  })

  const touchState = ref<TouchState>({
    startX: 0,
    currentX: 0
  })

  const clickedPath = ref('')

  // 计算属性
  const list = computed(() => store.opened)
  const activeTab = computed(() => currentRoute.value.path)
  const activeTabIndex = computed(() => list.value.findIndex((tab) => tab.path === activeTab.value))

  // 右键菜单逻辑
  const useContextMenu = () => {
    const getClickedTabInfo = () => {
      const clickedIndex = list.value.findIndex((tab) => tab.path === clickedPath.value)
      const currentTab = list.value[clickedIndex]

      return {
        clickedIndex,
        currentTab,
        isLastTab: clickedIndex === list.value.length - 1,
        isOneTab: list.value.length === 1,
        isCurrentTab: clickedPath.value === activeTab.value
      }
    }

    // 检查标签页是否固定
    const checkTabsFixedStatus = (clickedIndex: number) => {
      const leftTabs = list.value.slice(0, clickedIndex)
      const rightTabs = list.value.slice(clickedIndex + 1)
      const otherTabs = list.value.filter((_, index) => index !== clickedIndex)

      return {
        areAllLeftTabsFixed: leftTabs.length > 0 && leftTabs.every((tab) => tab.fixedTab),
        areAllRightTabsFixed: rightTabs.length > 0 && rightTabs.every((tab) => tab.fixedTab),
        areAllOtherTabsFixed: otherTabs.length > 0 && otherTabs.every((tab) => tab.fixedTab),
        areAllTabsFixed: list.value.every((tab) => tab.fixedTab)
      }
    }

    // 右键菜单选项
    const menuItems = computed(() => {
      const { clickedIndex, currentTab, isLastTab, isOneTab, isCurrentTab } = getClickedTabInfo()
      const fixedStatus = checkTabsFixedStatus(clickedIndex)

      return [
        {
          key: 'refresh',
          label: t('worktab.btn.refresh'),
          icon: 'ri:refresh-line',
          disabled: !isCurrentTab
        },
        {
          key: 'fixed',
          label: currentTab?.fixedTab ? t('worktab.btn.unfixed') : t('worktab.btn.fixed'),
          icon: 'ri:pushpin-2-line',
          disabled: false,
          showLine: true
        },
        {
          key: 'left',
          label: t('worktab.btn.closeLeft'),
          icon: 'ri:arrow-left-s-line',
          disabled: clickedIndex === 0 || fixedStatus.areAllLeftTabsFixed
        },
        {
          key: 'right',
          label: t('worktab.btn.closeRight'),
          icon: 'ri:arrow-right-s-line',
          disabled: isLastTab || fixedStatus.areAllRightTabsFixed
        },
        {
          key: 'other',
          label: t('worktab.btn.closeOther'),
          icon: 'ri:close-fill',
          disabled: isOneTab || fixedStatus.areAllOtherTabsFixed
        },
        {
          key: 'all',
          label: t('worktab.btn.closeAll'),
          icon: 'ri:close-circle-line',
          disabled: isOneTab || fixedStatus.areAllTabsFixed
        }
      ]
    })

    return { menuItems }
  }

  // 滚动逻辑
  const useScrolling = () => {
    const setTransition = () => {
      scrollState.value.transition = 'transform 0.5s cubic-bezier(0.15, 0, 0.15, 1)'
      setTimeout(() => {
        scrollState.value.transition = ''
      }, 250)
    }

    const getCurrentTabElement = (): HTMLElement | null => {
      return document.getElementById(`scroll-li-${activeTabIndex.value}`)
    }

    const calculateScrollPosition = () => {
      if (!scrollRef.value || !tabsRef.value) return

      const scrollWidth = scrollRef.value.offsetWidth
      const ulWidth = tabsRef.value.offsetWidth
      const curTabEl = getCurrentTabElement()

      if (!curTabEl) return

      const { offsetLeft, clientWidth } = curTabEl
      const curTabRight = offsetLeft + clientWidth
      const targetLeft = scrollWidth - curTabRight

      return {
        scrollWidth,
        ulWidth,
        offsetLeft,
        clientWidth,
        curTabRight,
        targetLeft
      }
    }

    const autoPositionTab = () => {
      const positions = calculateScrollPosition()
      if (!positions) return

      const { scrollWidth, ulWidth, offsetLeft, curTabRight, targetLeft } = positions

      if (
        (offsetLeft > Math.abs(scrollState.value.translateX) && curTabRight <= scrollWidth) ||
        (scrollState.value.translateX < targetLeft && targetLeft < 0)
      ) {
        return
      }

      requestAnimationFrame(() => {
        if (curTabRight > scrollWidth) {
          scrollState.value.translateX = Math.max(targetLeft - 6, scrollWidth - ulWidth)
        } else if (offsetLeft < Math.abs(scrollState.value.translateX)) {
          scrollState.value.translateX = -offsetLeft
        }
      })
    }

    const adjustPositionAfterClose = () => {
      const positions = calculateScrollPosition()
      if (!positions) return

      const { scrollWidth, ulWidth, offsetLeft, clientWidth } = positions
      const curTabLeft = offsetLeft + clientWidth

      requestAnimationFrame(() => {
        scrollState.value.translateX = curTabLeft > scrollWidth ? scrollWidth - ulWidth : 0
      })
    }

    return {
      setTransition,
      autoPositionTab,
      adjustPositionAfterClose
    }
  }

  // 事件处理逻辑
  const useEventHandlers = () => {
    const { setTransition, adjustPositionAfterClose } = useScrolling()

    const handleWheelScroll = (event: WheelEvent) => {
      if (!scrollRef.value || !tabsRef.value) return

      event.preventDefault()

      if (tabsRef.value.offsetWidth <= scrollRef.value.offsetWidth) return

      const xMax = 0
      const xMin = scrollRef.value.offsetWidth - tabsRef.value.offsetWidth
      const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY

      scrollState.value.translateX = Math.min(
        Math.max(scrollState.value.translateX - delta, xMin),
        xMax
      )
    }

    const handleTouchStart = (event: TouchEvent) => {
      touchState.value.startX = event.touches[0].clientX
    }

    const handleTouchMove = (event: TouchEvent) => {
      if (!scrollRef.value || !tabsRef.value) return

      touchState.value.currentX = event.touches[0].clientX
      const deltaX = touchState.value.currentX - touchState.value.startX
      const xMin = scrollRef.value.offsetWidth - tabsRef.value.offsetWidth

      scrollState.value.translateX = Math.min(
        Math.max(scrollState.value.translateX + deltaX, xMin),
        0
      )
      touchState.value.startX = touchState.value.currentX
    }

    const handleTouchEnd = () => {
      setTransition()
    }

    const setupEventListeners = () => {
      if (tabsRef.value) {
        tabsRef.value.addEventListener('wheel', handleWheelScroll, { passive: false })
        tabsRef.value.addEventListener('touchstart', handleTouchStart, { passive: true })
        tabsRef.value.addEventListener('touchmove', handleTouchMove, { passive: true })
        tabsRef.value.addEventListener('touchend', handleTouchEnd, { passive: true })
      }
    }

    const cleanupEventListeners = () => {
      if (tabsRef.value) {
        tabsRef.value.removeEventListener('wheel', handleWheelScroll)
        tabsRef.value.removeEventListener('touchstart', handleTouchStart)
        tabsRef.value.removeEventListener('touchmove', handleTouchMove)
        tabsRef.value.removeEventListener('touchend', handleTouchEnd)
      }
    }

    return {
      setupEventListeners,
      cleanupEventListeners,
      adjustPositionAfterClose
    }
  }

  // 标签页操作逻辑
  const useTabOperations = (adjustPositionAfterClose: () => void) => {
    const clickTab = (item: WorkTab) => {
      router.push({
        path: item.path,
        query: item.query as LocationQueryRaw
      })
    }

    const closeWorktab = (type: TabCloseType, tabPath: string) => {
      const path = typeof tabPath === 'string' ? tabPath : route.path

      const closeActions = {
        current: () => store.removeTab(path),
        left: () => store.removeLeft(path),
        right: () => store.removeRight(path),
        other: () => store.removeOthers(path),
        all: () => store.removeAll()
      }

      closeActions[type]?.()

      setTimeout(() => {
        adjustPositionAfterClose()
      }, 100)
    }

    const showMenu = (e: MouseEvent, path?: string) => {
      clickedPath.value = path || ''
      menuRef.value?.show(e)
      e.preventDefault()
      e.stopPropagation()
    }

    const handleSelect = (item: MenuItemType) => {
      const { key } = item

      if (key === 'refresh') {
        useCommon().refresh()
        return
      }

      if (key === 'fixed') {
        useWorktabStore().toggleFixedTab(clickedPath.value)
        return
      }

      const activeIndex = list.value.findIndex((tab) => tab.path === activeTab.value)
      const clickedIndex = list.value.findIndex((tab) => tab.path === clickedPath.value)

      const navigationRules = {
        left: activeIndex < clickedIndex,
        right: activeIndex > clickedIndex,
        other: true
      } as const

      const shouldNavigate = navigationRules[key as keyof typeof navigationRules]

      if (shouldNavigate) {
        router.push(clickedPath.value)
      }

      closeWorktab(key as TabCloseType, clickedPath.value)
    }

    return {
      clickTab,
      closeWorktab,
      showMenu,
      handleSelect
    }
  }

  // 组合所有逻辑
  const { menuItems } = useContextMenu()
  const { setTransition, autoPositionTab } = useScrolling()
  const { setupEventListeners, cleanupEventListeners, adjustPositionAfterClose } =
    useEventHandlers()
  const { clickTab, closeWorktab, showMenu, handleSelect } =
    useTabOperations(adjustPositionAfterClose)

  // 生命周期
  onMounted(() => {
    setupEventListeners()
    autoPositionTab()
  })

  onUnmounted(() => {
    cleanupEventListeners()
  })

  // 监听器
  watch(
    () => currentRoute.value,
    () => {
      setTransition()
      autoPositionTab()
    }
  )

  watch(
    () => userStore.language,
    () => {
      scrollState.value.translateX = 0
      nextTick(() => {
        autoPositionTab()
      })
    }
  )
</script>

<style scoped>
  /*
   * 页签条：shadcn 的胶囊（rounded-md + 选中白底 + 1px 描边 + sm 阴影）
   * ==================================================================
   * 这里只定义「单个页签」的形态；条的高度 / 背景 / 下边框在 shadcn-shell.scss。
   *
   * 两条不要碰的红线：
   * 1. 不要在 li 上写内联 border-radius（原来 `calc(var(--custom-radius) * 0.6) !important`
   *    会把圆角钉在 4.8px，全局令牌改成 6/8/10 都无效）；
   * 2. 不要再用 Tailwind 的 `!h-8` / `!border-none` 这类「带 !」的原子类 ——
   *    它们在 utilities 层里是 important，按 CSS 层叠规则会压过无层样式，
   *    连 shadcn-shell 的 `html .g-tabbar .google-tab` 都打不过。
   *    尺寸统一写在下面这条 `.work-tab` 里。
   */
  .work-tab {
    position: relative;
    display: inline-flex;
    flex: 0 0 auto;
    gap: 6px;
    align-items: center;
    height: 28px;
    padding: 0 6px 0 8px;
    margin-right: 4px;
    font-family: var(--font-sans);
    font-size: 12.5px;
    font-weight: 500;
    line-height: 1;
    color: var(--muted-foreground);
    cursor: pointer;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    transition:
      background-color 0.12s ease,
      color 0.12s ease,
      border-color 0.12s ease;
  }

  .work-tab:hover {
    color: var(--foreground);
    background: color-mix(in srgb, var(--foreground) 6%, transparent);
  }

  .work-tab.is-active {
    color: var(--foreground);
    background: var(--background);
    border-color: var(--border);
    box-shadow: var(--shadow-sm);
  }

  .work-tab-icon {
    flex: 0 0 auto;
    font-size: 14px;
    color: var(--muted-foreground);
  }

  .work-tab.is-active .work-tab-icon {
    color: var(--foreground);
  }

  .work-tab-title {
    max-width: 168px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /*
   * 关闭按钮：平时隐藏，hover / 激活才出现。
   * 屏幕上开了十来个页签时，十个常驻的 × 是最大的视觉噪音源。
   */
  .work-tab-close {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    margin-left: 2px;
    border-radius: var(--radius-sm);
    opacity: 0;
    transition:
      opacity 0.12s ease,
      background-color 0.12s ease;
  }

  .work-tab:hover .work-tab-close,
  .work-tab.is-active .work-tab-close {
    opacity: 1;
  }

  .work-tab-close:hover {
    background: color-mix(in srgb, var(--foreground) 10%, transparent);
  }

  .work-tab-close :deep(svg) {
    font-size: 11px;
    color: var(--muted-foreground);
  }

  .work-tab-close:hover :deep(svg) {
    color: var(--foreground);
  }

  /* 右侧「页签操作」按钮：和页签同高，ghost 形态 */
  .work-tab-more {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    color: var(--muted-foreground);
    cursor: pointer;
    border-radius: var(--radius-md);
    transition:
      color 0.12s ease,
      background-color 0.12s ease;
  }

  .work-tab-more:hover {
    color: var(--foreground);
    background: var(--accent);
  }
</style>
