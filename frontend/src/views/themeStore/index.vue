<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { FileTextOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import type { MyAppearanceItem } from '@/composables/useShareApi'
import type { AppearanceCategory, AppearanceFilter } from '@/types/mascotPack'
import { useAppearanceSettings } from '@/views/setting/useAppearanceSettings'
import { MAS_DOC_URLS, openExternalUrl } from '@/utils/openExternal'
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

type ThemeStoreTab = AppearanceCategory | 'mine'

const { t } = useI18n()
// 覆盖确认、失败提示和「预览 → 应用外观」沿用设置页那一套，所有窗口一起同步。
const { modalContextHolder, installPreparedOnlineAppearance } = useAppearanceSettings()
const account = useShareAccount({
  onAuthorized: state =>
    message.success(
      t('core.themeStore.account.authorized', { name: state.displayName || state.username })
    ),
  onError: text => message.error(text),
})
// 每个分类独立持有列表、封面和下载 token，切换时不会把旧请求写进新分类。
const contexts = {
  theme: {
    store: useOnlineAppearance({ install: installPreparedOnlineAppearance }),
    mine: useMyAppearances({
      onUnauthorized: () => void account.refresh(),
      onChanged: () => invalidateMine('theme'),
    }),
  },
  mascot: {
    store: useOnlineAppearance({
      categoryKey: 'mascot',
      install: token => installPreparedOnlineAppearance(token, 'mascot'),
    }),
    mine: useMyAppearances({
      categoryKey: 'mascot',
      onUnauthorized: () => void account.refresh(),
      onChanged: () => invalidateMine('mascot'),
    }),
  },
}
const allMine = useMyAppearances({
  categoryKey: 'all',
  onUnauthorized: () => void account.refresh(),
  onChanged: () => invalidateMine('all'),
})
const tab = ref<ThemeStoreTab>('theme')
const category = computed<AppearanceCategory>(() => (tab.value === 'mascot' ? 'mascot' : 'theme'))
const store = computed(() => contexts[category.value].store)
const view = computed(() => store.value.view.value)
const mine = computed(() => (tab.value === 'mine' ? allMine : contexts[category.value].mine))
const installing = computed(() =>
  Object.values(contexts).some(context => context.store.installing.value)
)
const { authorized, state: accountState } = account

const tabOptions = computed(() => [
  { value: 'theme', label: t('core.themeStore.tabs.resources') },
  { value: 'mascot', label: t('core.themeStore.tabs.mascot') },
  { value: 'mine', label: t('core.themeStore.tabs.mine') },
])
// 当前登录的账号；未登录为空。换账号或退出时之前账号的列表和封面都不能再用
const accountKey = computed(() => (authorized.value ? `user:${accountState.value.username}` : ''))
const uploadOpen = ref(false)
const uploadTargetId = ref<number | null>(null)
const uploadCategory = ref<AppearanceCategory>('theme')
const uploadMine = computed(() => contexts[uploadCategory.value].mine)

const openUpload = (fileId: number | null = null, resourceCategory?: AppearanceCategory): void => {
  uploadCategory.value =
    resourceCategory ??
    store.value.detailItem.value?.categoryKey ??
    (category.value === 'mascot' ? 'mascot' : 'theme')
  uploadTargetId.value = fileId
  uploadOpen.value = true
}

/**
 * 打开外观包与桌宠包的文档。
 *
 * 文档站还没出英文版的外观指南——`/en/docs/advanced-features/appearance.html` 现在落到中文首页，
 * 所以先固定开中文页，等英文版发布后再接 localizeDocUrl。
 */
const openDocs = (): void => {
  void openExternalUrl(MAS_DOC_URLS.appearance)
}

const handleUploaded = (): void => {
  invalidateMine()
  if (tab.value !== 'mine' && view.value === 'list')
    void store.value.loadList(store.value.page.value)
  if (authorized.value) void mine.value.ensureLoaded()
}

// 同页三份分类缓存共用一组资源；写入后其他分类在下次展示时重新加载。
function invalidateMine(source?: AppearanceFilter): void {
  if (source !== 'all') allMine.reset()
  for (const [key, context] of Object.entries(contexts)) {
    if (key !== source) context.mine.reset()
  }
}

const viewInStore = (item: MyAppearanceItem): void => {
  const resourceCategory = item.categoryKey ?? 'theme'
  tab.value = resourceCategory
  void contexts[resourceCategory].store.loadList(1)
  void contexts[resourceCategory].store.openDetail(toStoreItem(item, accountState.value.username))
}

// 先清再拉：两个 watcher 按定义顺序执行
watch(accountKey, () => invalidateMine())

watch(tab, (current, previous) => {
  if (previous !== 'mine') {
    const keyword = contexts[previous].store.keyword.value
    contexts[previous].store.reset()
    if (current !== 'mine') contexts[current].store.keyword.value = keyword
  }
  uploadTargetId.value = null
  if (current !== 'mine' && view.value === 'list') void store.value.loadList(1)
})

watch(
  [tab, accountKey],
  ([currentTab, key]) => {
    if (currentTab === 'mine' && key) void mine.value.ensureLoaded()
  },
  { immediate: true }
)

onMounted(() => {
  store.value.open()
  void account.refresh()
})

onBeforeUnmount(() => {
  for (const context of Object.values(contexts)) {
    context.store.reset()
    context.mine.reset()
  }
  allMine.reset()
  account.dispose()
})
</script>

<template>
  <div class="theme-store-page">
    <component :is="modalContextHolder" />
    <div class="theme-store-header">
      <h1 class="page-title">{{ t('core.themeStore.title') }}</h1>
      <div class="theme-store-actions">
        <ThemeStoreAccount :account="account" />
        <a-button type="primary" @click="openDocs">
          <template #icon><FileTextOutlined /></template>
          {{ t('core.themeStore.openDocs') }}
        </a-button>
        <a-button type="primary" @click="openUpload()">
          <template #icon><UploadOutlined /></template>
          {{ t('core.themeStore.upload.open') }}
        </a-button>
      </div>
    </div>
    <div class="theme-store-content">
      <a-segmented
        v-model:value="tab"
        :options="tabOptions"
        :disabled="uploadOpen || installing"
        class="theme-store-tabs"
      />
      <template v-if="tab !== 'mine'">
        <OnlineAppearanceList v-if="view === 'list'" :key="category" :store="store" />
        <OnlineAppearanceDetail
          v-else
          :key="category"
          :store="store"
          :account="account"
          :mine="mine"
          @upload-version="openUpload"
        />
      </template>
      <div v-else-if="!authorized" class="theme-store-login">
        <NoData :description="t('core.themeStore.mine.loginRequired')">
          <ThemeStoreAccount :account="account" class="theme-store-login-account" />
        </NoData>
      </div>
      <MyAppearanceList
        v-else
        :store="mine"
        @upload-version="openUpload"
        @view-in-store="viewInStore"
      />
    </div>
    <AppearanceUploadModal
      :key="uploadCategory"
      :category-key="uploadCategory"
      :allow-category-change="uploadTargetId === null"
      v-model:open="uploadOpen"
      :account="account"
      :mine="uploadMine"
      :target-file-id="uploadTargetId"
      @uploaded="handleUploaded"
      @category-change="uploadCategory = $event"
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
  color: var(--app-page-title-color, var(--ant-color-text));
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
