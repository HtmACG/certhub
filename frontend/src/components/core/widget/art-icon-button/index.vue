<!-- 按钮组件 -->
<!--
  shadcn 的 ghost icon button：32px 方块 / 8px 圆角 / muted 图标，
  hover 出 accent 底 + foreground 图标。
  原来是 34px + 4px 圆角 + text-xl 的图标，和表格里的 ArtButtonTable（32px / 8px）
  对不齐 —— 同一行出现两种尺寸，视觉上就是参差不齐。
-->
<template>
  <div
    class="size-8 inline-flex flex-cc c-p text-base text-g-600 rounded-md tad-300 hover:bg-hover-color hover:text-g-900"
    :class="{ 'rounded-full': circle }"
  >
    <ArtSvgIcon :icon="icon"></ArtSvgIcon>
    <slot></slot>
  </div>
</template>

<script lang="ts" setup>
  defineOptions({ name: 'ArtIconButton' })

  interface Props {
    /** 图标名称 */
    icon: string
    /** 圆角按钮 */
    circle?: boolean
  }

  withDefaults(defineProps<Props>(), {})
</script>
