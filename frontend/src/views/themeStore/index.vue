<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import type { MyAppearanceItem } from '@/composables/useShareApi'
import { useAppearanceSettings } from '@/views/setting/useAppearanceSettings'
import AppearanceUploadModal from './components/AppearanceUploadModal.vue'
import MyAppearanceList from './components/MyAppearanceList.vue'
import OnlineAppearanceDetail from './components/OnlineAppearanceDetail.vue'
import OnlineAppearanceList from './components/OnlineAppearanceList.vue'
import ThemeStoreAccount from './components/ThemeStoreAccount.vue'
import { toStoreItem } from './myAppearance'
import { useMyAppearances } from './useMyAppearances'
import { useOnlineAppearance } from './useOnlineAppearance'
import { useShareAccount } from './useShareAccount'

defineOptions({ name: 'ThemeStorePage' })

type ThemeStoreTab = 'all' | 'mine'

const { t } = useI18n()
// 覆盖确认、失败提示和「预览 → 应用外观」沿用设置页那一套，所有窗口一起同步。
const { modalContextHolder, installPreparedOnlineAppearance } = useAppearanceSettings()
const store = useOnlineAppearance({ install: installPreparedOnlineAppearance })
const account = useShareAccount({
  onAuthorized: state =>
    message.success(
      t('themeStore.account.authorized', { name: state.displayName || state.username })
    ),
  onError: text => message.error(text),
})
// 令牌被分享站拒了：刷新一次登录状态，界面回到「登录分享站」
const mine = useMyAppearances({ onUnauthorized: () => void account.refresh() })
const { view } = store
const { authorized, state: accountState } = account

const tab = ref<ThemeStoreTab>('all')
const tabOptions = computed(() => [
  { value: 'all', label: t('themeStore.tabs.all') },
  { value: 'mine', label: t('themeStore.tabs.mine') },
])
// 当前登录的账号；未登录为空。换账号或退出时之前账号的列表和封面都不能再用
const accountKey = computed(() => (authorized.value ? `user:${accountState.value.username}` : ''))
const uploadOpen = ref(false)
const uploadTargetId = ref<number | null>(null)

const openUpload = (fileId: number | null = null): void => {
  uploadTargetId.value = fileId
  uploadOpen.value = true
}

const handleUploaded = (): void => {
  if (view.value === 'list') void store.loadList(store.page.value)
  if (authorized.value) void mine.load()
}

const viewInStore = (item: MyAppearanceItem): void => {
  tab.value = 'all'
  void store.openDetail(toStoreItem(item, accountState.value.username))
}

// 先清再拉：两个 watcher 按定义顺序执行
watch(accountKey, () => mine.reset())

watch(
  [tab, accountKey],
  ([currentTab, key]) => {
    if (currentTab === 'mine' && key) void mine.ensureLoaded()
  },
  { immediate: true }
)

onMounted(() => {
  store.open()
  void account.refresh()
})

onBeforeUnmount(() => {
  store.reset()
  mine.reset()
  account.dispose()
})
</script>

<template>
  <div class="theme-store-page">
    <component :is="modalContextHolder" />
    <div class="theme-store-header">
      <h1 class="page-title">{{ t('themeStore.title') }}</h1>
      <div class="theme-store-actions">
        <ThemeStoreAccount :account="account" />
        <a-button type="primary" @click="openUpload()">
          <template #icon><UploadOutlined /></template>
          {{ t('themeStore.upload.open') }}
        </a-button>
      </div>
    </div>
    <div class="theme-store-content">
      <a-segmented v-model:value="tab" :options="tabOptions" class="theme-store-tabs" />
      <template v-if="tab === 'all'">
        <OnlineAppearanceList v-if="view === 'list'" :store="store" />
        <OnlineAppearanceDetail
          v-else
          :store="store"
          :account="account"
          :mine="mine"
          @upload-version="openUpload"
        />
      </template>
      <div v-else-if="!authorized" class="theme-store-login">
        <a-empty :description="t('themeStore.mine.loginRequired')">
          <ThemeStoreAccount :account="account" class="theme-store-login-account" />
        </a-empty>
      </div>
      <MyAppearanceList
        v-else
        :store="mine"
        @upload-version="openUpload"
        @view-in-store="viewInStore"
      />
    </div>
    <AppearanceUploadModal
      v-model:open="uploadOpen"
      :account="account"
      :mine="mine"
      :target-file-id="uploadTargetId"
      @uploaded="handleUploaded"
    />
  </div>
</template>

<style scoped>
.theme-store-page {
  display: flex;
  width: 100%;
  min-height: 100%;
  flex-direction: column;
  box-sizing: border-box;
}

.theme-store-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 0 4px;
}

.page-title {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 32px;
  font-weight: 700;
}

.theme-store-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
}

.theme-store-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 20px 24px 24px;
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.theme-store-tabs {
  align-self: flex-start;
  margin-bottom: 16px;
}

.theme-store-login {
  display: flex;
  min-height: 320px;
  align-items: center;
  justify-content: center;
}

.theme-store-login-account {
  justify-content: center;
}
</style>
