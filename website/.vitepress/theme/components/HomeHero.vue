<template>
  <header class="ch-hero">
    <div class="ch-wrap">
      <span class="ch-hero-badge">
        <span class="dot"></span>完全免费 · 无套餐、无数量限制
      </span>
      <h1>SSL 证书，<span class="ch-accent">自动签发、自动部署、自动续期</span></h1>
      <p class="ch-lead">
        CertHub 把证书申请、DNS 验证、部署与续期编排成一条可视化流水线。
        支持 Let's Encrypt 等主流 CA 与 {{ deployCount }} 个部署目标，流水线、站点、通知数量均无任何限制。
      </p>
      <div class="ch-actions">
        <a class="ch-btn ch-btn-primary ch-btn-lg" :href="repo" target="_blank" rel="noopener">一键免费开始</a>
        <a class="ch-btn ch-btn-outline ch-btn-lg" href="#demo">查看产品演示</a>
      </div>
      <div class="ch-meta">
        <span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
          永久免费无套餐
        </span>
        <span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
          流水线数量不限
        </span>
        <span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
          支持私有化部署
        </span>
      </div>

      <div class="ch-shot">
        <div class="ch-browser-bar">
          <i></i><i></i><i></i>
          <div class="ch-browser-url">http://127.0.0.1:8000/#/</div>
        </div>
        <img src="/assets/shots/dashboard.png" alt="CertHub 工作台真实界面" width="1080" height="674" />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { DEPLOY_GROUPS } from '../../data/ecosystem'

const repo = 'https://github.com/HtmACG/certhub'
const deployCount = DEPLOY_GROUPS.reduce((n, g) => n + g.items.length, 0)
</script>
