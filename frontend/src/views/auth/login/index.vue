<!--
  登录页
  =========================================================
  视觉规范见 AGENTS 6.0（shadcn/ui 默认设计语言）：
  · 页面底 = --background，卡片 = --card + 1px --border + rounded-lg，不用大投影；
  · 左侧表单、右侧品牌区都只用语义令牌，深浅色自动跟随；
  · 品牌区是「muted 面板 + 点阵纹理」，**不再用蓝紫渐变**——
    那种渐变是最典型的「AI 生成」观感，也和 shadcn 的中性配色冲突；
  · 窄屏（≤900px）隐藏品牌区，卡片收成单列，不出现横向滚动。
-->
<template>
  <div class="login-page">
    <div class="login-card">
      <!-- 左：登录表单 -->
      <section class="form-side">
        <div class="form-top">
          <ElDropdown v-if="languageOptions.length > 1" trigger="click" @command="changeLanguage">
            <div class="lang-switch" role="button" tabindex="0">
              <ArtSvgIcon icon="ri:global-line" class="lang-icon" />
              <span class="lang-text">{{ currentLangLabel }}</span>
            </div>
            <template #dropdown>
              <ElDropdownMenu>
                <ElDropdownItem
                  v-for="item in languageOptions"
                  :key="item.value"
                  :command="item.value"
                >
                  {{ item.label }}
                </ElDropdownItem>
              </ElDropdownMenu>
            </template>
          </ElDropdown>
        </div>

        <h1 class="greeting">{{ $t('login.title') }}</h1>
        <p class="subtitle">{{ subTitleText }}</p>

        <ElForm
          ref="formRef"
          :model="formData"
          :rules="rules"
          class="login-form"
          @keyup.enter="handleSubmit"
        >
          <ElFormItem prop="username">
            <ElInput
              v-model.trim="formData.username"
              class="login-input"
              :placeholder="$t('login.placeholder.username')"
            >
              <template #prefix>
                <ArtSvgIcon icon="ri:user-3-line" class="input-icon" />
              </template>
            </ElInput>
          </ElFormItem>
          <ElFormItem prop="password">
            <ElInput
              v-model.trim="formData.password"
              class="login-input"
              type="password"
              show-password
              autocomplete="off"
              :placeholder="$t('login.placeholder.password')"
            >
              <template #prefix>
                <ArtSvgIcon icon="ri:lock-2-line" class="input-icon" />
              </template>
            </ElInput>
          </ElFormItem>

          <!-- 图形验证码：密码错误达到阈值后才出现，不打扰正常登录 -->
          <ElFormItem v-if="captchaNeeded" prop="captchaCode">
            <div class="captcha-row">
              <ElInput
                v-model.trim="formData.captchaCode"
                class="login-input"
                maxlength="4"
                autocomplete="off"
                placeholder="图形验证码"
              >
                <template #prefix>
                  <ArtSvgIcon icon="ri:shield-keyhole-line" class="input-icon" />
                </template>
              </ElInput>
              <button
                type="button"
                class="captcha-img"
                :title="captchaLoading ? '正在刷新' : '看不清？点击换一张'"
                :disabled="captchaLoading"
                @click="refreshCaptcha"
              >
                <img v-if="captchaImage" :src="captchaImage" alt="图形验证码" />
                <span v-else class="captcha-img-empty">加载中…</span>
              </button>
            </div>
          </ElFormItem>

          <ElButton
            class="login-btn"
            type="primary"
            :loading="loading"
            @click="handleSubmit"
          >
            {{ $t('login.btnText') }}
          </ElButton>
        </ElForm>

        <p class="bottom-hint">忘记密码请联系管理员重置</p>
      </section>

      <!-- 右：品牌区（中性面板 + 点阵纹理，颜色全部走语义令牌） -->
      <aside class="brand-side">
        <div class="brand-row">
          <img v-if="siteStore.logoUrl" class="brand-logo" :src="siteStore.logoUrl" alt="" />
          <span v-else class="brand-name">{{ siteStore.displayName }}</span>
        </div>

        <!-- 线稿插画：证书 + 齿轮 + 弧线，纯内联 SVG（离线可用，不引外链）。
             描边统一用 currentColor，颜色由 .brand-art 的 color 决定。 -->
        <svg class="brand-art" viewBox="0 0 400 320" fill="none" aria-hidden="true">
          <g stroke="currentColor" stroke-opacity="0.55" stroke-width="1.6" stroke-linecap="round">
            <rect x="52" y="66" width="188" height="132" rx="10" />
            <path d="M76 100h84M76 124h140M76 148h116M76 170h72" />
            <circle cx="312" cy="120" r="42" />
            <path d="M292 120l14 14 26-28" stroke-width="2.2" />
            <path d="M312 62v-14M312 192v-12M370 120h14M240 120h14" />
            <path d="M120 232c-26-14-42-42-42-74" />
            <path d="M300 236c22-8 38-28 42-52" />
          </g>
          <g fill="currentColor" fill-opacity="0.3">
            <circle cx="156" cy="258" r="7" />
            <circle cx="212" cy="240" r="4" />
            <circle cx="252" cy="268" r="5" />
            <circle cx="96" cy="34" r="4" />
          </g>
          <g stroke="currentColor" stroke-opacity="0.22" stroke-width="1.2">
            <circle cx="200" cy="176" r="120" />
            <circle cx="200" cy="176" r="152" />
          </g>
        </svg>
      </aside>
    </div>

    <!-- 已开启两步验证：补充 6 位动态验证码 -->
    <ElDialog
      v-model="twofaVisible"
      title="两步验证"
      width="min(400px, 92vw)"
      append-to-body
      destroy-on-close
    >
      <p class="twofa-tip">请输入认证器 App 上显示的 6 位验证码。</p>
      <ElInput
        v-model="twofaCode"
        maxlength="6"
        placeholder="6 位验证码"
        class="custom-height"
        @keyup.enter="submit2fa"
      />
      <template #footer>
        <div class="twofa-footer">
          <ElButton @click="twofaVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="twofaLoading" @click="submit2fa">验证并登录</ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- 系统强制两步验证：首次登录必须先完成绑定 -->
    <ElDialog
      v-model="bindVisible"
      title="绑定两步验证"
      width="min(460px, 94vw)"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
    >
      <p class="twofa-tip">
        系统已开启强制两步验证，首次登录需要先完成绑定。用认证器 App 扫描二维码，或手动输入密钥。
      </p>
      <div class="bind-wrap">
        <div v-if="bindSecret.uri" class="bind-qr">
          <QrcodeVue :value="bindSecret.uri" :size="150" level="M" />
        </div>
        <div class="bind-main">
          <div class="bind-label">密钥</div>
          <div class="bind-secret">{{ bindSecret.secret || '正在获取…' }}</div>
          <ElInput
            v-model="bindCode"
            maxlength="6"
            placeholder="6 位验证码"
            class="mt-3"
            @keyup.enter="submitBind"
          />
        </div>
      </div>
      <template #footer>
        <div class="twofa-footer">
          <ElButton @click="bindVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="bindLoading" @click="submitBind">完成绑定并登录</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import AppConfig from '@/config'
  import { useUserStore } from '@/store/modules/user'
  import { useSiteStore } from '@/store/modules/site'
  import { useI18n } from 'vue-i18n'
  import { HttpError } from '@/utils/http/error'
  import { bind2fa, fetchBind2faSecret, fetchCaptcha, fetchLogin } from '@/api/auth'
  import { fetchAuthSettings } from '@/api/certd'
  import { languageOptions } from '@/locales'
  import type { LanguageEnum } from '@/enums/appEnum'
  import QrcodeVue from 'qrcode.vue'
  import { ElMessage, ElNotification, type FormInstance, type FormRules } from 'element-plus'

  defineOptions({ name: 'Login' })

  const { t, locale } = useI18n()
  const userStore = useUserStore()
  // 站点名称 / 副标题 / Logo 只有一处来源：系统设置 → 站点信息
  const siteStore = useSiteStore()
  siteStore.ensureLoaded()

  const router = useRouter()
  const route = useRoute()

  const systemName = AppConfig.systemInfo.name
  const formRef = ref<FormInstance>()

  const formData = reactive({
    username: '',
    password: '',
    captchaCode: ''
  })

  // ---- 图形验证码：密码错够了才要求，正常登录看不到这一行 ----
  const captchaNeeded = ref(false)
  const captchaImage = ref('')
  const captchaToken = ref('')
  const captchaLoading = ref(false)

  const refreshCaptcha = async () => {
    captchaLoading.value = true
    try {
      const data = await fetchCaptcha()
      captchaImage.value = data?.image || ''
      captchaToken.value = data?.token || ''
      formData.captchaCode = ''
    } catch {
      captchaImage.value = ''
      captchaToken.value = ''
    } finally {
      captchaLoading.value = false
    }
  }

  /** 后端说需要验证码时，把输入行露出来并换一张新图 */
  const requireCaptcha = async () => {
    if (!captchaNeeded.value) captchaNeeded.value = true
    await refreshCaptcha()
  }

  const rules = computed<FormRules>(() => ({
    username: [{ required: true, message: t('login.placeholder.username'), trigger: 'blur' }],
    password: [{ required: true, message: t('login.placeholder.password'), trigger: 'blur' }]
  }))

  const loading = ref(false)

  // 副标题：系统设置里填了就用它，没填退回内置文案
  const siteSubtitle = ref('')
  const subTitleText = computed(() => siteSubtitle.value || t('login.subTitle'))

  const currentLangLabel = computed(
    () => languageOptions.find((item) => item.value === locale.value)?.label || '简体中文'
  )

  const changeLanguage = (lang: LanguageEnum) => {
    if (locale.value === lang) return
    locale.value = lang
    userStore.setLanguage(lang)
  }

  // 两步验证（账号已开启 2FA）
  const twofaVisible = ref(false)
  const twofaCode = ref('')
  const twofaLoading = ref(false)
  const pendingAuth = ref<{ userName: string; password: string }>({ userName: '', password: '' })

  // 强制绑定两步验证（系统设置开启 force2fa 且账号未绑定）
  const bindVisible = ref(false)
  const bindToken = ref('')
  const bindCode = ref('')
  const bindLoading = ref(false)
  const bindSecret = reactive({ secret: '', uri: '' })

  onMounted(async () => {
    try {
      const site = await fetchAuthSettings()
      siteSubtitle.value = site?.subtitle || ''
    } catch {
      siteSubtitle.value = ''
    }
  })

  /** 写入令牌并跳转，正常登录与完成 2FA 绑定共用 */
  const finishLogin = (data: { token?: string; refreshToken?: string }) => {
    if (!data?.token) {
      throw new Error('Login failed - no token received')
    }
    userStore.setToken(data.token, data.refreshToken)
    userStore.setLoginStatus(true)
    showLoginSuccessNotice()

    const redirect = route.query.redirect as string
    router.push(redirect || '/')
  }

  // 登录
  const handleSubmit = async () => {
    if (!formRef.value) return

    try {
      const valid = await formRef.value.validate()
      if (!valid) return

      if (captchaNeeded.value && !formData.captchaCode) {
        ElMessage.warning('请输入图形验证码')
        return
      }

      loading.value = true

      const { username, password, captchaCode } = formData
      const res = await fetchLogin({
        userName: username,
        password,
        ...(captchaNeeded.value
          ? { captchaCode, captchaToken: captchaToken.value }
          : {})
      })

      // 账号开了两步验证：先弹验证码框，密码不再重复提交
      if (res?.need2fa) {
        pendingAuth.value = { userName: username, password }
        twofaCode.value = ''
        twofaVisible.value = true
        return
      }

      // 系统强制 2FA 且未绑定：只能拿到绑定令牌，先完成绑定
      if (res?.needBind2fa) {
        bindToken.value = res.bindToken || ''
        bindCode.value = ''
        await loadBindSecret()
        bindVisible.value = true
        return
      }

      finishLogin(res)
    } catch (error) {
      // 密码错误 / 验证码错误：后端会带 needCaptcha，立刻把验证码行露出来
      const needCaptcha = (error as any)?.data?.needCaptcha
      if (needCaptcha) {
        await requireCaptcha()
      } else if (!(error instanceof HttpError)) {
        console.error('[Login] Unexpected error:', error)
      }
    } finally {
      loading.value = false
    }
  }

  const loadBindSecret = async () => {
    bindLoading.value = true
    try {
      const data = await fetchBind2faSecret(bindToken.value)
      bindSecret.secret = data.secret
      bindSecret.uri = data.uri
    } finally {
      bindLoading.value = false
    }
  }

  const submit2fa = async () => {
    const code = twofaCode.value.trim()
    if (!/^\d{6}$/.test(code)) {
      ElMessage.warning('请输入 6 位验证码')
      return
    }
    twofaLoading.value = true
    try {
      const res = await fetchLogin({ ...pendingAuth.value, code })
      finishLogin(res)
      twofaVisible.value = false
    } catch (error) {
      if (!(error instanceof HttpError)) console.error('[Login] 2FA error:', error)
    } finally {
      twofaLoading.value = false
    }
  }

  const submitBind = async () => {
    const code = bindCode.value.trim()
    if (!/^\d{6}$/.test(code)) {
      ElMessage.warning('请输入 6 位验证码')
      return
    }
    bindLoading.value = true
    try {
      const data = await bind2fa(bindToken.value, code)
      finishLogin(data)
      bindVisible.value = false
    } catch (error) {
      if (!(error instanceof HttpError)) console.error('[Login] bind 2FA error:', error)
    } finally {
      bindLoading.value = false
    }
  }

  // 登录成功提示
  const showLoginSuccessNotice = () => {
    setTimeout(() => {
      ElNotification({
        title: t('login.success.title'),
        type: 'success',
        duration: 2500,
        zIndex: 10000,
        message: `${t('login.success.message')}, ${systemName}!`
      })
    }, 1000)
  }
</script>

<style scoped>
  /* ================= 页面与卡片 ================= */
  .login-page {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    min-height: 100vh;
    padding: 24px;
    /* 和内容区同一套：浅灰画布 + 白卡片，卡片才立得住 */
    background: var(--canvas);
  }

  .login-card {
    display: flex;
    width: 880px;
    max-width: 100%;
    min-height: 440px;
    overflow: hidden;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
  }

  /* ================= 左：表单 ================= */
  .form-side {
    display: flex;
    flex: 0 0 400px;
    flex-direction: column;
    padding: 28px 40px 24px;
    box-sizing: border-box;
  }

  .form-top {
    display: flex;
    justify-content: flex-end;
    min-height: 24px;
  }

  .lang-switch {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    font-size: 12px;
    color: var(--muted-foreground);
    cursor: pointer;
    outline: none;
    transition: color 0.15s ease;
  }

  .lang-switch:hover {
    color: var(--foreground);
  }

  .lang-icon {
    font-size: 14px;
    color: var(--muted-foreground);
  }

  .greeting {
    margin: 14px 0 0;
    font-size: 26px;
    font-weight: 600;
    line-height: 1.25;
    letter-spacing: -0.02em;
    color: var(--foreground);
  }

  /* 副标题允许换两行：原来 nowrap + 省略号，长文案会被截在半句上 */
  .subtitle {
    display: -webkit-box;
    margin: 8px 0 0;
    overflow: hidden;
    font-size: 13.5px;
    line-height: 1.6;
    color: var(--muted-foreground);
    text-overflow: ellipsis;
    white-space: normal;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }

  .login-form {
    margin-top: 28px;
  }

  .login-form :deep(.el-form-item) {
    margin-bottom: 14px;
  }

  /*
   * 登录输入框高度 40px（比全局 36px 大一档：登录是唯一的「焦点页」，
   * 大一号更好点）。配色与焦点环仍走全局 shadcn 规则，这里只覆盖尺寸。
   */
  .login-input :deep(.el-input__wrapper) {
    height: 40px;
    padding: 0 12px;
    background: transparent;
    border-radius: var(--radius-md);
    box-shadow: inset 0 0 0 1px var(--input);
  }

  .login-input :deep(.el-input__wrapper:hover) {
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--foreground) 25%, transparent);
  }

  .login-input :deep(.el-input__wrapper.is-focus) {
    box-shadow:
      inset 0 0 0 1px var(--ring),
      0 0 0 3px color-mix(in srgb, var(--ring) 15%, transparent);
  }

  .login-input :deep(.el-input__inner) {
    height: 40px;
    font-size: 14px;
    color: var(--foreground);
  }

  .login-input :deep(.el-input__inner::placeholder) {
    color: var(--muted-foreground);
  }

  .login-input :deep(.input-icon) {
    margin-right: 8px;
    font-size: 15px;
    color: var(--muted-foreground);
  }

  .login-btn {
    width: 100%;
    height: 40px !important;
    margin-top: 10px;
    font-size: 14px;
    font-weight: 500;
    border-radius: var(--radius-md);
  }

  /* ---- 图形验证码 ---- */
  .captcha-row {
    display: flex;
    gap: 10px;
    align-items: center;
    width: 100%;
  }

  .captcha-img {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 108px;
    height: 40px;
    padding: 0;
    overflow: hidden;
    cursor: pointer;
    background: var(--muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    transition: border-color 0.16s ease;
  }

  .captcha-img:hover {
    border-color: var(--ring);
  }

  .captcha-img img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .captcha-img-empty {
    font-size: 12px;
    color: var(--muted-foreground);
  }

  .bottom-hint {
    margin: auto 0 0;
    padding-top: 20px;
    font-size: 12px;
    color: var(--muted-foreground);
    text-align: center;
  }

  /* ================= 右：品牌区 ================= */
  /*
   * 中性面板 + 点阵纹理。点阵用 radial-gradient 画「点」，
   * 不是装饰性的颜色渐变（那是最典型的 AI 观感，shadcn 明确不用）。
   * 面板色取 --muted，深浅色模式下都自动跟随，不需要第二套暗色覆盖。
   */
  .brand-side {
    position: relative;
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    min-width: 0;
    padding: 28px 32px;
    overflow: hidden;
    color: var(--muted-foreground);
    /* 面板比卡片再深一档、又比页面底色浅一档：三块颜色各不相同，卡片才有层次 */
    background-color: color-mix(in srgb, var(--foreground) 4%, var(--card));
    background-image: radial-gradient(var(--border) 1px, transparent 1px);
    background-size: 16px 16px;
    border-left: 1px solid var(--border);
  }

  .brand-row {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    min-height: 32px;
  }

  .brand-name {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--foreground);
  }

  .brand-logo {
    max-width: 190px;
    max-height: 32px;
    object-fit: contain;
  }

  .brand-art {
    position: absolute;
    inset: 72px 32px 32px;
    width: auto;
    height: auto;
    /* 线稿要看得见，但仍是「中性灰线条」：0.32 在浅灰底上几乎消失 */
    opacity: 1;
  }

  /* ================= 弹窗内的小样式 ================= */
  .twofa-tip {
    margin: 0 0 12px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--muted-foreground);
  }

  .twofa-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .bind-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: flex-start;
  }

  /* 二维码必须留白：背景不能跟卡片同色，否则扫码器读不出来 */
  .bind-qr {
    flex: 0 0 auto;
    padding: 8px;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
  }

  .bind-main {
    flex: 1 1 170px;
    min-width: 0;
  }

  .bind-label {
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--muted-foreground);
  }

  .bind-secret {
    padding: 6px 8px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.6;
    color: var(--foreground);
    word-break: break-all;
    background: var(--muted);
    border-radius: var(--radius-sm);
  }

  /* ================= 响应式 ================= */
  @media (max-width: 900px) {
    .login-card {
      width: 420px;
      min-height: 0;
    }

    .brand-side {
      display: none;
    }

    .form-side {
      flex: 1 1 auto;
      padding: 24px 24px 20px;
    }
  }

  @media (max-width: 460px) {
    .login-page {
      padding: 12px;
    }

    .greeting {
      font-size: 22px;
    }
  }
</style>
