<script setup lang="ts">
/**
 * 「市场」页签：等大卡片栅格、卡片内就地显示安装进度、详情弹层。
 * 页头、搜索、筛选和目录失败条由外壳渲染；进页先读本机目录再静默刷新也由外壳负责。
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import NoData from '@/components/NoData.vue'
import MarketCard from './MarketCard.vue'
import MarketDetailModal from './MarketDetailModal.vue'
import { useMarketGrid } from './useMarketGrid'
import {
  MARKET_CARD_GAP,
  matchesMarketFilter,
  matchesSearch,
  type MarketEntryView,
} from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'

/** 首屏骨架卡片数。 */
const SKELETON_CARDS = 6

const { t } = useI18n()
const { data, installation, lock, marketQuery, marketFilter } = usePluginCenter()

const entries = computed(() =>
  data.market.value.filter(
    entry =>
      matchesMarketFilter(entry, marketFilter.value) && matchesSearch(entry, marketQuery.value)
  )
)
const firstLoad = computed(() => data.catalog.loading.value && !data.catalog.loaded.value)
const catalogEmpty = computed(() => data.catalog.loaded.value && !data.market.value.length)
const noMatch = computed(
  () => data.catalog.loaded.value && data.market.value.length > 0 && !entries.value.length
)

const grid = ref<HTMLElement | null>(null)
const columns = useMarketGrid(
  grid,
  computed(() => (firstLoad.value ? SKELETON_CARDS : entries.value.length))
)
const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${columns.value}, minmax(0, 1fr))`,
  gap: `${MARKET_CARD_GAP}px`,
}))

// 详情跟随目录回读：记 uid 而不是条目本身，条目消失时弹层随之关闭。
const detailUid = ref<string | null>(null)
const detailEntry = computed(
  () => data.market.value.find(entry => entry.uid === detailUid.value) ?? null
)

const install = (entry: MarketEntryView) => {
  // 提示与回读由安装状态源负责；锁忙或界面提示不可编辑时它直接返回。
  void installation.install(entry.document)
}
</script>

<template>
  <div class="market-pane">
    <NoData v-if="catalogEmpty" :description="t('core.plugins.marketEmpty')" />
    <NoData v-else-if="noMatch" :description="t('core.plugins.noMatch')" />
    <div
      v-show="firstLoad || entries.length"
      ref="grid"
      class="market-grid"
      :style="gridStyle"
      :aria-busy="firstLoad"
    >
      <template v-if="firstLoad">
        <div v-for="index in SKELETON_CARDS" :key="index" class="market-skeleton">
          <a-skeleton active :avatar="{ shape: 'square', size: 40 }" :paragraph="{ rows: 2 }" />
        </div>
      </template>
      <template v-else>
        <MarketCard
          v-for="entry in entries"
          :key="entry.uid"
          :entry="entry"
          :task="installation.taskOf(entry.uid)"
          :busy="lock.busy.value"
          @details="detailUid = entry.uid"
          @install="install(entry)"
        />
      </template>
    </div>
    <p v-if="data.market.value.length" class="market-count">
      {{ t('core.plugins.marketCount', { count: data.market.value.length }) }}
    </p>
    <MarketDetailModal :entry="detailEntry" @close="detailUid = null" />
  </div>
</template>

<style scoped>
.market-pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}

.market-grid {
  display: grid;
  grid-auto-rows: 1fr;
}

.market-skeleton {
  box-sizing: border-box;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.market-count {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}
</style>
