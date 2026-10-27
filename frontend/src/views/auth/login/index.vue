<!--
  登录页
  =========================================================
  参照设计稿：浅灰底（#f1f2f5）上居中一张 860×420 的白色卡片，
  左边是表单（右上角语言切换 / 大标题 / 副标题 / 两个输入框 / 主按钮），
  右边是品牌区（蓝紫渐变 + 白色字标 + 浅色线稿插画）。
  窄屏（≤900px）隐藏品牌区，卡片收成单列，不出现横向滚动。
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

      <!-- 右：品牌区（蓝紫渐变） -->
      <aside class="brand-side">
        <div class="brand-row">
          <img v-if="siteStore.logoUrl" class="brand-logo" :src="siteStore.logoUrl" alt="" />
          <span v-else class="brand-name">{{ siteStore.displayName }}</span>
        </div>

        <!-- 线稿插画：证书 + 齿轮 + 弧线，纯内联 SVG（离线可用，不引外链） -->
        <svg class="brand-art" viewBox="0 0 400 320" fill="none" aria-hidden="true">
          <g stroke="#fff" stroke-opacity="0.26" stroke-width="1.6" stroke-linecap="round">
            <rect x="52" y="66" width="188" height="132" rx="10" />
            <path d="M76 100h84M76 124h140M76 148h116M76 170h72" />
            <circle cx="312" cy="120" r="42" />
            <path d="M292 120l14 14 26-28" stroke-width="2.2" />
            <path d="M312 62v-14M312 192v-12M370 120h14M240 120h14" />
            <path d="M120 232c-26-14-42-42-42-74" />
            <path d="M300 236c22-8 38-28 42-52" />
          </g>
          <g fill="#fff" fill-opacity="0.2">
            <circle cx="156" cy="258" r="7" />
            <circle cx="212" cy="240" r="4" />
            <circle cx="252" cy="268" r="5" />
            <circle cx="96" cy="34" r="4" />
          </g>
          <g stroke="#fff" stroke-opacity="0.14" stroke-width="1.2">
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
    background: #f1f2f5;
  }

  .login-card {
    display: flex;
    width: 860px;
    max-width: 100%;
    min-height: 420px;
    overflow: hidden;
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 6px 24px rgb(0 0 0 / 8%);
  }

  /* ================= 左：表单 ================= */
  .form-side {
    display: flex;
    flex: 0 0 380px;
    flex-direction: column;
    padding: 16px 40px 22px;
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
    color: var(--art-gray-500);
    cursor: pointer;
    outline: none;
    transition: color 0.2s;
  }

  .lang-switch:hover {
    color: var(--el-color-primary);
  }

  .lang-icon {
    font-size: 15px;
    color: var(--el-color-primary);
  }

  .greeting {
    margin: 8px 0 0;
    font-size: 28px;
    font-weight: 600;
    line-height: 1.25;
    color: var(--el-color-primary);
  }

  .subtitle {
    margin: 12px 0 0;
    overflow: hidden;
    font-size: 13px;
    line-height: 1.6;
    color: var(--el-color-primary);
    text-overflow: ellipsis;
    white-space: nowrap;
    opacity: 0.82;
  }

  .login-form {
    margin-top: 44px;
  }

  .login-form :deep(.el-form-item) {
    margin-bottom: 17px;
  }

  .login-input :deep(.el-input__wrapper) {
    height: 40px;
    padding: 0 12px;
    background: #fff;
    border-radius: var(--custom-radius);
    box-shadow: inset 0 0 0 1px #e8e8e8;
  }

  .login-input :deep(.el-input__wrapper:hover) {
    box-shadow: inset 0 0 0 1px #d4d4d4;
  }

  .login-input :deep(.el-input__wrapper.is-focus) {
    box-shadow: inset 0 0 0 1px var(--el-color-primary);
  }

  .login-input :deep(.el-input__inner) {
    height: 40px;
    font-size: 13px;
  }

  .login-input :deep(.el-input__inner::placeholder) {
    color: #999;
  }

  .login-input :deep(.input-icon) {
    margin-right: 12px;
    font-size: 16px;
    color: #b9bfc7;
  }

  .login-btn {
    width: 100%;
    height: 40px !important;
    margin-top: 14px;
    font-size: 14px;
    border-radius: var(--custom-radius);
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
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: var(--custom-radius);
    transition: border-color 0.16s ease;
  }

  .captcha-img:hover {
    border-color: var(--el-color-primary);
  }

  .captcha-img img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .captcha-img-empty {
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .bottom-hint {
    margin: auto 0 0;
    padding-top: 22px;
    font-size: 12px;
    color: var(--art-gray-500);
    text-align: center;
  }

  /* ================= 右：品牌区 ================= */
  .brand-side {
    position: relative;
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    min-width: 0;
    padding: 24px;
    overflow: hidden;
    background: linear-gradient(to top right, #6b75ff 0%, #3da2fd 100%);
  }

  .brand-row {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    min-height: 32px;
  }

  .brand-name {
    font-size: 20px;
    font-weight: 600;
    color: #fff;
    letter-spacing: 0.5px;
  }

  .brand-logo {
    max-width: 190px;
    max-height: 32px;
    object-fit: contain;
  }

  .brand-art {
    position: absolute;
    inset: 66px 24px 20px;
    width: auto;
    height: auto;
  }

  /* ================= 弹窗内的小样式 ================= */
  .twofa-tip {
    margin: 0 0 12px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--art-gray-500);
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

  .bind-qr {
    padding: 8px;
    background: #fff;
    border-radius: 8px;
  }

  .bind-main {
    flex: 1;
    min-width: 170px;
  }

  .bind-label {
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .bind-secret {
    padding: 6px 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    line-height: 1.6;
    word-break: break-all;
    background: var(--art-gray-100);
    border-radius: 6px;
  }

  /* ================= 暗色 ================= */
  :global(.dark) .login-page {
    background: #0f1114;
  }

  :global(.dark) .login-card {
    background: #17191d;
    box-shadow: 0 6px 24px rgb(0 0 0 / 55%);
  }

  :global(.dark) .login-input :deep(.el-input__wrapper) {
    background: #1d2025;
    box-shadow: inset 0 0 0 1px #33373d;
  }

  :global(.dark) .login-input :deep(.el-input__wrapper.is-focus) {
    box-shadow: inset 0 0 0 1px var(--el-color-primary);
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
      font-size: 24px;
    }
  }
</style>
