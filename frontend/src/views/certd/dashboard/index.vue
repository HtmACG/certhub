<!--
  工作台
  =========================================================
  结构按「上面一块简约看板 + 下面四个列表」来：

  1. 顶部看板：一行文字 + 4 个数字 + 3 个快捷动作，不做大标题、不堆卡片；
  2. 下面只有四个列表：流水线 / 执行记录 / 证书 / 监控站点，
     每张卡只放最近 5 条，「查看全部」跳对应页面。

  趋势图、签发机构分布、能力总览这类"看板式"内容已经去掉 ——
  工作台的定位是"扫一眼现状、点进去处理"，不是报表。
-->
<template>
  <div class="certd-dashboard art-full-height g-scope" v-loading="loading">
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

    <!-- ② 四个列表 -->
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
                {{ item.stepCount }} 个任务
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
  } from '@/api/certd'
  import { useUserStore } from '@/store/modules/user'
  import { certStatusMeta, runStatusMeta, siteStatusMeta, triggerText } from '@/utils/certd'

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

  onMounted(load)
</script>

<style scoped>
  .certd-dashboard {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-bottom: 8px;
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

  /* ---------------- 响应式 ---------------- */
  @media (max-width: 1024px) {
    .list-grid {
      grid-template-columns: minmax(0, 1fr);
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
