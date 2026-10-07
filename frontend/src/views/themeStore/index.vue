<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import { useAppearanceSettings } from '@/views/setting/useAppearanceSettings'
import AppearanceUploadModal from './components/AppearanceUploadModal.vue'
import OnlineAppearanceDetail from './components/OnlineAppearanceDetail.vue'
import OnlineAppearanceList from './components/OnlineAppearanceList.vue'
import ThemeStoreAccount from './components/ThemeStoreAccount.vue'
import { useOnlineAppearance } from './useOnlineAppearance'
import { useShareAccount } from './useShareAccount'

defineOptions({ name: 'ThemeStorePage' })

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
const { view } = store
const uploadOpen = ref(false)

const handleUploaded = (): void => {
  if (view.value === 'list') void store.loadList(store.page.value)
}

onMounted(() => {
  store.open()
  void account.refresh()
})

onBeforeUnmount(() => {
  store.reset()
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
        <a-button type="primary" @click="uploadOpen = true">
          <template #icon><UploadOutlined /></template>
          {{ t('themeStore.upload.open') }}
        </a-button>
      </div>
    </div>
    <div class="theme-store-content">
      <OnlineAppearanceList v-if="view === 'list'" :store="store" />
      <OnlineAppearanceDetail v-else :store="store" />
    </div>
    <AppearanceUploadModal
      v-model:open="uploadOpen"
      :account="account"
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
</style>
