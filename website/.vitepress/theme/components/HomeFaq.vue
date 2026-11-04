<template>
  <section id="faq" class="ch-section">
    <div class="ch-wrap">
      <div class="ch-sec-head">
        <span class="ch-tag">常见问题</span>
        <h2>你可能想了解的问题</h2>
        <p>更多细节见 <a href="/faq.html">完整问答</a> 与 <a href="/docs/">帮助文档</a>。</p>
      </div>
      <div class="ch-faq-list">
        <details v-for="(f, i) in FAQS" :key="f.q" class="ch-faq-item">
          <summary class="ch-faq-q">
            <span class="no">{{ String(i + 1).padStart(2, '0') }}</span>
            <span>{{ f.q }}</span>
            <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
          </summary>
          <div class="ch-faq-a">{{ f.a }}</div>
        </details>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const FAQS = [
  {
    q: 'CertHub 真的完全免费吗？',
    a: '是的。CertHub 完全免费，无任何付费、授权或套餐模块，不含流水线数量、站点监控数量、通知渠道等任何限制，可自由私有化部署。'
  },
  {
    q: '支持哪些证书颁发机构？',
    a: '通过 ACME 协议对接 Let\u2019s Encrypt、Google Trust Services、ZeroSSL、Buypass、FreeSSL / LiteSSL 等机构，同时支持阿里云、腾讯云、火山引擎、TrustAsia 的免费或商业证书，以及本地自签与自有证书导入。'
  },
  {
    q: '证书可以部署到哪些地方？',
    a: '内置 75 个部署插件，覆盖 Nginx、Apache、Tomcat、HAProxy、IIS 等主机，宝塔、1Panel、群晖、Proxmox、雷池等面板，Kubernetes，以及各类云 CDN、对象存储与负载均衡，并支持自定义 Webhook。'
  },
  {
    q: '凭据和私钥安全吗？',
    a: '凭据与证书私钥在数据库中 AES-GCM 加密存储，界面上的密码框默认星号、点「小眼睛」才显示明文（便于排障，因此数据库与备份文件本身要当机密文件对待）。另外支持登录失败锁定、TOTP 两步验证与审计日志。'
  },
  {
    q: '如何快速安装部署？',
    a: 'Windows 双击 start.bat、Linux/macOS 执行 start.sh，脚本会自动创建虚拟环境、安装依赖、构建前端并启动服务，随后访问 http://127.0.0.1:8000，默认管理员账号为 admin / 123456（首次登录请立即改密码）。'
  },
  {
    q: '支持泛域名和 HTTP 验证吗？',
    a: '支持。泛域名证书必须使用 DNS-01 验证，需要在「授权管理」里配一个 DNS 服务商授权；单域名可以用 HTTP-01 文件验证，要求站点 80 端口可从公网访问。'
  }
]
</script>
