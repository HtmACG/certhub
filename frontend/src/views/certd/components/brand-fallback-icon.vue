<!--
  品牌图标兜底（内联 SVG）
  =========================================================
  以前 logo 都拿不到时画一块「品牌色底 + 首字母」的文字牌，用户反馈
  「文字图标不好看」。这里改成按类型给一个近似的矢量图标：

  - 内联 SVG（stroke=currentColor）：不依赖 Iconify 网络，离线也画得出来；
  - 颜色由外层 color 控制，跟主题 / 品牌色都合得上；
  - 尺寸由外层容器决定（默认铺满）。

  kind 由 brand-avatar 按名称关键词推断，见 brand-avatar.vue 的 KIND_RULES。
-->
<template>
  <svg
    class="brand-fallback-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 云 / CDN / 对象存储 -->
    <template v-if="kind === 'cloud'">
      <path d="M7.5 18.5h8.6a3.9 3.9 0 0 0 .4-7.8A5.9 5.9 0 0 0 5.6 11a3.75 3.75 0 0 0 1.9 7.5Z" />
      <path d="M12 11v12" opacity="0" />
    </template>

    <!-- 面板 / 容器面板 / NAS -->
    <template v-else-if="kind === 'panel'">
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M3 9h18" />
      <path d="M9 9v11" />
    </template>

    <!-- 主机 / 服务器 / SSH -->
    <template v-else-if="kind === 'host'">
      <rect x="3.5" y="4" width="17" height="6.5" rx="2" />
      <rect x="3.5" y="13.5" width="17" height="6.5" rx="2" />
      <path d="M7 7.25h.01M7 16.75h.01" />
    </template>

    <!-- 证书 / ACM / SSL -->
    <template v-else-if="kind === 'cert'">
      <path d="M6 3.5h8.5L19 8v10.5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2Z" />
      <path d="M14 3.5V8h4.5" />
      <path d="m9.6 13.8 1.7 1.7 3.3-3.4" />
    </template>

    <!-- 通知 / 邮件 -->
    <template v-else-if="kind === 'notify'">
      <path d="M6 9.5a6 6 0 0 1 12 0c0 3.2.7 5 1.6 6.2.4.6 0 1.3-.7 1.3H5.1c-.8 0-1.1-.7-.7-1.3.9-1.2 1.6-3 1.6-6.2Z" />
      <path d="M10 20a2.2 2.2 0 0 0 4 0" />
    </template>

    <!-- 脚本 / 命令 / 等待这类运维动作 -->
    <template v-else-if="kind === 'script'">
      <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" />
      <path d="m7 10 2.5 2.5L7 15" />
      <path d="M12.5 15.5h4.5" />
    </template>

    <!-- 通用（一个都不匹配时） -->
    <template v-else>
      <path d="M12 3.5 20.5 8v8L12 20.5 3.5 16V8Z" />
      <path d="M3.5 8 12 12.5 20.5 8" />
      <path d="M12 12.5v8" />
    </template>
  </svg>
</template>

<script setup lang="ts">
  defineOptions({ name: 'BrandFallbackIcon' })

  interface Props {
    /** 图标类别：cloud / panel / host / cert / notify / script / generic */
    kind?: string
  }

  withDefaults(defineProps<Props>(), { kind: 'generic' })
</script>

<style scoped>
  .brand-fallback-icon {
    width: 60%;
    height: 60%;
  }
</style>
