<template>
  <div class="pg">
    <div v-for="g in DEPLOY_GROUPS" :key="g.name" class="pg-group">
      <div class="pg-title">
        {{ g.name }}<span class="pg-count">{{ g.items.length }} 个</span>
      </div>
      <div class="pg-chips">
        <span v-for="n in g.items" :key="n" class="pg-chip">{{ n }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { DEPLOY_GROUPS } from '../../data/ecosystem'
</script>

<style scoped>
.pg-group {
  margin-bottom: 26px;
}

.pg-group:last-child {
  margin-bottom: 0;
}

.pg-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--vp-c-text-1);
  margin-bottom: 12px;
}

.pg-title::before {
  content: '';
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--vp-c-brand-1);
}

.pg-count {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--vp-c-text-3);
}

.pg-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pg-chip {
  display: inline-block;
  padding: 5px 11px;
  border-radius: 7px;
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-alt);
  font-size: 12.5px;
  color: var(--vp-c-text-2);
  line-height: 1.5;
}
</style>
