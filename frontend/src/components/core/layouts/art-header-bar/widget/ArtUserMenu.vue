<!-- 用户菜单：只有「退出登录」一个选项 -->
<template>
  <ElPopover
    ref="userMenuPopover"
    placement="bottom-end"
    :width="240"
    :hide-after="0"
    :offset="10"
    trigger="hover"
    :show-arrow="false"
    popper-class="user-menu-popover"
    popper-style="padding: 5px 16px;"
  >
    <template #reference>
      <span
        class="avatar-trigger mr-2 block size-8.5 overflow-hidden rounded-full c-p max-sm:mr-[16px] max-sm:h-6.5 max-sm:w-6.5"
      >
        <ArtDefaultAvatar />
      </span>
    </template>
    <template #default>
      <div class="pt-3">
        <div class="flex-c px-0 pb-1">
          <span class="mr-3 ml-0 block size-10 overflow-hidden rounded-full">
            <ArtDefaultAvatar />
          </span>
          <div class="h-full w-[calc(100%-60px)]">
            <span class="block truncate text-sm font-medium text-g-800">{{
              userInfo.userName || '未登录'
            }}</span>
            <span class="mt-0.5 block truncate text-xs text-g-500">{{ userInfo.email }}</span>
          </div>
        </div>
        <div class="mt-3 border-t border-g-300/80 pt-4">
          <div class="log-out c-p" @click="loginOut">
            {{ $t('topBar.user.logout') }}
          </div>
        </div>
      </div>
    </template>
  </ElPopover>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { ElMessageBox } from 'element-plus'
  import { useUserStore } from '@/store/modules/user'
  import ArtDefaultAvatar from '@/components/core/base/art-default-avatar/index.vue'

  defineOptions({ name: 'ArtUserMenu' })

  const { t } = useI18n()
  const userStore = useUserStore()

  const { getUserInfo: userInfo } = storeToRefs(userStore)
  const userMenuPopover = ref()

  /**
   * 用户登出确认
   */
  const loginOut = (): void => {
    closeUserMenu()
    setTimeout(() => {
      ElMessageBox.confirm(t('common.logOutTips'), t('common.tips'), {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        customClass: 'login-out-dialog'
      }).then(() => {
        userStore.logOut()
      })
    }, 200)
  }

  /**
   * 关闭用户菜单弹出层
   */
  const closeUserMenu = (): void => {
    setTimeout(() => {
      userMenuPopover.value?.hide()
    }, 100)
  }
</script>

<style scoped>
  @reference '@styles/core/tailwind.css';

  .avatar-trigger {
    background-color: var(--art-gray-200);
  }

  .log-out {
    @apply py-1.5
    mt-0
    text-xs
    text-center
    border
    border-g-400
    rounded-md
    transition-all
    duration-200
    hover:shadow-xl;
  }
</style>
