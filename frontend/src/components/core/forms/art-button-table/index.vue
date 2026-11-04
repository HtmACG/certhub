<!-- 表格按钮 -->
<!--
  shadcn 规范：表格行内操作用「ghost icon button」——
  32px 方块、8px 圆角、透明底，默认 muted 图标，悬停出现 accent 底。
  不再给图标铺一层彩色软底（bg-info/12 那种），一列里出现三种色块就花了；
  只有 delete 保留 destructive 前景色，作为唯一的高危提示。
-->
<template>
  <div
    :class="[
      'art-table-btn inline-flex items-center justify-center size-8 text-sm c-p rounded-lg align-middle',
      buttonClass
    ]"
    :style="{ backgroundColor: buttonBgColor, color: iconColor }"
    @click="handleClick"
  >
    <ArtSvgIcon :icon="iconContent" />
  </div>
</template>

<script setup lang="ts">
  defineOptions({ name: 'ArtButtonTable' })

  interface Props {
    /** 按钮类型 */
    type?: 'add' | 'edit' | 'delete' | 'more' | 'view'
    /** 按钮图标 */
    icon?: string
    /** 按钮样式类 */
    iconClass?: string
    /** icon 颜色 */
    iconColor?: string
    /** 按钮背景色 */
    buttonBgColor?: string
  }

  const props = withDefaults(defineProps<Props>(), {})

  const emit = defineEmits<{
    (e: 'click'): void
  }>()

  // 默认按钮配置（颜色全部走语义令牌：muted 图标 / accent 悬停底 / destructive 危险）
  const defaultButtons = {
    add: { icon: 'ri:add-fill', class: 'is-ghost' },
    edit: { icon: 'ri:pencil-line', class: 'is-ghost' },
    delete: { icon: 'ri:delete-bin-5-line', class: 'is-ghost is-danger' },
    view: { icon: 'ri:eye-line', class: 'is-ghost' },
    more: { icon: 'ri:more-2-fill', class: 'is-ghost' }
  } as const

  // 获取图标内容
  const iconContent = computed(() => {
    return props.icon || (props.type ? defaultButtons[props.type]?.icon : '') || ''
  })

  // 获取按钮样式类
  const buttonClass = computed(() => {
    return props.iconClass || (props.type ? defaultButtons[props.type]?.class : '') || ''
  })

  const handleClick = () => {
    emit('click')
  }
</script>
