<template>
  <!--
    分组标题：shadcn 的小节标题形态 —— 13px / 500 / foreground，
    右侧拖一条 1px 分隔线，不做「两条线夹住居中文字」的装饰。
  -->
  <div class="section-title" :style="style">
    <span>{{ title }}</span>
    <span class="section-title__line" />
  </div>
</template>

<script setup lang="ts">
  interface Props {
    title: string
    style?: Record<string, any>
  }

  defineProps<Props>()
</script>

<style scoped>
  .section-title {
    display: flex;
    gap: 10px;
    align-items: center;
    margin: 24px 0 12px;
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 500;
    line-height: 1.4;
    color: var(--foreground);
  }

  .section-title__line {
    flex: 1;
    height: 1px;
    background: var(--border);
  }
</style>
