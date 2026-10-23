<!--
  系统设置（管理员）
  =========================================================
  按「站点 / 安全 / 通知 / 网络」分区，每个分区独立保存，
  避免一次改动没填完就整表单失败。
  网络分区带「连通性测试」：直连 / HTTP 代理 / 反向代理三条路一次摆出来。
-->
<template>
  <div class="certd-setting art-full-height g-scope" v-loading="loading">
    <ElCard class="art-card" shadow="never">
      <ElTabs v-model="activeTab">
        <ElTabPane label="站点信息" name="site">
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem label="站点名称">
                  <ElInput v-model="site.name" placeholder="CertHub" clearable />
                  <p class="field-tip">显示在侧边栏 / 顶部栏标题，留空则用内置名称</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem label="副标题">
                  <ElInput
                    v-model="site.subtitle"
                    placeholder="例如：证书自动化管理系统"
                    maxlength="40"
                    show-word-limit
                    clearable
                  />
                  <p class="field-tip">显示在站点名称下方，留空就不显示这一行</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem label="浏览器标题">
                  <ElInput v-model="site.title" placeholder="CertHub 证书管理系统" />
                </ElFormItem>
              </ElCol>
              <ElCol :span="24">
                <ElFormItem label="Logo">
                  <div class="logo-row">
                    <span class="logo-preview">
                      <img
                        v-if="site.logo && !logoBroken"
                        :src="site.logo"
                        alt="logo"
                        @error="logoBroken = true"
                      />
                      <ArtLogo v-else :size="34" />
                    </span>
                    <ElInput
                      v-model="site.logo"
                      class="logo-input"
                      placeholder="留空用内置图标，也可粘贴图片地址"
                      clearable
                    />
                    <ElUpload
                      :auto-upload="false"
                      :show-file-list="false"
                      accept="image/png,image/jpeg,image/svg+xml,image/webp,image/gif"
                      :on-change="onLogoChange"
                    >
                      <ElButton>上传图片</ElButton>
                    </ElUpload>
                    <ElButton link type="danger" :disabled="!site.logo" @click="resetLogo">
                      恢复默认
                    </ElButton>
                  </div>
                  <p class="field-tip">
                    支持 PNG / JPG / SVG / WebP，建议正方形，≤ {{ LOGO_MAX_KB }}KB；
                    上传的图会转成 data URI 存进站点设置，不依赖外部图床。
                  </p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem label="版权信息">
                  <ElInput v-model="site.copyright" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem label="开放注册">
                  <ElSwitch v-model="site.registerEnabled" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem label="隐藏品牌">
                  <ElSwitch v-model="site.hideBrand" />
                </ElFormItem>
              </ElCol>
              <ElCol :span="24">
                <ElFormItem label="登录页公告">
                  <ElInput v-model="site.loginNotice" type="textarea" :autosize="{ minRows: 2 }" />
                </ElFormItem>
              </ElCol>
              <ElCol :span="24">
                <ElFormItem label="工作台公告">
                  <ElInput v-model="site.homeNotice" type="textarea" :autosize="{ minRows: 2 }" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <ElButton type="primary" :loading="saving === 'site'" @click="save('site')">保存</ElButton>
          </ElForm>
        </ElTabPane>

        <ElTabPane v-if="isAdmin" label="安全" name="security">
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem label="登录失败上限（次）">
                  <ElInputNumber v-model="security.loginFailLimit" :min="0" :max="50" class="w-full" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem label="锁定时长（分钟）">
                  <ElInputNumber v-model="security.lockMinutes" :min="1" :max="1440" class="w-full" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem label="强制两步验证">
                  <ElSwitch v-model="security.force2fa" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <ElButton type="primary" :loading="saving === 'security'" @click="save('security')">保存</ElButton>
          </ElForm>
        </ElTabPane>

        <ElTabPane label="到期提醒" name="notify">
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem label="提前提醒天数">
                  <ElInputNumber v-model="notify.expireDays" :min="1" :max="90" class="w-full" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <p class="form-tip">
              证书剩余天数小于该值时，调度器会通过「通知渠道」里设为默认的渠道推送提醒。
            </p>
            <ElButton type="primary" :loading="saving === 'notify'" @click="save('notify')">保存</ElButton>
          </ElForm>
        </ElTabPane>

        <ElTabPane v-if="isAdmin" label="网络代理" name="network">
          <ElAlert type="info" :closable="false" class="mb-3">
            语义与环境变量一致：httpProxy / httpsProxy / noProxy。填了代理就默认全部出网请求走代理，
            noProxy 命中的直连（支持 localhost、.example.com、192.168.*、10.0.0.0/8）。
          </ElAlert>
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem label="HTTP 代理">
                  <ElInput v-model="network.httpProxy" placeholder="http://127.0.0.1:7890" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem label="HTTPS 代理">
                  <ElInput v-model="network.httpsProxy" placeholder="http://127.0.0.1:7890" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="24" :md="8">
                <ElFormItem label="不走代理（noProxy）">
                  <ElInput v-model="network.noProxy" placeholder="localhost,127.0.0.1,192.168.*" />
                </ElFormItem>
              </ElCol>
            </ElRow>

            <ElDivider content-position="left">反向代理域名</ElDivider>
            <p class="form-tip">
              只在传输层改地址，ACME 的 JWS 里仍然是原始 URL。留空使用内置默认。
            </p>
            <div class="proxy-map">
              <div v-for="(row, index) in proxyRows" :key="index" class="proxy-row">
                <ElInput v-model="row.key" placeholder="acme-v02.api.letsencrypt.org" />
                <ElInput v-model="row.value" placeholder="反代域名，留空表示禁用" />
                <ElButton link type="danger" @click="removeProxyRow(index)">删除</ElButton>
              </div>
              <ElButton size="small" @click="addProxyRow">新增映射</ElButton>
            </div>

            <ElDivider content-position="left">连通性测试</ElDivider>
            <div class="test-wrap">
              <ElSelect v-model="testTarget" class="w-64">
                <ElOption
                  v-for="item in TEST_TARGETS"
                  :key="item.url"
                  :label="item.name"
                  :value="item.url"
                />
              </ElSelect>
              <ElButton :loading="testing" @click="runTest">测试连通性</ElButton>
            </div>
            <div v-if="testResult" class="test-result">
              <ElTag :type="testResult.verdict ? 'success' : 'warning'" effect="light">
                {{ testResult.verdict }}
              </ElTag>
              <div class="probe-list">
                <div class="probe-item">
                  <span>直连</span>
                  <ElTag :type="probeType(testResult.direct)" size="small" effect="plain">
                    {{ probeText(testResult.direct) }}
                  </ElTag>
                </div>
                <div v-if="testResult.proxied" class="probe-item">
                  <span>HTTP 代理</span>
                  <ElTag :type="probeType(testResult.proxied)" size="small" effect="plain">
                    {{ probeText(testResult.proxied) }}
                  </ElTag>
                </div>
                <div v-if="testResult.reverse" class="probe-item">
                  <span>反向代理</span>
                  <ElTag :type="probeType(testResult.reverse)" size="small" effect="plain">
                    {{ probeText(testResult.reverse) }}
                  </ElTag>
                </div>
              </div>
            </div>

            <ElButton type="primary" :loading="saving === 'network'" @click="save('network')">保存</ElButton>
          </ElForm>
        </ElTabPane>
      </ElTabs>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { fetchSettings, testProxy, updateSettings } from '@/api/certd'
  import { useUserStore } from '@/store/modules/user'
  import { useSiteStore } from '@/store/modules/site'
  import { ElMessage } from 'element-plus'
  import type { UploadFile } from 'element-plus'
  import ArtLogo from '@/components/core/base/art-logo/index.vue'

  defineOptions({ name: 'CertdSystemSetting' })

  const userStore = useUserStore()
  const siteStore = useSiteStore()
  const isAdmin = computed(() => userStore.info?.role === 'admin')

  /** 上传 Logo 的体积上限（换算成 data URI 后还要再放大 1/3，别把设置项撑爆） */
  const LOGO_MAX_KB = 256
  const logoBroken = ref(false)

  const loading = ref(false)
  const saving = ref('')
  const activeTab = ref('site')

  const site = reactive<any>({})
  const security = reactive<any>({})
  const notify = reactive<any>({})
  const network = reactive<any>({})

  const proxyRows = ref<{ key: string; value: string }[]>([])

  const TEST_TARGETS = [
    { name: "Google Trust Services", url: 'https://dv.acme-v02.api.pki.goog/directory' },
    { name: 'ZeroSSL', url: 'https://acme.zerossl.com/v2/DV90' },
    { name: "Let's Encrypt", url: 'https://acme-v02.api.letsencrypt.org/directory' },
  ]

  const testTarget = ref(TEST_TARGETS[0].url)
  const testing = ref(false)
  const testResult = ref<any>(null)

  const load = async () => {
    loading.value = true
    try {
      const data = await fetchSettings()
      Object.assign(site, data.site || {})
      Object.assign(security, data.security || {})
      Object.assign(notify, data.notify || {})
      Object.assign(network, data.network || {})
      const custom = (data.network?.reverseProxies || {}) as Record<string, string>
      proxyRows.value = Object.entries(custom).map(([key, value]) => ({ key, value }))
    } finally {
      loading.value = false
    }
  }

  const save = async (key: string) => {
    saving.value = key
    try {
      const source: any = { site, security, notify, network }[key]
      const value = { ...source }
      if (key === 'site') {
        // 标题类字段一律 trim：粘贴最常带首尾空格，显示出来就是「名字后面空一截」
        for (const field of ['name', 'subtitle', 'title', 'logo']) {
          value[field] = String(value[field] ?? '').trim()
        }
      }
      if (key === 'network') {
        // 只提交用户填的映射，内置默认与最终生效值都是后端算的
        value.reverseProxies = proxyRows.value.reduce<Record<string, string>>((acc, row) => {
          if (row.key.trim()) acc[row.key.trim()] = row.value.trim()
          return acc
        }, {})
        delete value.reverseProxyDefaults
        delete value.resolvedReverseProxies
      }
      await updateSettings({ [key]: value })
      if (key === 'site') {
        // 侧边栏 / 顶部栏的标题与 Logo 立刻跟着变，不用刷新页面
        siteStore.apply(value)
      }
      ElMessage.success('已保存')
    } finally {
      saving.value = ''
    }
  }

  /**
   * 选取本地图片后转成 data URI，直接塞进 site.logo
   * （不走上传接口：站点设置本来就是 json 文本，内联图最省事也不会丢）
   */
  const onLogoChange = (file: UploadFile): void => {
    const raw = file.raw as File | undefined
    if (!raw) return
    if (!raw.type.startsWith('image/')) {
      ElMessage.warning('请选择图片文件')
      return
    }
    if (raw.size > LOGO_MAX_KB * 1024) {
      ElMessage.warning(`图片请小于 ${LOGO_MAX_KB}KB`)
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      site.logo = String(reader.result || '')
      logoBroken.value = false
    }
    reader.readAsDataURL(raw)
  }

  // 换了地址（手改或上传）就重新尝试加载一次
  watch(
    () => site.logo,
    () => {
      logoBroken.value = false
    }
  )

  /**
   * 恢复内置图标
   */
  const resetLogo = (): void => {
    site.logo = ''
    logoBroken.value = false
  }

  const addProxyRow = () => {
    proxyRows.value.push({ key: '', value: '' })
  }

  const removeProxyRow = (index: number) => {
    proxyRows.value.splice(index, 1)
  }

  const runTest = async () => {
    testing.value = true
    try {
      testResult.value = await testProxy({
        httpProxy: network.httpProxy,
        httpsProxy: network.httpsProxy,
        target: testTarget.value,
      })
    } finally {
      testing.value = false
    }
  }

  const probeType = (probe: any) => (probe?.ok ? 'success' : 'danger')

  const probeText = (probe: any) => {
    if (!probe) return '未测试'
    if (probe.ok) return '可用 · ' + probe.status + ' · ' + probe.ms + 'ms'
    return (probe.error || '不可用') + (probe.ms ? ' · ' + probe.ms + 'ms' : '')
  }

  onMounted(load)
</script>

<style scoped>
  .setting-form {
    max-width: 1080px;
  }

  .form-tip {
    margin: 0 0 12px;
    font-size: 12px;
    line-height: 1.6;
    color: var(--art-gray-500);
  }

  /* 表单项下面那行灰字说明 */
  .field-tip {
    width: 100%;
    margin: 4px 0 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--art-gray-500);
  }

  .logo-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    width: 100%;
    min-width: 0;
  }

  .logo-preview {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    padding: 3px;
    overflow: hidden;
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: 8px;

    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  }

  .logo-input {
    flex: 1 1 220px;
    min-width: 160px;
  }

  .proxy-map {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 720px;
    margin-bottom: 12px;
  }

  .proxy-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .test-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
  }

  .test-result {
    margin-bottom: 14px;
  }

  .probe-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 8px;
  }

  .probe-item {
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 12px;
    color: var(--art-gray-600);
  }

  @media (max-width: 600px) {
    .proxy-row {
      flex-direction: column;
      align-items: stretch;
    }

    .test-wrap :deep(.el-select) {
      width: 100% !important;
    }
  }
</style>
