<template>
  <div class="at">
    <div v-for="g in ACCESS_TYPES" :key="g.category" class="at-group">
      <div class="at-title">
        {{ g.category }}<span class="at-count">{{ g.items.length }} 种</span>
      </div>
      <div class="at-chips">
        <span v-for="n in g.items" :key="n" class="at-chip">{{ n }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ACCESS_TYPES } from '../../data/ecosystem'
</script>

<style scoped>
.at-group {
  margin-bottom: 24px;
}

.at-group:last-child {
  margin-bottom: 0;
}

.at-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 12px;
}

.at-title::before {
  content: '';
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--vp-c-brand-1);
}

.at-count {
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--vp-c-text-3);
}

.at-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.at-chip {
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
