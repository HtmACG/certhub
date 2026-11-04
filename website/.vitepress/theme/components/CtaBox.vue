<template>
  <section class="ch-cta">
    <div class="ch-wrap">
      <div class="ch-cta-box">
        <span class="ch-tag">立即开始</span>
        <h2>现在开始，让证书管理自动化</h2>
        <p>一键脚本启动，几分钟即可拥有完整的证书自动化平台。</p>
        <div class="ch-actions">
          <a class="ch-btn ch-btn-primary ch-btn-lg" :href="repo" target="_blank" rel="noopener">免费下载部署</a>
          <a class="ch-btn ch-btn-outline ch-btn-lg" href="/docs/install.html">阅读安装文档</a>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const repo = 'https://github.com/HtmACG/certhub'
</script>
