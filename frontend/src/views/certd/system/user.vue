<!--
  用户管理（管理员）
  =========================================================
  多用户数据隔离：每个用户只能看到自己的流水线 / 证书 / 授权。
-->
<template>
  <div class="certd-user art-full-height g-scope">
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
            <ElButton type="primary" @click="openCreate">
              <ArtSvgIcon icon="ri:add-line" class="mr-1" />{{ $t('certd.user.create') }}
            </ElButton>
            <ElButton
              type="danger"
              plain
              :disabled="!selectedIds.length"
              :loading="removing"
              @click="removeSelected"
            >
              <ArtSvgIcon icon="ri:delete-bin-line" class="mr-1" />
              {{ $t('certd.common.batchDelete') }}<template v-if="selectedIds.length"> ({{ selectedIds.length }})</template>
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
        <template #role="{ row }">
          <ElTag :type="row.role === 'admin' ? 'primary' : 'info'" size="small" effect="light">
            {{ row.role === 'admin' ? $t('certd.user.roleAdmin') : $t('certd.user.roleUser') }}
          </ElTag>
        </template>
        <template #status="{ row }">
          <ElTag :type="row.status === 1 ? 'success' : 'info'" size="small" effect="light">
            {{ row.status === 1 ? $t('certd.user.statusEnabled') : $t('certd.user.statusDisabled') }}
          </ElTag>
        </template>
        <template #operation="{ row }">
          <div class="cell-actions">
            <ElButton link @click="openEdit(row)">{{ $t('certd.common.edit') }}</ElButton>
            <ElButton link @click="openResetPwd(row)">{{ $t('certd.user.resetPwdBtn') }}</ElButton>
            <ElButton link type="danger" :disabled="row.id === userStore.info?.userId" @click="remove(row)">
              删除
            </ElButton>
          </div>
        </template>
      </ArtTable>
    </ElCard>

    <ElDialog v-model="dialogVisible" :title="editingId ? '编辑用户' : '新增用户'" width="min(520px, 94vw)" destroy-on-close>
      <ElForm label-position="top">
        <ElFormItem :label="$t('certd.user.userNameLabel')">
          <ElInput v-model="form.userName" :disabled="!!editingId" :placeholder="$t('certd.user.userNamePh')" />
        </ElFormItem>
        <ElFormItem :label="editingId ? $t('certd.user.passwordKeepLabel') : $t('certd.user.passwordLabel')">
          <ElInput v-model="form.password" type="password" show-password autocomplete="new-password" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.user.nicknameLabel')">
          <ElInput v-model="form.nickname" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.user.emailLabel')">
          <ElInput v-model="form.email" />
        </ElFormItem>
        <ElFormItem :label="$t('certd.user.roleLabel')">
          <ElRadioGroup v-model="form.role">
            <ElRadioButton label="admin">{{ $t('certd.user.roleAdmin') }}</ElRadioButton>
            <ElRadioButton label="user">{{ $t('certd.user.roleUser') }}</ElRadioButton>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem :label="$t('certd.user.statusLabel')">
          <ElSwitch v-model="form.status" :active-value="1" :inactive-value="0" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
          <ElButton type="primary" :loading="saving" @click="save">{{ $t('certd.common.save') }}</ElButton>
        </div>
      </template>
    </ElDialog>

    <!-- 重置密码：单独一个入口，不用进「编辑」里翻 -->
    <ElDialog
      v-model="resetPwdVisible"
      :title="$t('certd.user.resetPwdTitle')"
      width="min(440px, 94vw)"
      destroy-on-close
    >
      <p class="reset-tip">
        {{ $t('certd.user.resetPwdTip', { name: resetPwdRow?.userName || '' }) }}
      </p>
      <ElForm label-position="top">
        <ElFormItem :label="$t('certd.user.newPasswordLabel')">
          <ElInput v-model="resetPwdForm.password" type="password" show-password autocomplete="new-password" />
          <div class="reset-actions">
            <ElButton link size="small" @click="genRandomPassword">{{ $t('certd.user.genRandom') }}</ElButton>
          </div>
          <div class="pwd-hint">
            <div v-for="item in resetPwdChecks" :key="item.key" class="pwd-check" :class="{ ok: item.ok }">
              <ArtSvgIcon
                :icon="item.ok ? 'ri:checkbox-circle-fill' : 'ri:checkbox-blank-circle-line'"
                class="pwd-check-icon"
              />
              {{ item.text }}
            </div>
          </div>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="resetPwdVisible = false">{{ $t('certd.common.cancel') }}</ElButton>
          <ElButton type="primary" :loading="resettingPwd" @click="submitResetPwd">{{ $t('certd.user.confirmReset') }}</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { useTable } from '@/hooks/core/useTable'
  import { createUser, deleteUser, fetchUserList, updateUser } from '@/api/certd'
  import { useUserStore } from '@/store/modules/user'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useBatchDelete } from '../composables/use-batch-delete'
  import { $t } from '@/locales'

  defineOptions({ name: 'CertdSystemUser' })

  const userStore = useUserStore()
  const searchForm = ref<Record<string, any>>({ keyword: undefined })
  const searchItems = computed(() => [
    { key: 'keyword', label: $t('certd.user.colUserName'), type: 'input', placeholder: $t('certd.user.searchPh') },
  ])

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
      apiFn: fetchUserList,
      apiParams: { current: 1, size: 20 },
      columnsFactory: () => [
        { type: 'selection', width: 48 },
        { prop: 'userName', label: $t('certd.user.colUserName'), minWidth: 140 },
        { prop: 'nickname', label: $t('certd.user.colNickname'), minWidth: 140 },
        { prop: 'email', label: $t('certd.user.colEmail'), minWidth: 180 },
        { prop: 'role', label: $t('certd.user.colRole'), width: 110, useSlot: true },
        { prop: 'status', label: $t('certd.user.colStatus'), width: 110, useSlot: true },
        { prop: 'lastLoginTime', label: $t('certd.user.colLastLogin'), width: 190 },
        { prop: 'operation', label: $t('certd.common.actions'), width: 220, fixed: 'right', useSlot: true },
      ],
    },
  })

  /* ---------------- 多选批量删除 ---------------- */
  const { selectedIds, removing, handleSelectionChange, removeSelected } = useBatchDelete(
    deleteUser,
    { label: () => $t('certd.user.itemLabel'), nameOf: (row: any) => row.userName, onDone: () => refreshData() }
  )

  const handleSearch = (params: Record<string, any>) => {
    Object.assign(searchParams, params)
    getData()
  }
  const handleReset = () => resetSearchParams()

  const dialogVisible = ref(false)
  const editingId = ref(0)
  const saving = ref(false)
  const form = reactive({
    userName: '',
    password: '',
    nickname: '',
    email: '',
    role: 'user',
    status: 1,
  })

  const openCreate = () => {
    editingId.value = 0
    Object.assign(form, { userName: '', password: '', nickname: '', email: '', role: 'user', status: 1 })
    dialogVisible.value = true
  }

  const openEdit = (row: any) => {
    editingId.value = row.id
    Object.assign(form, {
      userName: row.userName,
      password: '',
      nickname: row.nickname,
      email: row.email,
      role: row.role,
      status: row.status,
    })
    dialogVisible.value = true
  }

  const save = async () => {
    if (!form.userName.trim()) {
      ElMessage.warning($t('certd.user.userNameRequired'))
      return
    }
    if (!editingId.value) {
      const bad = checkPassword(form.password, form.userName).find((item) => !item.ok)
      if (bad) {
        ElMessage.warning($t('certd.user.pwdInvalid', { reason: bad.text }))
        return
      }
    }
    saving.value = true
    try {
      if (editingId.value) await updateUser(editingId.value, { ...form })
      else await createUser({ ...form })
      dialogVisible.value = false
      refreshData()
    } finally {
      saving.value = false
    }
  }

  /* ---------------- 重置密码 ---------------- */
  const resetPwdVisible = ref(false)
  const resettingPwd = ref(false)
  const resetPwdRow = ref<any>(null)
  const resetPwdForm = reactive({ password: '' })

  // 密码规则与后端 security.validate_password 一致
  const checkPassword = (pwd: string, userName: string) => [
    { key: 'min8', text: $t('certd.user.pwdMin8'), ok: pwd.length >= 8 },
    { key: 'notDigits', text: $t('certd.user.pwdNotDigits'), ok: pwd.length > 0 && !/^\d+$/.test(pwd) },
    { key: 'notUserName', text: $t('certd.user.pwdNotUserName'), ok: pwd.length > 0 && pwd !== userName },
  ]
  const resetPwdChecks = computed(() => checkPassword(resetPwdForm.password, resetPwdRow.value?.userName || ''))

  const openResetPwd = (row: any) => {
    resetPwdRow.value = row
    resetPwdForm.password = ''
    resetPwdVisible.value = true
  }

  // 随机强密码：去掉易混淆字符（0O1lI），固定 4 段便于抄写
  const genRandomPassword = () => {
    const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    const arr = new Uint32Array(16)
    crypto.getRandomValues(arr)
    const pwd = Array.from(arr, (n) => chars[n % chars.length]).join('')
    resetPwdForm.password = pwd
    ElMessage.success($t('certd.user.pwdGenerated'))
  }

  const submitResetPwd = async () => {
    if (!resetPwdRow.value) return
    const bad = resetPwdChecks.value.find((item) => !item.ok)
    if (bad) {
      ElMessage.warning($t('certd.user.newPwdInvalid', { reason: bad.text }))
      return
    }
    resettingPwd.value = true
    try {
      const row = resetPwdRow.value
      await updateUser(row.id, {
        userName: row.userName,
        nickname: row.nickname,
        email: row.email,
        role: row.role,
        status: row.status,
        password: resetPwdForm.password,
      })
      ElMessage.success($t('certd.user.pwdReset'))
      resetPwdVisible.value = false
      resetPwdForm.password = ''
      refreshData()
    } finally {
      resettingPwd.value = false
    }
  }

  const remove = async (row: any) => {
    await ElMessageBox.confirm($t('certd.user.confirmDelete', { name: row.userName }), $t('certd.user.deleteTitle'), {
      type: 'warning',
      confirmButtonText: $t('certd.common.confirm'),
      cancelButtonText: $t('certd.common.cancel'),
    })
    await deleteUser(row.id)
    ElMessage.success($t('certd.common.deleted'))
    refreshData()
  }
</script>

<style scoped>
  .cell-actions {
    display: flex;
    gap: 6px;
  }

  .dialog-footer {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .reset-tip {
    margin: 0 0 12px;
    font-size: 12px;
    line-height: 1.7;
    color: var(--art-gray-500);
  }

  .reset-actions {
    margin-top: 4px;
  }

  .pwd-hint {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    margin-top: 4px;
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
</style>
