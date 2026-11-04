<template>
  <section class="ch-stats">
    <div class="ch-wrap">
      <div class="ch-stats-grid">
        <div v-for="s in STATS" :key="s.label" class="ch-stat">
          <div class="num"><em>{{ s.num }}</em>{{ s.suffix }}</div>
          <div class="lab">{{ s.label }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { STATS } from '../../data/ecosystem'
</script>
