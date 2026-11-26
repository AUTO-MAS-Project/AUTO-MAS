<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { FileTextOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import type { MyAppearanceItem } from '@/composables/useShareApi'
import type { AppearanceCategory, AppearanceFilter } from '@/types/mascotPack'
import { useAppearanceSettings } from '@/views/setting/useAppearanceSettings'
import { MAS_DOC_URLS, openExternalUrl } from '@/utils/openExternal'
import { AppPage, PageHeader, PageSurface } from '@/components/ui'
import AppearanceUploadModal from './components/AppearanceUploadModal.vue'
import MyAppearanceList from './components/MyAppearanceList.vue'
import OnlineAppearanceDetailDrawer from './components/OnlineAppearanceDetailDrawer.vue'
import OnlineAppearanceList from './components/OnlineAppearanceList.vue'
import ThemeStoreAccount from './components/ThemeStoreAccount.vue'
import ThemeStoreLocalStatus from './components/ThemeStoreLocalStatus.vue'
import { toStoreItem } from './myAppearance'
import { useMyAppearances } from './useMyAppearances'
import { useOnlineAppearance } from './useOnlineAppearance'
import { useOutdatedAppearances } from './useOutdatedAppearances'
import { useShareAccount } from './useShareAccount'

defineOptions({ name: 'ThemeStorePage' })

type ThemeStoreTab = 'all' | AppearanceCategory | 'installed' | 'mine'

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

const refreshOutdated = (): void => {
  void outdated.refresh()
}

// 按分类独立持有列表、封面和下载 token，切换时不会把旧请求写进新分类。
const contexts = {
  all: {
    store: useOnlineAppearance({
      categoryKey: 'all',
      install: (token, category, opts) =>
        installPreparedOnlineAppearance(token, category ?? 'theme', opts),
      onInstalled: refreshOutdated,
    }),
  },
  theme: {
    store: useOnlineAppearance({
      categoryKey: 'theme',
      install: (token, _category, opts) => installPreparedOnlineAppearance(token, 'theme', opts),
      onInstalled: refreshOutdated,
    }),
    mine: useMyAppearances({
      categoryKey: 'theme',
      onUnauthorized: () => void account.refresh(),
      onChanged: () => invalidateMine('theme'),
    }),
  },
  mascot: {
    store: useOnlineAppearance({
      categoryKey: 'mascot',
      install: (token, _category, opts) => installPreparedOnlineAppearance(token, 'mascot', opts),
      onInstalled: refreshOutdated,
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

const tab = ref<ThemeStoreTab>('all')
const activeStoreKey = computed<'all' | 'theme' | 'mascot'>(() => {
  if (tab.value === 'theme') return 'theme'
  if (tab.value === 'mascot') return 'mascot'
  return 'all'
})
const store = computed(() => contexts[activeStoreKey.value].store)
const mine = computed(() => {
  if (tab.value === 'theme') return contexts.theme.mine
  if (tab.value === 'mascot') return contexts.mascot.mine
  return allMine
})
const storeInstalling = computed(() =>
  Object.values(contexts).some(context => context.store.installing.value)
)
// 顶部状态条与「全部更新」共享独立于搜索、分页和分类页签的全量本机待更新清单。
const outdated = useOutdatedAppearances({
  install: (token, category, opts) => installPreparedOnlineAppearance(token, category, opts),
  isBusy: () => storeInstalling.value,
  onUpdated: () => {
    if (tab.value !== 'mine') void store.value.loadList(store.value.page.value)
  },
})
const installing = computed(() => storeInstalling.value || outdated.updatingAll.value)
const { authorized, state: accountState } = account

const tabOptions = computed(() => [
  { value: 'all', label: t('core.themeStore.categories.all') },
  { value: 'theme', label: t('core.themeStore.categories.theme') },
  { value: 'mascot', label: t('core.themeStore.tabs.mascot') },
  { value: 'installed', label: t('core.themeStore.tabs.installed') },
  { value: 'mine', label: t('core.themeStore.tabs.mine') },
])

// 当前登录的账号；未登录为空。换账号或退出时之前账号的列表和封面都不能再用。
const accountKey = computed(() => (authorized.value ? `user:${accountState.value.username}` : ''))
const uploadOpen = ref(false)
const uploadTargetId = ref<number | null>(null)
const uploadCategory = ref<AppearanceCategory>('theme')
const uploadMine = computed(() => contexts[uploadCategory.value].mine)

const openUpload = (fileId: number | null = null, resourceCategory?: AppearanceCategory): void => {
  uploadCategory.value =
    resourceCategory ??
    store.value.detailItem.value?.categoryKey ??
    (tab.value === 'mascot' ? 'mascot' : 'theme')
  uploadTargetId.value = fileId
  uploadOpen.value = true
}

/**
 * 打开外观包与桌宠包的文档。
 * 文档站暂无英文版外观指南，先固定打开中文页。
 */
const openDocs = (): void => {
  void openExternalUrl(MAS_DOC_URLS.appearance)
}

const handleUploaded = (): void => {
  invalidateMine()
  void outdated.refresh()
  if (tab.value !== 'mine') void store.value.loadList(store.value.page.value)
  if (authorized.value) void mine.value.ensureLoaded()
}

function invalidateMine(source?: AppearanceFilter): void {
  if (source !== 'all') allMine.reset()
  if (source !== 'theme') contexts.theme.mine.reset()
  if (source !== 'mascot') contexts.mascot.mine.reset()
}

const viewInStore = (item: MyAppearanceItem): void => {
  const resourceCategory = item.categoryKey ?? 'theme'
  tab.value = resourceCategory
  void contexts[resourceCategory].store.loadList(1)
  void contexts[resourceCategory].store.openDetail(toStoreItem(item, accountState.value.username))
}

watch(accountKey, () => invalidateMine())

watch(tab, (current, previous) => {
  const prevKey =
    previous === 'theme' || previous === 'mascot' ? previous : previous === 'mine' ? null : 'all'
  const nextKey =
    current === 'theme' || current === 'mascot' ? current : current === 'mine' ? null : 'all'
  if (prevKey && nextKey && prevKey !== nextKey) {
    const keyword = contexts[prevKey].store.keyword.value
    contexts[prevKey].store.backToList()
    contexts[nextKey].store.keyword.value = keyword
  } else if (prevKey && !nextKey) {
    contexts[prevKey].store.backToList()
  }
  uploadTargetId.value = null
  if (nextKey && (contexts[nextKey].store.items.value.length === 0 || prevKey !== nextKey)) {
    void contexts[nextKey].store.loadList(1)
  }
})

watch(
  [tab, accountKey],
  ([currentTab, key]) => {
    if (currentTab === 'mine' && key) void mine.value.ensureLoaded()
  },
  { immediate: true }
)

let unsubAppearance: (() => void) | undefined
let unsubMascot: (() => void) | undefined

onMounted(() => {
  contexts.all.store.open()
  void outdated.refresh()
  void account.refresh()
  unsubAppearance = window.electronAPI.onAppearanceChanged?.(() => {
    if (!outdated.updatingAll.value) void outdated.refresh()
  })
  unsubMascot = window.electronAPI.onMascotChanged?.(() => {
    if (!outdated.updatingAll.value) void outdated.refresh()
  })
})

onBeforeUnmount(() => {
  unsubAppearance?.()
  unsubMascot?.()
  contexts.all.store.reset()
  contexts.theme.store.reset()
  contexts.theme.mine.reset()
  contexts.mascot.store.reset()
  contexts.mascot.mine.reset()
  allMine.reset()
  outdated.reset()
  account.dispose()
})
</script>

<template>
  <AppPage layout="scroll">
    <component :is="modalContextHolder" />
    <PageHeader :title="t('core.themeStore.title')">
      <template #actions>
        <ThemeStoreAccount :account="account" />
        <a-button @click="openDocs">
          <template #icon><FileTextOutlined /></template>
          {{ t('core.themeStore.openDocs') }}
        </a-button>
        <a-button type="primary" @click="openUpload()">
          <template #icon><UploadOutlined /></template>
          {{ t('core.themeStore.upload.open') }}
        </a-button>
      </template>
    </PageHeader>

    <PageSurface :scrollable="false" class="theme-store-content">
      <ThemeStoreLocalStatus
        :outdated-count="outdated.items.value.length"
        :updating-all="outdated.updatingAll.value"
        @update-all="void outdated.updateAll()"
      />

      <a-segmented
        v-model:value="tab"
        :options="tabOptions"
        :disabled="uploadOpen || installing"
        class="theme-store-tabs"
      />

      <template v-if="tab !== 'mine'">
        <OnlineAppearanceList
          :key="activeStoreKey"
          :store="store"
          :category-mode="tab === 'installed' ? 'installed' : activeStoreKey"
        />
        <OnlineAppearanceDetailDrawer
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
    </PageSurface>

    <AppearanceUploadModal
      :key="uploadCategory"
      v-model:open="uploadOpen"
      :category-key="uploadCategory"
      :allow-category-change="uploadTargetId === null"
      :account="account"
      :mine="uploadMine"
      :target-file-id="uploadTargetId"
      @uploaded="handleUploaded"
      @category-change="uploadCategory = $event"
    />
  </AppPage>
</template>

<style scoped>
.theme-store-content {
  display: flex;
  flex-direction: column;
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
