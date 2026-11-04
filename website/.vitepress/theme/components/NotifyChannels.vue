<template>
  <div class="nc">
    <span v-for="n in NOTIFY_CHANNELS" :key="n" class="nc-chip">{{ n }}</span>
  </div>
</template>

<script setup lang="ts">
import { NOTIFY_CHANNELS } from '../../data/ecosystem'
</script>

<style scoped>
.nc {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.nc-chip {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 7px;
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-alt);
  font-size: 13px;
  color: var(--vp-c-text-2);
}
</style>
