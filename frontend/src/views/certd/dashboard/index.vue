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
    <!-- ① 简约看板 -->
    <div class="dash-board">
      <div class="board-line">
        <div class="board-greet">
          {{ greeting }}，{{ userName }}
          <!-- 昵称本身就是「管理员」时不再重复显示角色，避免「管理员 管理员」 -->
          <span v-if="isAdmin && userName !== '管理员'" class="board-role">管理员</span>
        </div>
        <div class="board-stats">
          <button type="button" class="board-stat" @click="go('/certd/pipeline')">
            流水线 <b>{{ stats.pipelineTotal || 0 }}</b>
          </button>
          <button type="button" class="board-stat" @click="go('/certd/cert')">
            证书 <b>{{ stats.certTotal || 0 }}</b>
          </button>
          <button
            type="button"
            class="board-stat"
            :class="{ 'is-warn': stats.certExpiring > 0 }"
            @click="go('/certd/cert', { expiring: 1 })"
          >
            30 天内到期 <b>{{ stats.certExpiring || 0 }}</b>
          </button>
          <button type="button" class="board-stat" @click="go('/certd/monitor')">
            监控站点 <b>{{ stats.siteTotal || 0 }}</b>
          </button>
        </div>
        <div class="board-actions">
          <ElButton type="primary" @click="go('/certd/pipeline', { create: 'template' })">
            <ArtSvgIcon icon="ri:add-line" class="mr-1" />新建流水线
          </ElButton>
          <ElButton @click="go('/certd/cert', { import: 1 })">
            <ArtSvgIcon icon="ri:upload-2-line" class="mr-1" />导入证书
          </ElButton>
          <ElButton @click="go('/certd/access', { create: 1 })">
            <ArtSvgIcon icon="ri:key-2-line" class="mr-1" />添加授权
          </ElButton>
        </div>
      </div>
    </div>

    <!-- ② 系统信息看板：CPU / 内存 / 系统盘使用率，三个车速表仪表 -->
    <ElCard v-if="hasSystemInfo" class="art-card system-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title"><ArtSvgIcon icon="ri:server-line" />系统信息</span>
          <span class="card-count">{{ sys.hostname }}</span>
          <ElTooltip :content="systemLoading ? '正在刷新' : '立即刷新系统信息'" placement="top">
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
            <span class="sys-name">CPU 使用率</span>
            <span class="sys-state" :style="{ color: usageColor(sys.cpu.percent) }">
              {{ usageText(sys.cpu.percent) }}
            </span>
          </div>
          <ArtGaugeChart :value="Number(sys.cpu.percent) || 0" :height="gaugeHeight" />
          <div class="sys-detail is-center" :title="sys.cpu.name">
            {{ sys.cpu.coresPhysical }} 核 {{ sys.cpu.coresLogical }} 线程
            <template v-if="sys.cpu.freqMhz"> · {{ (sys.cpu.freqMhz / 1000).toFixed(1) }} GHz</template>
          </div>
        </div>

        <!-- 内存 -->
        <div class="sys-col">
          <div class="sys-head">
            <ArtSvgIcon icon="ri:database-2-line" class="sys-icon" />
            <span class="sys-name">内存使用率</span>
            <span class="sys-state" :style="{ color: usageColor(sys.memory.percent) }">
              {{ usageText(sys.memory.percent) }}
            </span>
          </div>
          <ArtGaugeChart :value="Number(sys.memory.percent) || 0" :height="gaugeHeight" />
          <div class="sys-detail is-center">
            已用 {{ formatBytes(sys.memory.used) }} / 共 {{ formatBytes(sys.memory.total) }}
          </div>
          <div v-if="sys.swap.total" class="sys-detail is-center">
            交换区 {{ sys.swap.percent }}% · {{ formatBytes(sys.swap.used) }} /
            {{ formatBytes(sys.swap.total) }}
          </div>
        </div>

        <!-- 系统盘：只展示系统盘（Windows 是系统所在盘符，Linux 是 /） -->
        <div class="sys-col">
          <div class="sys-head">
            <ArtSvgIcon icon="ri:hard-drive-2-line" class="sys-icon" />
            <span class="sys-name">系统盘使用率</span>
            <span v-if="systemDisk" class="sys-state" :style="{ color: usageColor(systemDisk.percent) }">
              {{ usageText(systemDisk.percent) }}
            </span>
          </div>
          <template v-if="systemDisk">
            <ArtGaugeChart :value="Number(systemDisk.percent) || 0" :height="gaugeHeight" />
            <div class="sys-detail is-center" :title="systemDisk.mount">
              {{ diskLabel }} 已用 {{ formatBytes(systemDisk.used) }} /
              {{ formatBytes(systemDisk.total) }}
            </div>
            <div class="sys-detail is-center">
              剩余 {{ formatBytes(systemDisk.free) }}
              <template v-if="systemDisk.fstype"> · {{ systemDisk.fstype }}</template>
            </div>
          </template>
          <div v-else class="sys-detail is-center" :style="{ height: gaugeHeight, lineHeight: gaugeHeight }">
            暂时读不到系统盘信息
          </div>
        </div>
      </div>

      <!-- 主机与运行时长 -->
      <div class="sys-footer">
        <span class="sys-footer-item">
          <ArtSvgIcon icon="ri:computer-line" />{{ sys.os }}
        </span>
        <span class="sys-footer-item">
          <ArtSvgIcon icon="ri:time-line" />已运行 {{ formatUptime(sys.uptime) }}
        </span>
        <span class="sys-footer-item">
          <ArtSvgIcon icon="ri:calendar-line" />启动于 {{ sys.bootTime }}
        </span>
      </div>
    </ElCard>

    <!-- ③ 四个列表 -->
    <div class="list-grid">
      <!-- 流水线 -->
      <ElCard class="art-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title"><ArtSvgIcon icon="ri:node-tree" />流水线</span>
            <span class="card-count">{{ pipelineTotal }} 条</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/pipeline')">
              查看全部
            </ElLink>
          </div>
        </template>
        <div v-if="!pipelines.length" class="empty-line">
          还没有流水线，点右上角「新建流水线」开始。
        </div>
        <ul v-else class="simple-list">
          <li
            v-for="item in pipelines"
            :key="item.id"
            class="simple-item is-clickable"
            @click="go('/certd/pipeline/detail/' + item.id)"
          >
            <div class="item-main">
              <span class="item-title">{{ item.title || '未命名流水线' }}</span>
              <span class="item-sub">
                {{ item.disabled ? '已停用' : '已启用' }} · {{ item.stageCount }} 个阶段 ·
                {{ item.stepCount }} 个任务<template v-if="item.stepDisabledCount"
                  >（{{ item.stepDisabledCount }} 步已停用）</template
                >
                <template v-if="item.lastHistoryTime">· 上次 {{ item.lastHistoryTime }}</template>
              </span>
            </div>
            <ElTag
              v-if="item.running"
              size="small"
              type="warning"
              effect="dark"
              class="flex-shrink-0"
            >
              运行中
            </ElTag>
            <ElTag
              v-else
              size="small"
              :type="runStatusMeta(item.lastStatus).type"
              effect="light"
              class="flex-shrink-0"
            >
              {{ item.lastHistoryTime ? runStatusMeta(item.lastStatus).text : '未运行' }}
            </ElTag>
          </li>
        </ul>
      </ElCard>

      <!-- 执行记录 -->
      <ElCard class="art-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title"><ArtSvgIcon icon="ri:history-line" />执行记录</span>
            <span class="card-count">{{ historyTotal }} 条</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/history')">
              查看全部
            </ElLink>
          </div>
        </template>
        <div v-if="!histories.length" class="empty-line">还没有执行记录，跑一次流水线就有了。</div>
        <ul v-else class="simple-list">
          <li
            v-for="item in histories"
            :key="item.id"
            class="simple-item is-clickable"
            @click="go('/certd/history')"
          >
            <div class="item-main">
              <span class="item-title">{{ item.pipelineTitle || '已删除的流水线' }}</span>
              <span class="item-sub">
                {{ triggerText(item.triggerType) }} · {{ item.startTime }}
                <template v-if="item.duration">· 耗时 {{ item.duration }}s</template>
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
            <span class="card-title"><ArtSvgIcon icon="ri:award-line" />证书列表</span>
            <span class="card-count">{{ certTotal }} 张</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/cert')">
              查看全部
            </ElLink>
          </div>
        </template>
        <div v-if="!certs.length" class="empty-line">证书库还是空的，申请或导入一张证书后显示在这里。</div>
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
                {{ item.issuer || '未知签发机构' }}
                <template v-if="item.notAfter">· 到期 {{ item.notAfter }}</template>
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
            <span class="card-title"><ArtSvgIcon icon="ri:radar-line" />被监控的站点</span>
            <span class="card-count">{{ siteTotal }} 个</span>
            <ElLink type="primary" :underline="false" @click="go('/certd/monitor')">
              查看全部
            </ElLink>
          </div>
        </template>
        <div v-if="!sites.length" class="empty-line">还没有被监控的站点，去「站点监控」添加 URL。</div>
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
                {{ item.issuer || '未获取到证书' }}
                <template v-if="item.expireTime">· 到期 {{ item.expireTime }}</template>
                <template v-if="item.lastCheckTime">· 检查于 {{ item.lastCheckTime }}</template>
              </span>
            </div>
            <ElTag
              size="small"
              :type="item.enabled === false ? 'info' : siteStatusMeta(item.status).type"
              effect="light"
              class="flex-shrink-0"
            >
              {{ item.enabled === false ? '已停用' : siteStatusMeta(item.status).text }}
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

  defineOptions({ name: 'CertdDashboard' })

  /** 每个列表卡片最多展示几条 */
  const LIST_SIZE = 5

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
  const diskLabel = computed(() => systemDisk.value?.mount || '系统盘')

  /** 仪表高度：窄屏压矮一点，免得下面的说明被挤出卡片 */
  const { width: windowWidth } = useWindowSize()
  const gaugeHeight = computed(() => ((windowWidth.value || 1200) <= 768 ? '150px' : '178px'))

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

  /** 运行秒数转「2 天 3 小时 / 5 小时 6 分」 */
  const formatUptime = (seconds: number) => {
    const value = Number(seconds) || 0
    const days = Math.floor(value / 86400)
    const hours = Math.floor((value % 86400) / 3600)
    const minutes = Math.floor((value % 3600) / 60)
    if (days) return `${days} 天 ${hours} 小时`
    if (hours) return `${hours} 小时 ${minutes} 分`
    return `${minutes} 分钟`
  }

  const userName = computed(() => userStore.info?.nickname || userStore.info?.userName || '管理员')
  const isAdmin = computed(() => userStore.info?.role === 'admin')

  const greeting = computed(() => {
    const hour = new Date().getHours()
    if (hour < 6) return '夜间好'
    if (hour < 12) return '上午好'
    if (hour < 14) return '中午好'
    if (hour < 18) return '下午好'
    return '晚上好'
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
    min-height: var(--art-full-height);
    padding-bottom: 8px;
  }

  /* 看板 / 卡片 / 列表都不许被压扁 */
  .certd-dashboard > * {
    flex: 0 0 auto;
  }

  /* ---------------- 简约看板：一行文字 + 数字 + 动作 ---------------- */
  .dash-board {
    padding: 12px 16px;
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: calc(var(--custom-radius) + 4px);
  }

  .board-line {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    align-items: center;
    justify-content: space-between;
  }

  .board-greet {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 6px;
    align-items: center;
    font-size: 14px;
    font-weight: 500;
    color: var(--g-text, var(--art-gray-800));
  }

  /* 角色只是一行小字，不用 ElTag（会和"管理员"这个名字重复成一个标签） */
  .board-role {
    padding: 0 6px;
    font-size: 11px;
    font-weight: 400;
    color: var(--g-text-3, var(--art-gray-500));
    border: 1px solid var(--g-line, var(--art-card-border));
    border-radius: var(--custom-radius);
  }

  .board-stats {
    display: flex;
    flex-wrap: wrap;
    flex: 1 1 auto;
    gap: 6px 14px;
    align-items: center;
    justify-content: center;
  }

  .board-stat {
    flex: 0 0 auto;
    padding: 2px 8px;
    font-size: 13px;
    color: var(--g-text-2, var(--art-gray-600));
    cursor: pointer;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--custom-radius);
    transition: color 0.15s, background-color 0.15s, border-color 0.15s;
  }

  .board-stat:hover {
    color: var(--g-blue, var(--theme-color));
    background: var(--g-fill-hover, var(--art-gray-200));
    border-color: var(--g-line, var(--art-card-border));
  }

  .board-stat b {
    margin-left: 2px;
    font-size: 15px;
    font-weight: 600;
    color: var(--g-text, var(--art-gray-800));
  }

  .board-stat.is-warn,
  .board-stat.is-warn b {
    color: var(--g-amber, #e37400);
  }

  .board-actions {
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
    color: var(--g-text, var(--art-gray-800));
  }

  .card-title .art-svg-icon {
    color: var(--g-text-2, var(--art-gray-600));
  }

  .card-count {
    font-size: 12px;
    font-weight: 400;
    color: var(--g-text-3, var(--art-gray-500));
  }

  .card-header :deep(.el-link) {
    margin-left: auto;
    font-size: 12px;
  }

  .simple-list {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .simple-item {
    display: flex;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--g-line-2, var(--art-card-border));
  }

  .simple-item:last-child {
    border-bottom: none;
  }

  .simple-item.is-clickable {
    cursor: pointer;
  }

  .simple-item.is-clickable:hover .item-title {
    color: var(--g-blue, var(--theme-color));
  }

  .item-main {
    min-width: 0;
  }

  .item-title {
    display: block;
    overflow: hidden;
    font-size: 13px;
    font-weight: 500;
    color: var(--g-text, var(--art-gray-800));
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .item-sub {
    display: block;
    overflow: hidden;
    font-size: 12px;
    color: var(--g-text-3, var(--art-gray-500));
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .empty-line {
    padding: 22px 0;
    font-size: 12.5px;
    line-height: 1.6;
    text-align: center;
    color: var(--g-text-3, var(--art-gray-500));
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
    border-left: 1px solid var(--g-line-2, var(--art-card-border));
  }

  .sys-col:first-child {
    padding-left: 0;
    border-left: none;
  }

  .sys-head {
    display: flex;
    gap: 6px;
    align-items: baseline;
  }

  .sys-icon {
    font-size: 16px;
    color: var(--g-text-2, var(--art-gray-600));
  }

  .sys-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--g-text, var(--art-gray-800));
  }

  /* 状态词（正常 / 偏高 / 告警）：颜色由使用率分档决定，写在行内 style 上 */
  .sys-state {
    flex: 0 0 auto;
    margin-left: auto;
    font-size: 12px;
    font-weight: 500;
  }

  .sys-detail {
    overflow: hidden;
    font-size: 12px;
    color: var(--g-text-3, var(--art-gray-500));
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
    border-top: 1px solid var(--g-line-2, var(--art-card-border));
  }

  .sys-footer-item {
    display: inline-flex;
    gap: 5px;
    align-items: center;
    font-size: 12px;
    color: var(--g-text-2, var(--art-gray-600));
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
