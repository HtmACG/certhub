<template>
  <section id="demo" class="ch-section ch-section-alt">
    <div class="ch-wrap">
      <div class="ch-sec-head">
        <span class="ch-tag">产品演示</span>
        <h2>真实界面，所见即所得</h2>
        <p>以下均为 CertHub 实际运行界面，点击标签查看不同模块。</p>
      </div>

      <div class="ch-demo">
        <div class="ch-demo-tabs" role="tablist">
          <button
            v-for="(d, i) in DEMOS"
            :key="d.key"
            type="button"
            role="tab"
            :aria-selected="active === i"
            class="ch-demo-tab"
            :class="{ active: active === i }"
            @click="active = i"
          >
            <span class="no">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="t">{{ d.title }}</span>
          </button>
        </div>

        <div class="ch-demo-stage">
          <div class="ch-browser-bar">
            <i></i><i></i><i></i>
            <div class="ch-browser-url">{{ DEMOS[active].url }}</div>
          </div>
          <div class="ch-demo-img">
            <img :src="DEMOS[active].img" :alt="DEMOS[active].title + '界面'" />
          </div>
          <div class="ch-demo-caption">{{ DEMOS[active].caption }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const DEMOS = [
  {
    key: 'dashboard',
    title: '工作台',
    img: '/assets/shots/dashboard.png',
    url: 'http://127.0.0.1:8000/#/',
    caption: '工作台：一屏掌握流水线、有效证书、运行成功率与站点状态，主机资源实时可见。'
  },
  {
    key: 'pipelines',
    title: '流水线列表',
    img: '/assets/shots/pipelines.png',
    url: 'http://127.0.0.1:8000/#/pipelines',
    caption: '流水线列表：阶段 / 步骤、最近运行、下次运行与启停状态一眼看清，支持批量运行与批量改定时。'
  },
  {
    key: 'canvas',
    title: '流水线画布',
    img: '/assets/shots/canvas.png',
    url: 'http://127.0.0.1:8000/#/pipelines/5',
    caption: '流水线画布：阶段与任务卡片节点化，连线即执行顺序，绿色为成功走向、橙色虚线为失败后跳转。'
  },
  {
    key: 'access',
    title: '授权管理',
    img: '/assets/shots/access.png',
    url: 'http://127.0.0.1:8000/#/access',
    caption: '授权管理：DNS、面板、主机与云厂商凭据统一入库，按类型校验，支持一键测试连通性。'
  },
  {
    key: 'monitor',
    title: '站点监控',
    img: '/assets/shots/monitor.png',
    url: 'http://127.0.0.1:8000/#/monitor',
    caption: '站点监控：定时巡检对端证书，状态、签发者、到期时间与剩余天数一目了然，异常站点自动告警。'
  },
  {
    key: 'cert',
    title: '证书详情',
    img: '/assets/shots/cert.png',
    url: 'http://127.0.0.1:8000/#/certs',
    caption: '证书详情：证书、证书链、私钥分标签查看，可导出 PEM / DER / PFX / P7B / JKS 等格式。'
  }
]

const active = ref(0)
</script>
