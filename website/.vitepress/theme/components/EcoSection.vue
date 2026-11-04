<template>
  <section id="ecosystem" class="ch-section">
    <div class="ch-wrap">
      <div class="ch-sec-head">
        <span class="ch-tag">生态集成</span>
        <h2>兼容主流 CA、云厂商与平台</h2>
        <p>共 {{ total }} 项内置集成，全部 Logo 取自项目真实资源，无任何文字占位。</p>
      </div>

      <div class="ch-eco-group">
        <div class="ch-ca-head">
          <span class="ch-ca-eyebrow">TRUSTED CA BRANDS</span>
          <h3>汇聚主流 SSL 证书品牌</h3>
          <p>从国际通用 CA 到轻量免费方案，再到企业私有 CA，一个控制台即可按需申请、统一续期。</p>
        </div>
        <div class="ch-ca-grid">
          <div v-for="c in CAS" :key="c.name" class="ch-ca-card">
            <img :src="c.logo" :alt="c.name + ' Logo'" loading="lazy" />
            <span class="ch-ca-name">{{ c.name }}</span>
            <span class="ch-ca-desc">{{ c.desc }}</span>
          </div>
        </div>
        <p class="ch-ca-note">以上商标及标识归其各自所有者所有，仅用于标示可在本平台申请的证书品牌。</p>
      </div>

      <div class="ch-eco-divider">部署与集成能力</div>

      <div v-for="g in ECO_GROUPS" :key="g.title" class="ch-eco-group">
        <div class="ch-eco-title">
          {{ g.title }}<span class="count">{{ g.items.length }} 项</span>
        </div>
        <div class="ch-eco-grid">
          <div v-for="it in g.items" :key="it.name" class="ch-eco-item">
            <img :src="it.logo" :alt="it.name + ' Logo'" loading="lazy" />
            <span class="n">{{ it.name }}</span>
          </div>
        </div>
      </div>

      <p class="ch-ca-note">
        完整清单（{{ deployCount }} 个部署插件、{{ certCount }} 种签发来源）见
        <a href="/ecosystem.html">生态集成</a> 页。
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { CAS, CERT_SOURCES, DEPLOY_GROUPS, ECO_GROUPS } from '../../data/ecosystem'

const total = CAS.length + ECO_GROUPS.reduce((n, g) => n + g.items.length, 0)
const deployCount = DEPLOY_GROUPS.reduce((n, g) => n + g.items.length, 0)
const certCount = CERT_SOURCES.length
</script>
