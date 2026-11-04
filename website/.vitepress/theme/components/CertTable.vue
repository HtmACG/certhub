<template>
  <div class="ct-wrap">
    <table class="ct">
      <thead>
        <tr>
          <th>来源</th>
          <th>类型</th>
          <th>有效期</th>
          <th>验证方式</th>
          <th>标签</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in CERT_SOURCES" :key="c.name">
          <td><strong>{{ c.name }}</strong></td>
          <td>{{ c.kind }}</td>
          <td>{{ c.validity }}</td>
          <td>{{ c.challenge }}</td>
          <td>
            <span v-for="t in c.tags" :key="t" class="ct-tag">{{ t }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { CERT_SOURCES } from '../../data/ecosystem'
</script>

<style scoped>
.ct-wrap {
  overflow-x: auto;
}

.ct {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.ct th,
.ct td {
  border: 1px solid var(--vp-c-divider);
  padding: 9px 12px;
  text-align: left;
  vertical-align: top;
}

.ct th {
  background: var(--vp-c-bg-alt);
  font-weight: 600;
  white-space: nowrap;
}

.ct-tag {
  display: inline-block;
  margin: 1px 4px 1px 0;
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-size: 11.5px;
  line-height: 1.7;
  white-space: nowrap;
}
</style>
