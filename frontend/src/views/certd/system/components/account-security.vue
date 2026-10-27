<!--
  我的账号（系统设置 → 安全）
  =========================================================
  原来独立的「账号与安全」页，按需求合并进系统设置的「安全」页签。
  这里只放**跟当前登录用户自己有关**的东西：
  基本资料 / 修改密码 / 两步验证。
  与全站有关的登录策略（失败上限、锁定时长、图形验证码）留在 setting.vue，
  并且只有管理员看得到。
-->
<template>
  <div class="account-security">
    <ElRow :gutter="16">
      <ElCol :xs="24" :sm="24" :md="12" :lg="12">
        <div class="sec-block">
          <div class="sec-title">基本资料</div>
          <ElForm label-position="top">
            <ElRow :gutter="16">
              <ElCol :xs="24" :sm="12">
                <ElFormItem label="用户名">
                  <ElInput :model-value="info.userName" disabled />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12">
                <ElFormItem label="角色">
                  <ElInput :model-value="info.role === 'admin' ? '管理员' : '普通用户'" disabled />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12">
                <ElFormItem label="昵称">
                  <ElInput v-model="profile.nickname" />
                </ElFormItem>
              </ElCol>
              <ElCol :xs="24" :sm="12">
                <ElFormItem label="邮箱">
                  <ElInput v-model="profile.email" placeholder="到期提醒也会发到这里" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <ElButton type="primary" :loading="savingProfile" @click="saveProfile">保存资料</ElButton>
          </ElForm>
        </div>

        <div class="sec-block">
          <div class="sec-title">修改密码</div>
          <ElForm label-position="top">
            <ElFormItem label="当前密码">
              <ElInput v-model="password.oldPassword" type="password" show-password autocomplete="off" />
            </ElFormItem>
            <ElFormItem label="新密码">
              <ElInput
                v-model="password.newPassword"
                type="password"
                show-password
                autocomplete="new-password"
              />
              <div class="pwd-hint">
                <div v-for="item in pwdChecks" :key="item.text" class="pwd-check" :class="{ ok: item.ok }">
                  <ArtSvgIcon
                    :icon="item.ok ? 'ri:checkbox-circle-fill' : 'ri:checkbox-blank-circle-line'"
                    class="pwd-check-icon"
                  />
                  {{ item.text }}
                </div>
              </div>
            </ElFormItem>
            <ElFormItem label="确认新密码">
              <ElInput
                v-model="password.confirmPassword"
                type="password"
                show-password
                autocomplete="new-password"
                @keyup.enter="savePassword"
              />
            </ElFormItem>
            <ElButton type="primary" :loading="savingPassword" @click="savePassword">修改密码</ElButton>
            <span class="pwd-tip">修改成功后需要用新密码重新登录</span>
          </ElForm>
        </div>
      </ElCol>

      <ElCol :xs="24" :sm="24" :md="12" :lg="12">
        <div class="sec-block" v-loading="loadingTotp">
          <div class="sec-title">
            两步验证
            <ElTag :type="info.totpEnabled ? 'success' : 'info'" size="small" effect="light">
              {{ info.totpEnabled ? '已开启' : '未开启' }}
            </ElTag>
          </div>

          <!-- 未开启：扫码绑定 -->
          <div v-if="!info.totpEnabled">
            <p class="form-tip">
              用 Google Authenticator / Microsoft Authenticator / 1Password 等 App
              <b>扫描右侧二维码</b>，添加后填入 App 上的 6 位验证码即可开启。
            </p>
            <div class="totp-wrap">
              <div class="totp-qr">
                <QrcodeVue v-if="totp.uri" :value="totp.uri" :size="150" level="M" />
                <div v-else class="totp-qr-empty">二维码生成中…</div>
                <div class="totp-qr-label">{{ issuerLabel }}</div>
              </div>
              <div class="totp-main">
                <div class="totp-label">扫描不了？手动输入密钥</div>
                <div class="totp-secret">
                  <span class="mono">{{ totp.secret || '—' }}</span>
                  <ElButton link size="small" :disabled="!totp.secret" @click="copySecret">
                    复制
                  </ElButton>
                </div>
                <ElInput
                  v-model="totpCode"
                  placeholder="6 位验证码"
                  maxlength="6"
                  class="mt-3"
                  @keyup.enter="enableTotp"
                />
                <div class="totp-actions">
                  <ElButton type="primary" :loading="savingTotp" @click="enableTotp">
                    开启两步验证
                  </ElButton>
                  <ElButton link @click="loadTotpSecret">刷新二维码</ElButton>
                </div>
              </div>
            </div>
          </div>

          <!-- 已开启：可继续扫码添加设备 + 关闭 -->
          <div v-else>
            <p class="form-tip">
              两步验证已开启，每次登录需要输入 App 上的 6 位验证码。换手机或多台设备时，用新设备
              <b>扫描同一张二维码</b>即可，密钥不变、老设备照常可用。
            </p>
            <ElButton size="small" @click="toggleAddDevice">
              {{ showAddDevice ? '收起二维码' : '添加设备（扫码）' }}
            </ElButton>

            <div v-if="showAddDevice" class="totp-wrap mt-3">
              <div class="totp-qr">
                <QrcodeVue v-if="totp.uri" :value="totp.uri" :size="150" level="M" />
                <div v-else class="totp-qr-empty">二维码生成中…</div>
                <div class="totp-qr-label">{{ issuerLabel }}</div>
              </div>
              <div class="totp-main">
                <div class="totp-label">手动输入密钥</div>
                <div class="totp-secret">
                  <span class="mono">{{ totp.secret || '—' }}</span>
                  <ElButton link size="small" :disabled="!totp.secret" @click="copySecret">
                    复制
                  </ElButton>
                </div>
              </div>
            </div>

            <div class="totp-disable">
              <div class="totp-label">关闭两步验证</div>
              <ElInput v-model="totpCode" placeholder="输入当前验证码以关闭" maxlength="6" />
              <ElButton type="danger" class="mt-2" :loading="savingTotp" @click="disableTotp">
                关闭两步验证
              </ElButton>
            </div>
          </div>
        </div>
      </ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
  import QrcodeVue from 'qrcode.vue'
  import {
    changePassword,
    disable2fa,
    enable2fa,
    fetch2faSecret,
    updateProfile,
  } from '@/api/certd'
  import { useUserStore } from '@/store/modules/user'
  import { useSiteStore } from '@/store/modules/site'
  import { ElMessage } from 'element-plus'

  defineOptions({ name: 'AccountSecurity' })

  const userStore = useUserStore()
  const siteStore = useSiteStore()

  // 后端 /api/user/info 的字段比 UserInfo 类型宽（nickname / role / totpEnabled），
  // 这里直接按 any 用，避免每次 setUserInfo 都因为「可选 vs 必填」报类型错
  const info = computed<any>(() => userStore.info || {})
  const savingProfile = ref(false)
  const savingPassword = ref(false)
  const savingTotp = ref(false)
  const loadingTotp = ref(false)
  // 已开启时是否展开「添加设备」的二维码
  const showAddDevice = ref(false)

  const profile = reactive({ nickname: '', email: '' })
  const password = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
  const totp = reactive({ secret: '', uri: '', account: '' })
  const totpCode = ref('')

  // 二维码上方那行小字：App 里显示的名字（issuer 用站点名称，后端已按站点设置生成）
  const issuerLabel = computed(
    () => `${siteStore.displayName} · ${totp.account || info.value.userName || ''}`
  )

  const saveProfile = async () => {
    savingProfile.value = true
    try {
      await updateProfile({ nickname: profile.nickname, email: profile.email })
      ElMessage.success('已保存')
      if (userStore.info) {
        userStore.setUserInfo({ ...(userStore.info as any), nickname: profile.nickname, email: profile.email })
      }
    } finally {
      savingProfile.value = false
    }
  }

  // 与后端 security.validate_password 保持同一套规则，前端先提示、后端再兜底
  const pwdChecks = computed(() => {
    const pwd = password.newPassword || ''
    const userName = (info.value as any).userName || ''
    return [
      { text: '至少 8 个字符', ok: pwd.length >= 8 },
      { text: '不能是纯数字', ok: pwd.length > 0 && !/^\d+$/.test(pwd) },
      { text: '不能与用户名相同', ok: pwd.length > 0 && pwd !== userName },
    ]
  })

  const savePassword = async () => {
    if (!password.oldPassword || !password.newPassword) {
      ElMessage.warning('请填写当前密码与新密码')
      return
    }
    const bad = pwdChecks.value.find((item) => !item.ok)
    if (bad) {
      ElMessage.warning(`新密码不符合要求：${bad.text}`)
      return
    }
    if (password.newPassword !== password.confirmPassword) {
      ElMessage.warning('两次输入的新密码不一致')
      return
    }
    if (password.newPassword === password.oldPassword) {
      ElMessage.warning('新密码不能与当前密码相同')
      return
    }
    savingPassword.value = true
    try {
      await changePassword({
        oldPassword: password.oldPassword,
        newPassword: password.newPassword,
      })
      password.oldPassword = ''
      password.newPassword = ''
      password.confirmPassword = ''
      ElMessage.success('密码已修改，请用新密码重新登录')
      // 旧 token 仍然有效（JWT 无法吊销），改了密码就该立刻换身份重新认证
      userStore.logOut()
    } finally {
      savingPassword.value = false
    }
  }

  /**
   * 取（或复用）两步验证密钥，拿到 otpauth:// 链接去渲染二维码。
   * 后端对已开启的账号会沿用原密钥，所以多台设备扫到的是同一张码。
   */
  const loadTotpSecret = async () => {
    loadingTotp.value = true
    try {
      const data = await fetch2faSecret()
      totp.secret = data.secret || ''
      totp.uri = data.uri || ''
      totp.account = (data as any).account || ''
    } finally {
      loadingTotp.value = false
    }
  }

  const toggleAddDevice = async () => {
    showAddDevice.value = !showAddDevice.value
    if (showAddDevice.value && !totp.uri) {
      await loadTotpSecret()
    }
  }

  /** 复制密钥（手动添加到 App 用） */
  const copySecret = async () => {
    if (!totp.secret) return
    try {
      await navigator.clipboard.writeText(totp.secret)
      ElMessage.success('密钥已复制')
    } catch {
      ElMessage.warning('复制失败，请手动选中密钥复制')
    }
  }

  const enableTotp = async () => {
    if (!totpCode.value) {
      ElMessage.warning('请输入验证码')
      return
    }
    savingTotp.value = true
    try {
      await enable2fa(totpCode.value)
      ElMessage.success('两步验证已开启')
      if (userStore.info) userStore.setUserInfo({ ...(userStore.info as any), totpEnabled: true })
      totpCode.value = ''
      showAddDevice.value = false
    } finally {
      savingTotp.value = false
    }
  }

  const disableTotp = async () => {
    if (!totpCode.value) {
      ElMessage.warning('请输入验证码')
      return
    }
    savingTotp.value = true
    try {
      await disable2fa(totpCode.value)
      ElMessage.success('已关闭两步验证')
      if (userStore.info) userStore.setUserInfo({ ...(userStore.info as any), totpEnabled: false })
      totpCode.value = ''
      // 关闭后回到「扫码绑定」的初始态
      totp.uri = ''
      totp.secret = ''
      showAddDevice.value = false
      await loadTotpSecret()
    } finally {
      savingTotp.value = false
    }
  }

  onMounted(async () => {
    profile.nickname = (info.value as any).nickname || ''
    profile.email = (info.value as any).email || ''
    siteStore.ensureLoaded()
    // 未开启时直接把二维码摆出来，不让人先点「生成密钥」才看到码
    if (!info.value.totpEnabled) {
      await loadTotpSecret()
    }
  })
</script>

<style scoped>
  /* 每个分区之间一条细线，比整页卡片轻，放进页签里也不显得重复套框 */
  .sec-block {
    padding-bottom: 4px;
    margin-bottom: 20px;
    border-bottom: 1px solid var(--art-card-border);
  }

  .sec-block:last-child {
    margin-bottom: 0;
    border-bottom: 0;
  }

  .sec-title {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 600;
    color: var(--art-text-gray-900, var(--g-text, #1f2937));
  }

  .form-tip {
    margin: 0 0 12px;
    font-size: 12px;
    line-height: 1.7;
    color: var(--art-gray-500);
  }

  .pwd-hint {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    margin-top: 6px;
  }

  .pwd-check {
    display: flex;
    gap: 2px;
    align-items: center;
    font-size: 12px;
    line-height: 1.6;
    color: var(--art-gray-500);
  }

  .pwd-check.ok {
    color: var(--el-color-success);
  }

  .pwd-check-icon {
    font-size: 13px;
  }

  .pwd-tip {
    margin-left: 10px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .totp-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
  }

  .totp-qr {
    display: flex;
    flex: 0 0 auto;
    flex-direction: column;
    gap: 6px;
    align-items: center;
    padding: 10px;
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: 10px;
  }

  .totp-qr-empty {
    padding: 42px 20px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .totp-qr-label {
    max-width: 158px;
    overflow: hidden;
    font-size: 11px;
    color: var(--art-gray-500);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .totp-main {
    flex: 1 1 180px;
    min-width: 160px;
  }

  .totp-label {
    margin-bottom: 4px;
    font-size: 12px;
    color: var(--art-gray-500);
  }

  .totp-secret {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: space-between;
    padding: 4px 8px;
    background: var(--art-gray-100);
    border-radius: 6px;
  }

  .totp-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-top: 12px;
  }

  .totp-disable {
    margin-top: 16px;
    padding-top: 14px;
    border-top: 1px solid var(--art-card-border);
  }

  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    word-break: break-all;
  }
</style>
