<script setup lang="ts">
import { computed, ref } from 'vue'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { useAppearanceTryOnStore } from '@/stores/appearanceTryOn'
import type { OnlineAppearanceItem } from '@/types/appearance'
import type { AppearanceCategory } from '@/types/mascotPack'
import {
  filterAndSortStoreItems,
  isLiveThemeItem,
  pickAutoFeaturedItem,
  shouldUseCompactBanner,
  type StoreQuickFilter,
  type StoreSortKey,
} from '../storeFiltering'
import { getOnlineAppearanceStatus, type OnlineAppearanceStore } from '../useOnlineAppearance'
import OnlineAppearanceCard from './OnlineAppearanceCard.vue'
import StoreFeaturedBanner from './StoreFeaturedBanner.vue'

const props = defineProps<{
  store: OnlineAppearanceStore
  categoryMode: 'all' | 'theme' | 'mascot' | 'installed'
}>()

const { t } = useI18n()
const { persistedAppearance } = useTheme()
const tryOnStore = useAppearanceTryOnStore()

const {
  items,
  listLoading,
  listError,
  page,
  total,
  keyword,
  pageSize,
  tryingFileKey,
  coverFor,
  loadList,
  scheduleSearch,
  clearKeyword,
  openDetail,
  tryOnItem,
} = props.store

const quickFilter = ref<StoreQuickFilter>('all')
const sortKey = ref<StoreSortKey>('latest')
const bannerCollapsed = ref(false)

const isThemeItem = (item: OnlineAppearanceItem): boolean => {
  const cat: AppearanceCategory =
    item.categoryKey ?? (props.categoryMode === 'mascot' ? 'mascot' : 'theme')
  return cat === 'theme'
}

const isItemActive = (item: OnlineAppearanceItem): boolean =>
  Boolean(item.installed && persistedAppearance.value?.id === item.installed.appearanceId)

const isItemTrying = (item: OnlineAppearanceItem): boolean =>
  Boolean(tryOnStore.active && tryOnStore.session?.fileKey === item.fileKey)

const displayItems = computed(() =>
  filterAndSortStoreItems(items.value, {
    filter: quickFilter.value,
    sort: sortKey.value,
    installedOnly: props.categoryMode === 'installed',
  })
)

const featuredItem = computed(() => {
  if (
    props.categoryMode === 'installed' ||
    keyword.value.trim() ||
    quickFilter.value !== 'all' ||
    page.value !== 1
  ) {
    return null
  }
  return pickAutoFeaturedItem(items.value)
})

const compactBanner = computed(() => shouldUseCompactBanner(total.value || items.value.length))
const outdatedCount = computed(
  () => items.value.filter(item => getOnlineAppearanceStatus(item) === 'outdated').length
)
const liveCount = computed(() => items.value.filter(isLiveThemeItem).length)

const sortOptions = computed(() => [
  { value: 'latest', label: t('core.themeStore.sort.latest') },
  { value: 'popular', label: t('core.themeStore.sort.popular') },
  { value: 'updated', label: t('core.themeStore.sort.updated') },
])

const handleKeywordInput = (value: string): void => {
  keyword.value = value
  scheduleSearch()
}

const resetFilters = (): void => {
  quickFilter.value = 'all'
  clearKeyword()
}
</script>

<template>
  <div class="online-toolbar">
    <a-input
      :value="keyword"
      allow-clear
      :placeholder="t('core.themeStore.search')"
      class="online-search"
      @update:value="handleKeywordInput"
      @press-enter="loadList(1)"
    >
      <template #prefix><SearchOutlined /></template>
    </a-input>

    <div v-if="categoryMode !== 'mascot'" class="online-filter-pills">
      <a-button
        size="small"
        :type="quickFilter === 'all' ? 'primary' : 'default'"
        :ghost="quickFilter === 'all'"
        @click="quickFilter = 'all'"
      >
        {{ t('core.themeStore.categories.all') }}
      </a-button>
      <a-button
        v-if="outdatedCount > 0"
        size="small"
        :type="quickFilter === 'outdated' ? 'primary' : 'default'"
        :ghost="quickFilter === 'outdated'"
        @click="quickFilter = 'outdated'"
      >
        {{ t('core.themeStore.filter.outdated', { count: outdatedCount }) }}
      </a-button>
      <a-button
        v-if="liveCount > 0"
        size="small"
        :type="quickFilter === 'live' ? 'primary' : 'default'"
        :ghost="quickFilter === 'live'"
        @click="quickFilter = 'live'"
      >
        {{ t('core.themeStore.filter.liveTheme') }}
      </a-button>
    </div>

    <a-select
      v-model:value="sortKey"
      :options="sortOptions"
      :aria-label="t('core.themeStore.sort.label')"
      class="online-sort-select"
    />

    <a-button
      :loading="listLoading"
      :aria-label="t('core.themeStore.refresh')"
      @click="loadList(page)"
    >
      <template #icon><ReloadOutlined /></template>
      {{ t('core.themeStore.refresh') }}
    </a-button>
  </div>

  <div v-if="listLoading" class="online-state">
    <a-spin size="large" :tip="t('core.themeStore.loading')" />
  </div>
  <div v-else-if="listError" class="online-state">
    <a-result status="warning" :title="t('core.themeStore.listFailed')" :sub-title="listError">
      <template #extra>
        <a-button type="primary" @click="loadList(page)">
          {{ t('core.themeStore.retry') }}
        </a-button>
      </template>
    </a-result>
  </div>
  <div v-else-if="displayItems.length === 0" class="online-state">
    <NoData
      :description="
        keyword.trim() || quickFilter !== 'all'
          ? t('core.themeStore.noMatch')
          : categoryMode === 'installed'
            ? t('core.themeStore.installedEmpty')
            : t('core.themeStore.empty')
      "
    >
      <a-button v-if="keyword.trim() || quickFilter !== 'all'" @click="resetFilters">
        {{ t('core.themeStore.clearSearch') }}
      </a-button>
    </NoData>
  </div>
  <template v-else>
    <StoreFeaturedBanner
      v-if="featuredItem"
      :item="featuredItem"
      :cover-url="
        coverFor(featuredItem.fileKey, featuredItem.publishedVersionNo, featuredItem.categoryKey)
      "
      :compact="compactBanner"
      :collapsed="bannerCollapsed"
      :trying="tryingFileKey === featuredItem.fileKey"
      :can-try-on="isThemeItem(featuredItem)"
      @try-on="item => void tryOnItem(item)"
      @open-detail="openDetail"
      @toggle-collapse="bannerCollapsed = !bannerCollapsed"
    />

    <div
      class="online-grid"
      :class="{
        'online-grid--mascot': categoryMode === 'mascot',
        'online-grid--dock-pad': tryOnStore.active,
      }"
    >
      <OnlineAppearanceCard
        v-for="item in displayItems"
        :key="`${item.categoryKey ?? ''}:${item.fileKey}`"
        :item="item"
        :cover-url="coverFor(item.fileKey, item.publishedVersionNo, item.categoryKey)"
        :show-category-badge="categoryMode === 'all'"
        :can-try-on="isThemeItem(item)"
        :is-active="isItemActive(item)"
        :is-trying="isItemTrying(item)"
        :trying-loading="tryingFileKey === item.fileKey"
        @open="openDetail"
        @try-on="entry => void tryOnItem(entry)"
      />
    </div>
  </template>

  <div v-if="!listLoading && !listError && total > pageSize" class="online-pagination">
    <a-pagination
      size="small"
      :current="page"
      :page-size="pageSize"
      :total="total"
      :show-size-changer="false"
      @change="loadList"
    />
  </div>
</template>

<style scoped>
.online-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
}

.online-search {
  flex: 1 1 220px;
  min-width: 180px;
}

.online-filter-pills {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.online-sort-select {
  width: 132px;
}

.online-state {
  display: flex;
  min-height: 320px;
  align-items: center;
  justify-content: center;
}

.online-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(252px, 1fr));
  gap: 16px;
}

.online-grid--mascot {
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
}

.online-grid--dock-pad {
  padding-bottom: 76px;
}

.online-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
