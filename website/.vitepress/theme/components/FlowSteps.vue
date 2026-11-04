<template>
  <section id="flow" class="ch-section ch-flow">
    <div class="ch-wrap">
      <div class="ch-sec-head">
        <span class="ch-tag">工作流程</span>
        <h2>五步开启证书自动化</h2>
        <p>配置一次，证书自动流转、到期自动续期。</p>
      </div>
      <div class="ch-flow-track">
        <div class="ch-flow-line"></div>
        <div v-for="(s, i) in STEPS" :key="s.title" class="ch-flow-step">
          <div class="ch-flow-icon">{{ String(i + 1).padStart(2, '0') }}</div>
          <h4>{{ s.title }}</h4>
          <p>{{ s.desc }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const STEPS = [
  { title: '配置授权', desc: '填入云厂商、DNS 或主机凭据，AES-GCM 加密存储。' },
  { title: '创建流水线', desc: '从内置模板开始，选择 CA、域名与部署目标。' },
  { title: '自动验证', desc: '自动写入 DNS / HTTP 验证记录并等待生效。' },
  { title: '签发部署', desc: '获取证书链，自动下发到目标并重载服务。' },
  { title: '监控续期', desc: '到期前自动续期，多渠道通知，永不过期。' }
]
</script>
