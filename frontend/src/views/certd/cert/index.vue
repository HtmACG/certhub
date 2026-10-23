<!--
  证书库
  =========================================================
  一个页面解决「看、导、查、下」：
  · 列表按剩余有效期上色，快到期的排到眼前；
  · 点域名打开详情抽屉：概览 / SAN / 指纹 / 证书 PEM / 私钥（小眼睛控制）；
  · 导出下拉支持 pem / der / pfx / p7b / jks / nginx 六种格式；
  · 手工证书也能导入（证书 + 私钥必须成对，后端会校验）。
-->
<template>
  <div class="certd-cert art-full-height g-scope">
    <ArtSearchBar
      v-model="searchForm"
      :items="searchItems"
      :show-expand="false"
      @search="handleSearch"
      @reset="handleReset"
    />

    <ElCard class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" :loading="loading" @refresh="refreshData">
        <template #left>
          <ElSpace wrap>
            <ElButton type="primary" @click="importVisible = true">
              <ArtSvgIcon icon="ri:upload-2-line" class="mr-1" />导入证书
            </ElButton>
            <ElButton
              type="danger"
              plain
              :disabled="!selectedIds.length"
              :loading="removing"
              @click="removeSelected"
            >
              <ArtSvgIcon icon="ri:delete-bin-line" class="mr-1" />
              批量删除<template v-if="selectedIds.length">（{{ selectedIds.length }}）</template>
            </ElButton>
            <ElButton :disabled="!expiringOnly" @click="toggleExpiring">
              只看 30 天内到期
            </ElButton>
          </ElSpace>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        @selection-change="handleSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      >
        <template #domains="{ row }">
          <div class="cell-domains">
            <ElLink type="primary" :underline="false" @click="openDetail(row)">
              {{ row.domain }}
            </ElLink>
            <div v-if="row.domains.length > 1" class="cell-sub">
              共 {{ row.domains.length }} 个域名
            </div>
          </div>
        </template>

        <template #notAfter="{ row }">
          <ElTag :type="certStatusMeta(row.daysLeft).type" size="small" effect="light">
            {{ certStatusMeta(row.daysLeft).text }}
          </ElTag>
          <div class="cell-sub">{{ row.notAfter || '-' }}</div>
        </template>

        <template #operation="{ row }">
          <div class="cell-actions">
            <ElTooltip content="查看详情">
              <ArtButtonTable type="view" @click="openDetail(row)" />
            </ElTooltip>
            <ElDropdown trigger="click" @command="(format: string) => handleDownload(row, format)">
              <ArtButtonTable type="more" />
              <template #dropdown>
                <ElDropdownMenu>
                  <ElDropdownItem command="pem">下载 PEM 证书</ElDropdownItem>
                  <ElDropdownItem command="der">下载 DER</ElDropdownItem>
                  <ElDropdownItem command="nginx">下载 Nginx 合并格式</ElDropdownItem>
                  <ElDropdownItem command="pfx" divided>下载 PFX（PKCS#12）</ElDropdownItem>
                  <ElDropdownItem command="p7b">下载 P7B 证书链</ElDropdownItem>
                  <ElDropdownItem command="jks">下载 JKS</ElDropdownItem>
                  <ElDropdownItem command="key" divided>下载私钥</ElDropdownItem>
                </ElDropdownMenu>
              </template>
            </ElDropdown>
            <ElTooltip content="删除">
              <ArtButtonTable type="delete" @click="removeCert(row)" />
            </ElTooltip>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <!-- 详情抽屉 -->
    <ElDrawer v-model="detailVisible" title="证书详情" size="min(720px, 96vw)" destroy-on-close>
      <div v-if="detail" v-loading="detailLoading" class="cert-detail">
        <div class="cert-detail-head">
          <BrandAvatar
            :logo="issuerLogo(issuerOf(detail.issuer))"
            :color="issuerColor(issuerOf(detail.issuer))"
            :name="issuerOf(detail.issuer)"
            :size="40"
          />
          <div>
            <div class="cert-detail-title">{{ detail.domain }}</div>
            <div class="cell-sub">{{ detail.issuer }}</div>
          </div>
          <ElTag :type="certStatusMeta(detail.daysLeft).type" effect="light">
            {{ certStatusMeta(detail.daysLeft).text }}
          </ElTag>
        </div>

        <ElDescriptions :column="1" border class="mt-3">
          <ElDescriptionsItem label="主题">{{ detail.details?.subject }}</ElDescriptionsItem>
          <ElDescriptionsItem label="签发者">{{ detail.details?.issuer }}</ElDescriptionsItem>
          <ElDescriptionsItem label="有效期">
            {{ detail.details?.notBefore }} ~ {{ detail.details?.notAfter }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="公钥">{{ detail.details?.publicKey }}</ElDescriptionsItem>
          <ElDescriptionsItem label="签名算法">
            {{ detail.details?.signatureAlgorithm }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="序列号">{{ detail.details?.serialNumber }}</ElDescriptionsItem>
          <ElDescriptionsItem label="SHA256 指纹">
            <span class="mono break-all">{{ detail.details?.fingerprintSha256 }}</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="证书链">
            {{ detail.details?.chainCount }} 张
            <ElTag v-if="detail.details?.isSelfSigned" size="small" type="warning" effect="plain">
              自签名
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="SAN">
            <div class="san-wrap">
              <ElTag v-for="name in detail.details?.san || []" :key="name" size="small" effect="plain">
                {{ name }}
              </ElTag>
            </div>
          </ElDescriptionsItem>
        </ElDescriptions>

        <div class="pem-block">
          <div class="pem-head">
            <span>证书 PEM</span>
            <ElButton link type="primary" @click="copyText(detail.certPem)">复制</ElButton>
          </div>
          <pre class="pem-body">{{ detail.certPem }}</pre>
        </div>

        <div class="pem-block">
          <div class="pem-head">
            <span>私钥 PEM</span>
            <div class="flex items-center gap-2">
              <ElButton link type="primary" @click="keyVisible = !keyVisible">
                {{ keyVisible ? '隐藏' : '显示' }}
              </ElButton>
              <ElButton v-if="keyVisible" link @click="copyText(detail.keyPem)">复制</ElButton>
            </div>
          </div>
          <pre class="pem-body">{{ keyVisible ? detail.keyPem : maskPem(detail.keyPem) }}</pre>
        </div>

        <div class="export-wrap">
          <span class="cell-sub">导出：</span>
          <ElSelect v-model="exportFormat" class="w-40">
            <ElOption label="PEM" value="pem" />
            <ElOption label="DER" value="der" />
            <ElOption label="Nginx（证书+私钥）" value="nginx" />
            <ElOption label="PFX（PKCS#12）" value="pfx" />
            <ElOption label="P7B（证书链）" value="p7b" />
            <ElOption label="JKS（Java KeyStore）" value="jks" />
          </ElSelect>
          <ElInput
            v-if="exportFormat === 'pfx' || exportFormat === 'jks'"
            v-model="exportPassword"
            type="password"
            show-password
            placeholder="导出密码（JKS 至少 6 位）"
            class="w-52"
          />
          <ElTooltip
            v-if="exportFormat === 'pfx'"
            content="Windows Server 2016 / 2008 只认 SHA1 + 3DES 的 PFX，导入报错时换这里的兼容档（服务器需要装 openssl）"
          >
            <ElSelect v-model="exportPfxArgs" class="w-56" placeholder="PFX 兼容性">
              <ElOption label="最新 Windows 服务器（默认）" value="" />
              <ElOption
                label="Windows Server 2016 兼容"
                value="-macalg SHA1 -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES"
              />
              <ElOption
                label="Windows Server 2008 兼容"
                value="-nomac -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES"
              />
            </ElSelect>
          </ElTooltip>
          <ElButton type="primary" @click="handleDownload(detail, exportFormat)">下载</ElButton>
          <ElButton @click="handleDownload(detail, 'key')">下载私钥</ElButton>
        </div>
      </div>
    </ElDrawer>

    <!-- 导入 -->
    <ElDialog v-model="importVisible" title="导入自有证书" width="min(680px, 94vw)" destroy-on-close>
      <ElAlert type="info" :closable="false" class="mb-3">
        只接受 PEM 格式的证书与私钥，两者必须是一对（后端会用公钥比对校验）。
        导入后的证书与流水线签发的一样：可部署、可监控到期、可导出其它格式。
      </ElAlert>
      <ElForm label-position="top">
        <ElFormItem label="证书内容（含证书链）">
          <ElInput
            v-model="importForm.cert"
            type="textarea"
            :autosize="{ minRows: 5, maxRows: 12 }"
            placeholder="-----BEGIN CERTIFICATE-----"
          />
        </ElFormItem>
        <ElFormItem label="私钥内容">
          <ElInput
            v-model="importForm.key"
            type="textarea"
            :autosize="{ minRows: 5, maxRows: 12 }"
            placeholder="-----BEGIN PRIVATE KEY-----"
          />
        </ElFormItem>
        <ElFormItem label="备注">
          <ElInput v-model="importForm.remark" placeholder="例如：从阿里云下载的 2026 年证书" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="importVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="importing" @click="submitImport">导入</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import { useTable } from '@/hooks/core/useTable'
  import {
    deleteCert,
    downloadCert,
    fetchCertDetail,
    fetchCertList,
    importCert,
  } from '@/api/certd'
  import type { CertItem } from '@/api/certd'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { certStatusMeta } from '@/utils/certd'
  import { useBatchDelete } from '../composables/use-batch-delete'
  import BrandAvatar from '../components/brand-avatar.vue'

  defineOptions({ name: 'CertdCert' })

  const route = useRoute()
  const searchForm = ref<Record<string, any>>({ keyword: undefined, expiring: undefined })
  const expiringOnly = ref(false)

  const searchItems = [
    { key: 'keyword', label: '关键字', type: 'input', placeholder: '域名 / 签发机构' },
    {
      key: 'expiring',
      label: '到期范围',
      type: 'select',
      options: [
        { label: '30 天内到期', value: '30' },
        { label: '7 天内到期', value: '7' },
        { label: '90 天内到期', value: '90' },
      ],
    },
  ]

  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    searchParams,
    getData,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshData,
  } = useTable({
    core: {
      apiFn: fetchCertList,
      apiParams: { current: 1, size: 10 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'domains', label: '域名', minWidth: 220, useSlot: true },
        { prop: 'issuer', label: '签发机构', minWidth: 200 },
        { prop: 'notAfter', label: '有效期', width: 160, useSlot: true },
        { prop: 'createTime', label: '入库时间', width: 170 },
        { prop: 'operation', label: '操作', width: 140, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteCert,
    { label: '证书', nameOf: (row: any) => row.domain, onDone: () => refreshData() }
  )

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }

  const handleReset = () => {
    expiringOnly.value = false
    resetSearchParams()
  }

  const toggleExpiring = () => {
    expiringOnly.value = !expiringOnly.value
    searchParams.expiring = expiringOnly.value ? '30' : undefined
    getData()
  }

  /* ---------------- 详情 ---------------- */
  const detailVisible = ref(false)
  const detailLoading = ref(false)
  const detail = ref<any>(null)
  const keyVisible = ref(false)
  const exportFormat = ref('pem')
  const exportPassword = ref('')
  /** PFX 的 Windows 兼容参数（空 = 最新服务器默认） */
  const exportPfxArgs = ref('')

  const openDetail = async (row: CertItem) => {
    detailVisible.value = true
    detailLoading.value = true
    keyVisible.value = false
    detail.value = null
    try {
      detail.value = await fetchCertDetail(row.id)
    } finally {
      detailLoading.value = false
    }
  }

  const maskPem = (pem: string) => {
    if (!pem) return ''
    const lines = pem.split('\n')
    const head = lines.slice(0, 2).join('\n')
    const tail = lines.slice(-2).join('\n')
    return head + '\n' + '········ 已隐藏，点「显示」查看完整私钥 ········\n' + tail
  }

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text || '')
      ElMessage.success('已复制')
    } catch {
      ElMessage.error('复制失败，请手动选择')
    }
  }

  const handleDownload = async (row: CertItem, format: string) => {
    try {
      if ((format === 'pfx' || format === 'jks') && !exportPassword.value) {
        ElMessage.warning('请先填写导出密码（JKS 至少 6 位）')
        return
      }
      await downloadCert(row.id, format === 'key' ? 'pem' : format, {
        password: exportPassword.value,
        args: format === 'pfx' ? exportPfxArgs.value : '',
        type: format === 'key' ? 'key' : 'cert',
      })
      ElMessage.success('已开始下载')
    } catch (error: any) {
      ElMessage.error(error?.message || '下载失败')
    }
  }

  const removeCert = async (row: CertItem) => {
    await ElMessageBox.confirm('删除后无法恢复，确定删除这张证书吗？', '删除证书', {
      type: 'warning',
    })
    await deleteCert(row.id)
    ElMessage.success('已删除')
    refreshData()
  }

  /* ---------------- 导入 ---------------- */
  const importVisible = ref(false)
  const importing = ref(false)
  const importForm = reactive({ cert: '', key: '', remark: '' })

  const submitImport = async () => {
    if (!importForm.cert.includes('BEGIN CERTIFICATE')) {
      ElMessage.warning('证书内容缺少 -----BEGIN CERTIFICATE-----')
      return
    }
    if (!importForm.key.includes('PRIVATE KEY')) {
      ElMessage.warning('私钥内容缺少 -----BEGIN ... PRIVATE KEY-----')
      return
    }
    importing.value = true
    try {
      const result = await importCert({ ...importForm })
      ElMessage.success('已导入：' + (result.domains || []).join(', '))
      importVisible.value = false
      importForm.cert = ''
      importForm.key = ''
      importForm.remark = ''
      refreshData()
    } finally {
      importing.value = false
    }
  }

  /* ---------------- 签发机构图标 ---------------- */
  const issuerOf = (issuer?: string) => {
    const text = (issuer || '').toLowerCase()
    if (text.includes("let's encrypt")) return "Let's Encrypt"
    if (text.includes('zerossl')) return 'ZeroSSL'
    if (text.includes('google')) return 'Google Trust Services'
    if (text.includes('buypass')) return 'Buypass'
    if (text.includes('digicert')) return 'DigiCert'
    if (text.includes('trustasia')) return 'TrustAsia'
    return issuer || '未知签发机构'
  }

  const issuerLogo = (name: string) => {
    const map: Record<string, string> = {
      "Let's Encrypt": 'logos:letsencrypt',
      'Google Trust Services': 'logos:google-icon',
      ZeroSSL: 'mdi:shield-lock-outline',
      Buypass: 'mdi:shield-lock-outline',
      DigiCert: 'mdi:shield-lock-outline',
      TrustAsia: 'mdi:shield-lock-outline',
    }
    return map[name] || 'mdi:file-certificate-outline'
  }

  const issuerColor = (name: string) => {
    const map: Record<string, string> = {
      "Let's Encrypt": '#003a70',
      'Google Trust Services': '#4285f4',
      ZeroSSL: '#1b6ee0',
      Buypass: '#00979d',
    }
    return map[name] || '#8b5cf6'
  }

  onMounted(() => {
    if (route.query.import) importVisible.value = true
  })
</script>

<style scoped>
  .cell-domains {
    min-width: 0;
  }

  .cell-sub {
    margin-top: 2px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .cell-actions {
    display: flex;
    align-items: center;
  }

  .cert-detail-head {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .cert-detail-title {
    font-size: 15px;
    font-weight: 600;
  }

  .san-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
  }

  .pem-block {
    margin-top: 14px;
    border: 1px solid var(--art-card-border);
    border-radius: 8px;
    overflow: hidden;
  }

  .pem-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: 600;
    background: var(--art-gray-100);
  }

  .pem-body {
    max-height: 220px;
    margin: 0;
    padding: 10px;
    overflow: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    color: var(--art-gray-700);
  }

  .export-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-top: 14px;
  }

  @media (max-width: 600px) {
    .export-wrap :deep(.el-select),
    .export-wrap :deep(.el-input) {
      width: 100%;
    }
  }
</style>
