<!--
  工作台
  =========================================================
  结构按「上面一块简约看板 + 中间三个仪表 + 下面四个列表」来：

  1. 顶部看板：一行文字 + 4 个数字 + 3 个快捷动作，不做大标题、不堆卡片；
  2. 中部「系统信息」：CPU / 内存 / 系统盘三个车速表仪表（ArtGaugeChart），
     硬盘只展示系统盘，数据盘不铺在这里；每 5 秒自动刷新一次读数；
  3. 下面只有四个列表：流水线 / 执行记录 / 证书 / 监控站点，
     每张卡只放最近 5 条，「查看全部」跳对应页面。

  趋势图、签发机构分布、能力总览这类"看板式"内容已经去掉 ——
  工作台的定位是"扫一眼现状、点进去处理"，不是报表。
-->
<template>
  <div class="certd-dashboard g-scope" v-loading="loading">
    <!-- ① 页头：一行标题 + 一行数据摘要 + 右侧动作。
         不做成卡片：内容区已经是浅灰底，再套一个白盒子会变成「盒子叠盒子」。 -->
    <div class="dash-head">
      <div class="dash-head-main">
        <h1 class="dash-title">
          {{ greeting }}，{{ userName }}
          <!-- 昵称本身就是「管理员」时不再重复显示角色 -->
          <span v-if="isAdmin && userName !== adminLabel" class="dash-role">{{
            $t('certd.dashboard.admin')
          }}</span>
        </h1>
        <p class="dash-sub">
          <span class="dash-stat" @click="go('/certd/pipeline')">
            {{ $t('certd.dashboard.statPipeline') }} <b>{{ stats.pipelineTotal || 0 }}</b>
          </span>
          <span class="dash-sep">·</span>
          <span class="dash-stat" @click="go('/certd/cert')">
            {{ $t('certd.dashboard.statCert') }} <b>{{ stats.certTotal || 0 }}</b>
          </span>
          <span class="dash-sep">·</span>
          <span
            class="dash-stat"
            :class="{ 'is-warn': stats.certExpiring > 0 }"
            @click="go('/certd/cert', { expiring: 1 })"
          >
            {{ $t('certd.dashboard.statExpiring') }} <b>{{ stats.certExpiring || 0 }}</b>
          </span>
          <span class="dash-sep">·</span>
          <span class="dash-stat" @click="go('/certd/monitor')">
            {{ $t('certd.dashboard.statSite') }} <b>{{ stats.siteTotal || 0 }}</b>
          </span>
        </p>
      </div>
      <div class="dash-actions">
        <ElButton type="primary" @click="go('/certd/pipeline', { create: 'template' })">
          <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.dashboard.newPipeline') }}
        </ElButton>
        <ElButton @click="go('/certd/cert', { import: 1 })">
          <ArtSvgIcon icon="ri:upload-2-line" class="mr-1" />{{ $t('certd.dashboard.importCert') }}
        </ElButton>
        <ElButton @click="go('/certd/access', { create: 1 })">
          <ArtSvgIcon icon="ri:key-2-line" class="mr-1" />{{ $t('certd.dashboard.addAccess') }}
        </ElButton>
      </div>
    </div>

    <!-- ② 系统信息看板：CPU / 内存 / 系统盘使用率，三个车速表仪表 -->
    <ElCard v-if="hasSystemInfo" class="art-card system-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title"
            ><ArtSvgIcon icon="ri:server-line" />{{ $t('certd.dashboard.systemInfo') }}</span
          >
          <span class="card-count">{{ sys.hostname }}</span>
          <ElTooltip
            :content="
              systemLoading ? $t('certd.dashboard.refreshing') : $t('certd.dashboard.refreshSystem')
            "
            placement="top"
          >
            <ElButton link :loading="systemLoading" @click="loadSystemInfo">
              <ArtSvgIcon icon="ri:refresh-line" />
            </ElButton>
          </ElTooltip>
        </div>
      </template>

      <!-- 三个车速表：CPU / 内存 / 系统盘（只展示系统盘，数据盘不铺在这里） -->
      <div class="sys-grid">
        <!-- CPU -->
        <div class="sys-col">
          <div class="sys-head">
            <ArtSvgIcon icon="ri:cpu-line" class="sys-icon" />
            <span class="sys-name">{{ $t('certd.dashboard.cpuUsage') }}</span>
            <span class="sys-state" :style="{ color: usageColor(sys.cpu.percent) }">
              {{ usageText(sys.cpu.percent) }}
            </span>
          </div>
          <ArtGaugeChart :value="Number(sys.cpu.percent) || 0" :height="gaugeHeight" />
          <div class="sys-detail is-center" :title="sys.cpu.name">
            {{
              $t('certd.dashboard.coresThreads', {
                cores: sys.cpu.coresPhysical,
                threads: sys.cpu.coresLogical,
              })
            }}
            <template v-if="sys.cpu.freqMhz"> · {{ (sys.cpu.freqMhz / 1000).toFixed(1) }} GHz</template>
          </div>
        </div>

        <!-- 内存 -->
        <div class="sys-col">
          <div class="sys-head">
            <ArtSvgIcon icon="ri:database-2-line" class="sys-icon" />
            <span class="sys-name">{{ $t('certd.dashboard.memoryUsage') }}</span>
            <span class="sys-state" :style="{ color: usageColor(sys.memory.percent) }">
              {{ usageText(sys.memory.percent) }}
            </span>
          </div>
          <ArtGaugeChart :value="Number(sys.memory.percent) || 0" :height="gaugeHeight" />
          <div class="sys-detail is-center">
            {{
              $t('certd.dashboard.memoryDetail', {
                used: formatBytes(sys.memory.used),
                total: formatBytes(sys.memory.total),
              })
            }}
          </div>
          <div v-if="sys.swap.total" class="sys-detail is-center">
            {{
              $t('certd.dashboard.swapDetail', {
                percent: sys.swap.percent,
                used: formatBytes(sys.swap.used),
                total: formatBytes(sys.swap.total),
              })
            }}
          </div>
        </div>

        <!-- 系统盘：只展示系统盘（Windows 是系统所在盘符，Linux 是 /） -->
        <div class="sys-col">
          <div class="sys-head">
            <ArtSvgIcon icon="ri:hard-drive-2-line" class="sys-icon" />
            <span class="sys-name">{{ $t('certd.dashboard.diskUsage') }}</span>
            <span v-if="systemDisk" class="sys-state" :style="{ color: usageColor(systemDisk.percent) }">
              {{ usageText(systemDisk.percent) }}
            </span>
          </div>
          <template v-if="systemDisk">
            <ArtGaugeChart :value="Number(systemDisk.percent) || 0" :height="gaugeHeight" />
            <div class="sys-detail is-center" :title="systemDisk.mount">
              {{
                $t('certd.dashboard.diskDetail', {
                  label: diskLabel,
                  used: formatBytes(systemDisk.used),
                  total: formatBytes(systemDisk.total),
                })
              }}
            </div>
            <div class="sys-detail is-center">
              {{ $t('certd.dashboard.diskFree', { free: formatBytes(systemDisk.free) }) }}
              <template v-if="systemDisk.fstype"> · {{ systemDisk.fstype }}</template>
            </div>
          </template>
          <div v-else class="sys-detail is-center" :style="{ height: gaugeHeight, lineHeight: gaugeHeight }">
            {{ $t('certd.dashboard.diskUnavailable') }}
          </div>
        </div>
      </div>

      <!-- 主机与运行时长 -->
      <div class="sys-footer">
        <span class="sys-footer-item">
          <ArtSvgIcon icon="ri:computer-line" />{{ sys.os }}
        </span>
        <span class="sys-footer-item">
          <ArtSvgIcon icon="ri:time-line" />{{ $t('certd.dashboard.uptime', { time: formatUptime(sys.uptime) }) }}
        </span>
        <span class="sys-footer-item">
          <ArtSvgIcon icon="ri:calendar-line" />{{ $t('certd.dashboard.bootTime', { time: sys.bootTime }) }}
        </span>
      </div>
    </ElCard>

    <!-- ③ 四个列表 -->
    <div class="list-grid">
      <!-- 流水线 -->
      <ElCard class="art-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title"
              ><ArtSvgIcon icon="ri:node-tree" />{{ $t('certd.dashboard.cardPipeline') }}</span
            >
            <span class="card-count">{{
              $t('certd.dashboard.countItems', { n: pipelineTotal })
            }}</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/pipeline')">
              {{ $t('certd.common.viewAll') }}
            </ElLink>
          </div>
        </template>
        <div v-if="!pipelines.length" class="empty-line">
          {{ $t('certd.dashboard.emptyPipeline') }}
        </div>
        <ul v-else class="simple-list">
          <li
            v-for="item in pipelines"
            :key="item.id"
            class="simple-item is-clickable"
            @click="go('/certd/pipeline/detail/' + item.id)"
          >
            <div class="item-main">
              <span class="item-title">{{ item.title || $t('certd.dashboard.unnamedPipeline') }}</span>
              <span class="item-sub">
                <template v-if="item.disabled">{{ $t('certd.status.disabled') }} · </template
                >{{ $t('certd.dashboard.stageCount', { n: item.stageCount }) }} ·
                {{ $t('certd.dashboard.taskCount', { n: item.stepCount }) }}<template
                  v-if="item.stepDisabledCount"
                  >{{ $t('certd.dashboard.stepsDisabled', { n: item.stepDisabledCount }) }}</template
                ><template v-if="item.lastHistoryTime"> · {{ item.lastHistoryTime }}</template>
              </span>
            </div>
            <ElTag
              v-if="item.running"
              size="small"
              type="warning"
              effect="dark"
              class="flex-shrink-0"
            >
              {{ $t('certd.status.running') }}
            </ElTag>
            <ElTag
              v-else
              size="small"
              :type="runStatusMeta(item.lastStatus).type"
              effect="light"
              class="flex-shrink-0"
            >
              {{ item.lastHistoryTime ? runStatusMeta(item.lastStatus).text : $t('certd.common.never') }}
            </ElTag>
          </li>
        </ul>
      </ElCard>

      <!-- 执行记录 -->
      <ElCard class="art-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title"
              ><ArtSvgIcon icon="ri:history-line" />{{ $t('certd.dashboard.cardHistory') }}</span
            >
            <span class="card-count">{{
              $t('certd.dashboard.countItems', { n: historyTotal })
            }}</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/history')">
              {{ $t('certd.common.viewAll') }}
            </ElLink>
          </div>
        </template>
        <div v-if="!histories.length" class="empty-line">
          {{ $t('certd.dashboard.emptyHistory') }}
        </div>
        <ul v-else class="simple-list">
          <li
            v-for="item in histories"
            :key="item.id"
            class="simple-item is-clickable"
            @click="go('/certd/history')"
          >
            <div class="item-main">
              <span class="item-title">{{ item.pipelineTitle || $t('certd.dashboard.deletedPipeline') }}</span>
              <span class="item-sub">
                {{ triggerText(item.triggerType) }} · {{ item.startTime }}
                <template v-if="item.duration"
                  >· {{ $t('certd.dashboard.durationSuffix', { n: item.duration + 's' }) }}</template
                >
              </span>
            </div>
            <ElTag
              size="small"
              :type="runStatusMeta(item.status).type"
              effect="light"
              class="flex-shrink-0"
            >
              {{ runStatusMeta(item.status).text }}
            </ElTag>
          </li>
        </ul>
      </ElCard>

      <!-- 证书列表 -->
      <ElCard class="art-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title"
              ><ArtSvgIcon icon="ri:award-line" />{{ $t('certd.dashboard.cardCert') }}</span
            >
            <span class="card-count">{{
              $t('certd.dashboard.countCerts', { n: certTotal })
            }}</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/cert')">
              {{ $t('certd.common.viewAll') }}
            </ElLink>
          </div>
        </template>
        <div v-if="!certs.length" class="empty-line">{{ $t('certd.dashboard.emptyCert') }}</div>
        <ul v-else class="simple-list">
          <li
            v-for="item in certs"
            :key="item.id"
            class="simple-item is-clickable"
            @click="go('/certd/cert')"
          >
            <div class="item-main">
              <span class="item-title">{{ item.domain || firstDomain(item.domains) }}</span>
              <span class="item-sub">
                {{ item.issuer || $t('certd.dashboard.unknownIssuer') }}
                <template v-if="item.notAfter"
                  >· {{ $t('certd.dashboard.certExpireSuffix', { date: item.notAfter }) }}</template
                >
              </span>
            </div>
            <ElTag
              size="small"
              :type="certStatusMeta(item.daysLeft).type"
              effect="light"
              class="flex-shrink-0"
            >
              {{ certStatusMeta(item.daysLeft).text }}
            </ElTag>
          </li>
        </ul>
      </ElCard>

      <!-- 监控站点 -->
      <ElCard class="art-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title"
              ><ArtSvgIcon icon="ri:radar-line" />{{ $t('certd.dashboard.cardSite') }}</span
            >
            <span class="card-count">{{ $t('certd.dashboard.countSites', { n: siteTotal }) }}</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/monitor')">
              {{ $t('certd.common.viewAll') }}
            </ElLink>
          </div>
        </template>
        <div v-if="!sites.length" class="empty-line">{{ $t('certd.dashboard.emptySite') }}</div>
        <ul v-else class="simple-list">
          <li
            v-for="item in sites"
            :key="item.id"
            class="simple-item is-clickable"
            @click="go('/certd/monitor')"
          >
            <div class="item-main">
              <span class="item-title">{{ item.url }}</span>
              <span class="item-sub">
                {{ item.issuer || $t('certd.dashboard.noCert') }}
                <template v-if="item.expireTime"
                  >· {{ $t('certd.dashboard.certExpireSuffix', { date: item.expireTime }) }}</template
                >
                <template v-if="item.lastCheckTime"
                  >· {{ $t('certd.dashboard.checkedAt', { time: item.lastCheckTime }) }}</template
                >
              </span>
            </div>
            <ElTag
              size="small"
              :type="item.enabled === false ? 'info' : siteStatusMeta(item.status).type"
              effect="light"
              class="flex-shrink-0"
            >
              {{
                item.enabled === false ? $t('certd.status.disabled') : siteStatusMeta(item.status).text
              }}
            </ElTag>
          </li>
        </ul>
      </ElCard>
    </div>
  </div>
</template>

<script setup lang="ts">
  import {
    fetchCertList,
    fetchHistoryList,
    fetchOverview,
    fetchPipelineList,
    fetchSiteList,
    fetchSystemInfo,
  } from '@/api/certd'
  import ArtGaugeChart from '@/components/core/charts/art-gauge-chart/index.vue'
  import { useUserStore } from '@/store/modules/user'
  import {
    certStatusMeta,
    runStatusMeta,
    siteStatusMeta,
    triggerText,
    usageColor,
    usageText,
  } from '@/utils/certd'
  import { $t } from '@/locales'

  defineOptions({ name: 'CertdDashboard' })

  /** 每个列表卡片最多展示几条（四张卡统一 4 条，网格里的卡片高度才会一致） */
  const LIST_SIZE = 4

  const router = useRouter()
  const userStore = useUserStore()

  const loading = ref(false)
  const stats = ref<any>({})

  const pipelines = ref<any[]>([])
  const pipelineTotal = ref(0)
  const histories = ref<any[]>([])
  const historyTotal = ref(0)
  const certs = ref<any[]>([])
  const certTotal = ref(0)
  const sites = ref<any[]>([])
  const siteTotal = ref(0)

  /* ---------------- 系统信息 ---------------- */
  const sys = ref<any>({})
  const systemLoading = ref(false)
  /** 系统信息自动刷新间隔（毫秒） */
  const SYSTEM_REFRESH_MS = 5000
  let sysTimer: ReturnType<typeof setInterval> | undefined

  const hasSystemInfo = computed(
    () => sys.value && sys.value.cpu && sys.value.memory
  )

  /**
   * 系统盘：只展示系统盘（Windows 是系统所在盘符，类 Unix 是 /）。
   * 后端 collect_system_info 已经挑好并放在 systemDisk 里；
   * 老接口没有 systemDisk / system 字段时在这里兜底（C 盘 → 根目录 → 第一块盘），
   * 免得「升级只换了前端」时整块仪表是空的。
   */
  const systemDisk = computed(() => {
    const info = sys.value || {}
    if (info.systemDisk) return info.systemDisk
    const disks: any[] = Array.isArray(info.disks) ? info.disks : []
    if (!disks.length) return null
    return (
      disks.find((disk) => disk.system) ||
      disks.find((disk) => /^[a-c]:[\\/]?$/i.test(String(disk.mount || ''))) ||
      disks.find((disk) => String(disk.mount || '') === '/') ||
      disks[0]
    )
  })
  const diskLabel = computed(() => systemDisk.value?.mount || $t('certd.dashboard.systemDisk'))

  /** 仪表高度：窄屏压矮一点，免得下面的说明被挤出卡片 */
  const { width: windowWidth } = useWindowSize()
  const gaugeHeight = computed(() => ((windowWidth.value || 1200) <= 768 ? '132px' : '150px'))

  const loadSystemInfo = async () => {
    systemLoading.value = true
    try {
      sys.value = await fetchSystemInfo()
    } catch {
      // 拉取失败保留上一次数据，不打断看板
    } finally {
      systemLoading.value = false
    }
  }

  /** 字节数转人类可读（1.2 GB 这种） */
  const formatBytes = (bytes: number) => {
    const value = Number(bytes)
    if (!value || value <= 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    const index = Math.min(
      units.length - 1,
      Math.floor(Math.log(value) / Math.log(1024))
    )
    return (value / Math.pow(1024, index)).toFixed(index ? 1 : 0) + ' ' + units[index]
  }

  /** 运行秒数转「2 天 3 小时 / 5 小时 6 分」（文案走词条，中英文案各自决定分隔写法） */
  const formatUptime = (seconds: number) => {
    const value = Number(seconds) || 0
    const days = Math.floor(value / 86400)
    const hours = Math.floor((value % 86400) / 3600)
    const minutes = Math.floor((value % 3600) / 60)
    if (days) return $t('certd.dashboard.uptimeDays', { d: days, h: hours })
    if (hours) return $t('certd.dashboard.uptimeHours', { h: hours, m: minutes })
    return $t('certd.dashboard.uptimeMinutes', { m: minutes })
  }

  /**
   * 昵称兜底
   *
   * ⚠️ 「管理员」是默认账号的中文昵称，但它同时也是界面上的角色名。
   * 英文界面下如果直接把它当数据展示会突兀，所以兜底值本身也走词条。
   */
  const adminLabel = computed(() => $t('certd.dashboard.admin'))
  const userName = computed(
    () => userStore.info?.nickname || userStore.info?.userName || adminLabel.value
  )
  const isAdmin = computed(() => userStore.info?.role === 'admin')

  /** 问候语按小时分档；文案走词条，英文用 Good morning / afternoon / evening */
  const greeting = computed(() => {
    const hour = new Date().getHours()
    if (hour < 6) return $t('certd.dashboard.greetNight')
    if (hour < 12) return $t('certd.dashboard.greetMorning')
    if (hour < 14) return $t('certd.dashboard.greetNoon')
    if (hour < 18) return $t('certd.dashboard.greetAfternoon')
    return $t('certd.dashboard.greetEvening')
  })

  const firstDomain = (domains: string | string[]) => {
    if (Array.isArray(domains)) return domains[0] || '-'
    return String(domains || '-').split(',')[0]
  }

  const go = (path: string, query?: Record<string, any>) => {
    router.push({ path, query })
  }

  /** 列表接口统一返回 { records, total }；这里容忍直接返回数组的老写法 */
  const pickRecords = (data: any): { records: any[]; total: number } => {
    if (Array.isArray(data)) return { records: data, total: data.length }
    const records = data?.records || []
    return { records, total: Number(data?.total ?? records.length) }
  }

  const load = async () => {
    loading.value = true
    try {
      const [overview, pipelineData, historyData, certData, siteData] = await Promise.all([
        fetchOverview().catch(() => ({})),
        fetchPipelineList({ current: 1, size: LIST_SIZE }).catch(() => null),
        fetchHistoryList({ current: 1, size: LIST_SIZE }).catch(() => null),
        fetchCertList({ current: 1, size: LIST_SIZE }).catch(() => null),
        fetchSiteList({ current: 1, size: LIST_SIZE }).catch(() => null),
      ])

      stats.value = (overview as any)?.stats || {}

      const pipelineList = pickRecords(pipelineData)
      pipelines.value = pipelineList.records
      pipelineTotal.value = pipelineList.total || stats.value.pipelineTotal || 0

      const historyList = pickRecords(historyData)
      histories.value = historyList.records
      historyTotal.value = historyList.total

      const certList = pickRecords(certData)
      certs.value = certList.records
      certTotal.value = certList.total || stats.value.certTotal || 0

      const siteList = pickRecords(siteData)
      sites.value = siteList.records
      siteTotal.value = siteList.total || stats.value.siteTotal || 0
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    load()
    loadSystemInfo()
    // 定时刷新系统信息，CPU/内存/硬盘使用率保持实时
    sysTimer = setInterval(loadSystemInfo, SYSTEM_REFRESH_MS)
  })

  onUnmounted(() => {
    if (sysTimer) clearInterval(sysTimer)
  })
</script>

<style scoped>
  /*
    工作台的内容比一屏高（看板 + 三个仪表 + 四个列表），这里刻意不用
    art-full-height：那个类给的是「刚好一屏」的固定高度 + flex 列，
    卡片会被压缩（.art-card 的 card-body 还带 overflow: hidden），
    结果「系统信息」的仪表溢出到下面的列表卡片底下，看起来就是「被遮盖」。
    改成 min-height + 子元素不许收缩：一屏内撑满，超了交给外层 main 滚动。
  */
  .certd-dashboard {
    display: flex;
    flex-direction: column;
    gap: 12px;
    /* --art-full-height 已经扣掉了头部与页面纵向内边距（见 useLayoutHeight） */
    min-height: var(--art-full-height);
    padding-bottom: 8px;
  }

  /* 看板 / 卡片 / 列表都不许被压扁 */
  .certd-dashboard > * {
    flex: 0 0 auto;
  }

  /* ---------------- 页头：标题 + 一行摘要 + 动作 ---------------- */
  .dash-head {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 24px;
    align-items: flex-end;
    justify-content: space-between;
    padding: 2px 2px 0;
  }

  .dash-head-main {
    min-width: 0;
  }

  .dash-title {
    display: flex;
    gap: 8px;
    align-items: center;
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    line-height: 1.3;
    letter-spacing: -0.01em;
    color: var(--foreground);
  }

  /* 角色只是一行小字，不用 ElTag（会和"管理员"这个名字重复成一个标签） */
  .dash-role {
    padding: 0 6px;
    font-size: 11px;
    font-weight: 400;
    line-height: 18px;
    color: var(--muted-foreground);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  /*
   * 数据摘要：一行「标签 + 数字」，用中点分隔。
   * 原来四个统计项是居中散在一整行里的按钮，离标题很远、也没有分隔，
   * 看起来像三个不相干的元素；现在它紧跟标题，成为一个可读的句子。
   */
  .dash-sub {
    display: flex;
    flex-wrap: wrap;
    gap: 0 2px;
    align-items: baseline;
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--muted-foreground);
  }

  .dash-stat {
    display: inline-flex;
    gap: 4px;
    align-items: baseline;
    cursor: pointer;
    border-radius: var(--radius-sm);
  }

  .dash-stat:hover {
    color: var(--foreground);
  }

  .dash-stat b {
    font-size: 14px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--foreground);
  }

  .dash-stat.is-warn,
  .dash-stat.is-warn b {
    color: var(--warning);
  }

  .dash-sep {
    padding: 0 6px;
    color: var(--border);
  }

  .dash-actions {
    display: flex;
    flex: 0 0 auto;
    flex-wrap: wrap;
    gap: 8px;
  }

  /* ---------------- 四个列表 ---------------- */
  .list-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .card-header {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .card-title {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    font-size: 14px;
    font-weight: 600;
    color: var(--foreground);
  }

  .card-title .art-svg-icon {
    color: var(--muted-foreground);
  }

  .card-count {
    font-size: 12px;
    font-weight: 400;
    color: var(--muted-foreground);
  }

  .card-header :deep(.el-link) {
    margin-left: auto;
    font-size: 12px;
  }

  .simple-list {
    margin: 0;
    padding: 0;
    list-style: none;
    /*
     * 四张卡统一预留 4 行的高度：条目少的卡（证书 2 条 / 站点 3 条）
     * 不会在底部留出一块比旁边短的空洞 —— 网格里两张卡高度一样，
     * 但内容一多一少时，短的那张底部会露出明显空白，看起来就是「参差不齐」。
     */
    min-height: 220px;
  }

  .simple-item {
    display: flex;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }

  .simple-item:last-child {
    border-bottom: none;
  }

  .simple-item.is-clickable {
    padding-right: 6px;
    padding-left: 6px;
    margin: 0 -6px;
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: background-color 0.12s ease;
  }

  /* 行 hover 只换底色（shadcn 的列表行交互），不给文字换色 + 下划线 */
  .simple-item.is-clickable:hover {
    background: var(--accent);
  }

  .item-main {
    min-width: 0;
  }

  .item-title {
    display: block;
    overflow: hidden;
    font-size: 13px;
    font-weight: 500;
    color: var(--foreground);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .item-sub {
    display: block;
    overflow: hidden;
    font-size: 12px;
    color: var(--muted-foreground);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .empty-line {
    padding: 22px 0;
    font-size: 12.5px;
    line-height: 1.6;
    text-align: center;
    color: var(--muted-foreground);
  }

  /* ---------------- 系统信息看板 ---------------- */
  .system-card :deep(.el-card__header) {
    padding-bottom: 10px;
  }

  /* 三个仪表等宽横排：CPU / 内存 / 系统盘 */
  .sys-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 18px;
  }

  .sys-col {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    padding-left: 18px;
    border-left: 1px solid var(--border);
  }

  .sys-col:first-child {
    padding-left: 0;
    border-left: none;
  }

  .sys-head {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }

  .sys-icon {
    font-size: 16px;
    color: var(--muted-foreground);
  }

  .sys-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--foreground);
  }

  /* 状态词（正常 / 偏高 / 告警）紧跟标题，不要推到列尾：
     列宽 360px，右对齐时「正常」离「CPU 使用率」有 240px，
     看起来像另一列的标签。 */
  .sys-state {
    flex: 0 0 auto;
    font-size: 12px;
    font-weight: 500;
  }

  .sys-detail {
    overflow: hidden;
    font-size: 12px;
    color: var(--muted-foreground);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sys-detail.is-center {
    text-align: center;
  }

  .sys-footer {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 20px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }

  .sys-footer-item {
    display: inline-flex;
    gap: 5px;
    align-items: center;
    font-size: 12px;
    color: var(--muted-foreground);
  }

  .sys-footer-item .art-svg-icon {
    font-size: 14px;
  }

  /* ---------------- 响应式 ---------------- */
  @media (max-width: 1024px) {
    .list-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .sys-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
  }

  @media (max-width: 768px) {
    .sys-grid {
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
    }
  }

  @media (max-width: 768px) {
    .board-stats {
      justify-content: flex-start;
    }

    .board-actions {
      width: 100%;
    }

    .board-actions :deep(.el-button) {
      flex: 1 1 auto;
    }
  }
</style>
