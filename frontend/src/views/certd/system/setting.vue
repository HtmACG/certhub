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
        <ElTabPane v-if="isAdmin" :label="$t('certd.setting.tabSite')" name="site">
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem :label="$t('certd.setting.siteName')">
                  <ElInput v-model="site.name" placeholder="CertHub" clearable />
                  <p class="field-tip">{{ $t('certd.setting.siteNameTip') }}</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem :label="$t('certd.setting.subtitle')">
                  <ElInput
                    v-model="site.subtitle"
                    :placeholder="$t('certd.setting.subtitlePh')"
                    maxlength="40"
                    show-word-limit
                    clearable
                  />
                  <p class="field-tip">{{ $t('certd.setting.subtitleTip') }}</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem :label="$t('certd.setting.browserTitle')">
                  <ElInput v-model="site.title" :placeholder="$t('certd.setting.browserTitlePh')" />
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
                      :placeholder="$t('certd.setting.logoPh')"
                      clearable
                    />
                    <ElUpload
                      :auto-upload="false"
                      :show-file-list="false"
                      accept="image/png,image/jpeg,image/svg+xml,image/webp,image/gif"
                      :on-change="onLogoChange"
                    >
                      <ElButton>{{ $t('certd.setting.uploadImage') }}</ElButton>
                    </ElUpload>
                    <ElButton link type="danger" :disabled="!site.logo" @click="resetLogo">
                      {{ $t('certd.setting.resetDefault') }}
                    </ElButton>
                  </div>
                  <p class="field-tip">{{ $t('certd.setting.logoTip', { kb: LOGO_MAX_KB }) }}</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem :label="$t('certd.setting.copyright')">
                  <ElInput v-model="site.copyright" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem :label="$t('certd.setting.openRegister')">
                  <ElSwitch v-model="site.registerEnabled" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="12" :lg="8">
                <ElFormItem :label="$t('certd.setting.hideBrand')">
                  <ElSwitch v-model="site.hideBrand" />
                </ElFormItem>
              </ElCol>
              <ElCol :span="24">
                <ElFormItem :label="$t('certd.setting.loginNotice')">
                  <ElInput v-model="site.loginNotice" type="textarea" :autosize="{ minRows: 2 }" />
                </ElFormItem>
              </ElCol>
              <ElCol :span="24">
                <ElFormItem :label="$t('certd.setting.homeNotice')">
                  <ElInput v-model="site.homeNotice" type="textarea" :autosize="{ minRows: 2 }" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <ElButton type="primary" :loading="saving === 'site'" @click="save('site')">{{ $t('certd.common.save') }}</ElButton>
          </ElForm>
        </ElTabPane>

        <!--
          「安全」页签对所有登录用户可见：
          上半部分是自己的账号（原「账号与安全」页，已合并进来），
          下半部分的登录策略只有管理员能改。
        -->
        <ElTabPane :label="$t('certd.setting.tabSecurity')" name="security">
          <AccountSecurity />

          <ElForm v-if="isAdmin" label-position="top" class="setting-form policy-form">
            <div class="sec-title">
              {{ $t('certd.setting.policyTitle') }}
              <span class="sec-title-tip">{{ $t('certd.setting.policyScope') }}</span>
            </div>
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.loginFailLimit')">
                  <ElInputNumber v-model="security.loginFailLimit" :min="0" :max="50" class="w-full" />
                  <p class="field-tip">{{ $t('certd.setting.loginFailLimitTip') }}</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.lockMinutes')">
                  <ElInputNumber v-model="security.lockMinutes" :min="1" :max="1440" class="w-full" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.force2fa')">
                  <ElSwitch v-model="security.force2fa" />
                  <p class="field-tip">{{ $t('certd.setting.force2faTip') }}</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.captchaEnabled')">
                  <ElSwitch v-model="security.captchaEnabled" />
                  <p class="field-tip">{{ $t('certd.setting.captchaEnabledTip') }}</p>
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.captchaAfter')">
                  <ElInputNumber
                    v-model="security.captchaAfter"
                    :min="1"
                    :max="10"
                    :disabled="!security.captchaEnabled"
                    class="w-full"
                  />
                  <p class="field-tip">{{ $t('certd.setting.captchaAfterTip') }}</p>
                </ElFormItem>
              </ElCol>
            </ElRow>
            <ElButton type="primary" :loading="saving === 'security'" @click="save('security')">
              {{ $t('certd.common.save') }}
            </ElButton>
          </ElForm>
        </ElTabPane>

        <ElTabPane v-if="isAdmin" :label="$t('certd.setting.tabNotify')" name="notify">
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.expireDays')">
                  <ElInputNumber v-model="notify.expireDays" :min="1" :max="90" class="w-full" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <p class="form-tip">{{ $t('certd.setting.expireDaysTip') }}</p>
            <ElButton type="primary" :loading="saving === 'notify'" @click="save('notify')">{{ $t('certd.common.save') }}</ElButton>
          </ElForm>
        </ElTabPane>

        <ElTabPane v-if="isAdmin" :label="$t('certd.setting.tabNetwork')" name="network">
          <ElAlert type="info" :closable="false" class="mb-3">{{ $t('certd.setting.proxyAlert') }}</ElAlert>
          <ElForm label-position="top" class="setting-form">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.httpProxy')">
                  <ElInput v-model="network.httpProxy" placeholder="http://127.0.0.1:7890" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12" :md="8">
                <ElFormItem :label="$t('certd.setting.httpsProxy')">
                  <ElInput v-model="network.httpsProxy" placeholder="http://127.0.0.1:7890" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="24" :md="8">
                <ElFormItem :label="$t('certd.setting.noProxy')">
                  <ElInput v-model="network.noProxy" placeholder="localhost,127.0.0.1,192.168.*" />
                </ElFormItem>
              </ElCol>
            </ElRow>

            <ElDivider content-position="left">{{ $t('certd.setting.reverseProxies') }}</ElDivider>
            <p class="form-tip">{{ $t('certd.setting.reverseTip') }}</p>
            <div class="proxy-map">
              <div v-for="(row, index) in proxyRows" :key="index" class="proxy-row">
                <ElInput v-model="row.key" placeholder="acme-v02.api.letsencrypt.org" />
                <ElInput v-model="row.value" :placeholder="$t('certd.setting.reverseValuePh')" />
                <ElButton link type="danger" @click="removeProxyRow(index)">{{ $t('certd.common.delete') }}</ElButton>
              </div>
              <ElButton size="small" @click="addProxyRow">{{ $t('certd.setting.addMapping') }}</ElButton>
            </div>

            <ElDivider content-position="left">{{ $t('certd.setting.connectivity') }}</ElDivider>
            <div class="test-wrap">
              <ElSelect v-model="testTarget" class="w-64">
                <ElOption
                  v-for="item in TEST_TARGETS"
                  :key="item.url"
                  :label="item.name"
                  :value="item.url"
                />
              </ElSelect>
              <ElButton :loading="testing" @click="runTest">{{ $t('certd.setting.runTest') }}</ElButton>
            </div>
            <div v-if="testResult" class="test-result">
              <ElTag :type="testResult.verdict ? 'success' : 'warning'" effect="light">
                {{ testResult.verdict }}
              </ElTag>
              <div class="probe-list">
                <div class="probe-item">
                  <span>{{ $t('certd.setting.direct') }}</span>
                  <ElTag :type="probeType(testResult.direct)" size="small" effect="plain">
                    {{ probeText(testResult.direct) }}
                  </ElTag>
                </div>
                <div v-if="testResult.proxied" class="probe-item">
                  <span>{{ $t('certd.setting.viaProxy') }}</span>
                  <ElTag :type="probeType(testResult.proxied)" size="small" effect="plain">
                    {{ probeText(testResult.proxied) }}
                  </ElTag>
                </div>
                <div v-if="testResult.reverse" class="probe-item">
                  <span>{{ $t('certd.setting.viaReverse') }}</span>
                  <ElTag :type="probeType(testResult.reverse)" size="small" effect="plain">
                    {{ probeText(testResult.reverse) }}
                  </ElTag>
                </div>
              </div>
            </div>

            <ElButton type="primary" :loading="saving === 'network'" @click="save('network')">{{ $t('certd.common.save') }}</ElButton>
          </ElForm>
        </ElTabPane>

        <!-- 项目信息：只读，内容来自后端 /api/settings 的 about（改后端常量即可，不用动前端） -->
        <ElTabPane :label="$t('certd.setting.tabAbout')" name="about">
          <div class="about-panel">
            <div class="about-brand">
              <ArtLogo :size="42" />
              <div class="about-brand-text">
                <div class="about-name">{{ about.name || 'CertHub' }}</div>
                <div class="about-sub">
                  {{ $t('certd.setting.version') }} <b>{{ about.version || '-' }}</b>
                  <span class="about-dot">·</span>
                  {{ $t('certd.setting.webBuild') }} v{{ webVersion }}
                </div>
              </div>
            </div>

            <ElDescriptions :column="1" border class="about-desc">
              <ElDescriptionsItem :label="$t('certd.setting.projectName')">{{ about.name || 'CertHub' }}</ElDescriptionsItem>
              <ElDescriptionsItem :label="$t('certd.setting.version')">{{ about.version || '-' }}</ElDescriptionsItem>
              <ElDescriptionsItem :label="$t('certd.setting.webBuild')">v{{ webVersion }}</ElDescriptionsItem>
              <ElDescriptionsItem :label="$t('certd.setting.developer')">{{ about.developer || '-' }}</ElDescriptionsItem>
              <ElDescriptionsItem :label="$t('certd.setting.email')">
                <ElLink
                  v-if="about.email"
                  type="primary"
                  :underline="false"
                  :href="'mailto:' + about.email"
                >
                  <ArtSvgIcon icon="ri:mail-line" class="mr-1" />{{ about.email }}
                </ElLink>
                <span v-else>-</span>
              </ElDescriptionsItem>
              <ElDescriptionsItem :label="$t('certd.setting.website')">
                <ElLink
                  v-if="about.website"
                  type="primary"
                  :underline="false"
                  :href="about.websiteUrl || 'http://' + about.website"
                  target="_blank"
                  rel="noopener"
                >
                  <ArtSvgIcon icon="ri:global-line" class="mr-1" />{{ about.website }}
                </ElLink>
                <span v-else>-</span>
              </ElDescriptionsItem>
              <ElDescriptionsItem v-if="site.copyright" :label="$t('certd.setting.copyright')">
                {{ site.copyright }}
              </ElDescriptionsItem>
            </ElDescriptions>

            <p class="about-tip">{{ $t('certd.setting.aboutTip') }}</p>
          </div>
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
  import AccountSecurity from './components/account-security.vue'
  import { $t } from '@/locales'

  defineOptions({ name: 'CertdSystemSetting' })

  const userStore = useUserStore()
  const siteStore = useSiteStore()
  const isAdmin = computed(() => userStore.info?.role === 'admin')
  const route = useRoute()

  /** 上传 Logo 的体积上限（换算成 data URI 后还要再放大 1/3，别把设置项撑爆） */
  const LOGO_MAX_KB = 256
  const logoBroken = ref(false)

  const loading = ref(false)
  const saving = ref('')
  // 支持 ?tab=security 直达（老的「账号与安全」入口已并进来，会带这个参数跳过来）
  const activeTab = ref(String(route.query.tab || 'site'))

  const site = reactive<any>({})
  /** 项目信息（只读，来自后端 about） */
  const about = reactive<any>({})
  /** 前端构建版本（VITE_VERSION，构建时写进产物） */
  const webVersion = __APP_VERSION__
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
      Object.assign(about, data.about || {})
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
      ElMessage.success($t('certd.common.saved'))
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
      ElMessage.warning($t('certd.setting.pickImage'))
      return
    }
    if (raw.size > LOGO_MAX_KB * 1024) {
      ElMessage.warning($t('certd.setting.imageTooLarge', { kb: LOGO_MAX_KB }))
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
    if (!probe) return $t('certd.setting.probeUntested')
    if (probe.ok) return $t('certd.setting.probeOk', { status: probe.status, ms: probe.ms })
    return (probe.error || $t('certd.setting.probeFail')) + (probe.ms ? ' · ' + probe.ms + 'ms' : '')
  }

  onMounted(() => {
    // 普通用户进不来管理页签，落错页签就退到「安全」
    const adminTabs = ['site', 'notify', 'network']
    if (!isAdmin.value && adminTabs.includes(activeTab.value)) {
      activeTab.value = 'security'
    }
    load()
  })
</script>

<style scoped>
  .setting-form {
    max-width: 1080px;
  }

  /* 「安全」页签里的登录策略：跟上面的「我的账号」拉开距离，说明这是全站设置 */
  .policy-form {
    padding-top: 18px;
    margin-top: 4px;
    border-top: 1px solid var(--art-card-border);
  }

  .sec-title {
    display: flex;
    gap: 8px;
    align-items: baseline;
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 600;
    color: var(--foreground);
  }

  .sec-title-tip {
    font-size: 12px;
    font-weight: 400;
    color: var(--art-gray-500);
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

  /* ---------------- 项目信息（只读） ---------------- */
  .about-panel {
    max-width: 720px;
  }

  .about-brand {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 14px 16px;
    margin-bottom: 14px;
    background: var(--muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
  }

  .about-brand-text {
    min-width: 0;
  }

  .about-name {
    font-size: 15px;
    font-weight: 600;
    color: var(--art-gray-800);
  }

  .about-sub {
    margin-top: 4px;
    font-size: 12.5px;
    color: var(--art-gray-500);
  }

  .about-sub b {
    font-weight: 600;
    color: var(--art-gray-700);
  }

  .about-dot {
    margin: 0 6px;
    color: var(--art-gray-400);
  }

  .about-desc :deep(.el-descriptions__label) {
    width: 110px;
    white-space: nowrap;
  }

  .about-desc :deep(.el-descriptions__content) {
    word-break: break-all;
  }

  .about-tip {
    margin: 12px 0 0;
    font-size: 12px;
    line-height: 1.6;
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
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);

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
