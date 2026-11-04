<template>
  <section id="features" class="ch-section">
    <div class="ch-wrap">
      <div class="ch-sec-head">
        <span class="ch-tag">核心能力</span>
        <h2>覆盖证书自动化的每个环节</h2>
        <p>从签发、部署到监控续期，一套平台完成证书全生命周期管理。</p>
      </div>
      <div class="ch-feats">
        <div v-for="f in FEATURES" :key="f.title" class="ch-feat">
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const FEATURES = [
  {
    title: 'ACME 全自动签发',
    desc: '自研 ACME v2 客户端，支持 DNS-01 / HTTP-01 挑战与 EAB，对接 Let\u2019s Encrypt、Google Trust Services、ZeroSSL、Buypass、LiteSSL 等机构。'
  },
  {
    title: '云厂商免费证书',
    desc: '内置阿里云、腾讯云、火山引擎与 TrustAsia 免费证书申请，自动完成 DNS 验证与签发，无需登录各家控制台。'
  },
  {
    title: '可视化流水线',
    desc: '阶段与任务以卡片节点呈现，拖拽连线即可编排，支持定时触发、失败后跳转、批量运行与流水线分组。'
  },
  {
    title: '75 个部署目标',
    desc: '覆盖 Nginx、Apache、Tomcat、IIS、宝塔、群晖、Kubernetes、云 CDN 与对象存储，签发后一键下发并自动重载。'
  },
  {
    title: '实时签发日志',
    desc: '基于 SSE 的逐行实时日志，词法高亮、阶段标色，点击运行即刻可见，历史记录同样可完整回放。'
  },
  {
    title: '监控、续期与安全',
    desc: '持续巡检站点证书、到期自动续期、10 种通知渠道；凭据 AES-GCM 加密存储，支持登录锁定、TOTP 两步验证与审计日志。'
  }
]
</script>
