<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { AppPage, PageHeader, PageSurface } from '@/components/ui'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { apiErrorMessage } from '@/utils/apiResult'
import InstalledPane from '@/views/plugins/installed/InstalledPane.vue'
import MarketPane from '@/views/plugins/market/MarketPane.vue'
import UpdatesPane from '@/views/plugins/updates/UpdatesPane.vue'
import UpdatesToolbar from '@/views/plugins/updates/UpdatesToolbar.vue'
import { INSTALLED_FILTERS, MARKET_FILTERS } from '@/views/plugins/pluginCenterModel'
import { providePluginCenter, type PluginCenterTab } from '@/views/plugins/usePluginCenter'

/** 插件中心外壳：/plugins、/plugins/market、/plugins/updates 共用一个实例，页签跟随路由。 */
const ROUTE_BY_TAB: Record<PluginCenterTab, string> = {
  installed: 'Plugins',
  market: 'PluginMarket',
  updates: 'PluginUpdates',
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const center = providePluginCenter()
const { data, lock, installedQuery, installedFilter, marketQuery, marketFilter } = center

const tab = computed<PluginCenterTab>(() =>
  route.name === 'PluginMarket'
    ? 'market'
    : route.name === 'PluginUpdates'
      ? 'updates'
      : 'installed'
)
const tabOptions = computed(() => [
  {
    value: 'installed',
    payload: { count: data.registry.loaded.value ? data.installed.value.length : null },
  },
  { value: 'market', payload: { count: null } },
  { value: 'updates', payload: { count: data.updates.value.length || null } },
])
const selectTab = (value: string | number) => {
  const next = ROUTE_BY_TAB[value as PluginCenterTab]
  if (next && next !== route.name) void router.push({ name: next })
}

const query = computed({
  get: () => (tab.value === 'market' ? marketQuery.value : installedQuery.value),
  set: value => {
    if (tab.value === 'market') marketQuery.value = value
    else installedQuery.value = value
  },
})
const filterOptions = computed(() =>
  tab.value === 'market'
    ? MARKET_FILTERS.map(value => ({
        value,
        active: marketFilter.value === value,
        pick: () => (marketFilter.value = value),
      }))
    : INSTALLED_FILTERS.map(value => ({
        value,
        active: installedFilter.value === value,
        pick: () => (installedFilter.value = value),
      }))
)

const loading = computed(() => data.registry.loading.value || data.catalog.loading.value)
const loadError = computed(() =>
  tab.value === 'market'
    ? data.catalog.error.value
    : data.registry.error.value || data.catalog.error.value
)
const refresh = async () => {
  // 从发行目录检查更新（市场页签为刷新目录），再回读安装状态与可执行操作。
  try {
    if (await data.refreshCatalog())
      message.success(
        t(tab.value === 'market' ? 'core.plugins.marketRefreshed' : 'core.plugins.updatesChecked')
      )
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.plugins.actionFailed')))
  }
}

watch(
  tab,
  current => {
    // 进入市场先显示本机目录，再从发行源刷新；慢网或失败时保留已有列表。
    if (current === 'market') void data.autoRefreshCatalog()
  },
  { immediate: true }
)
</script>

<template>
  <AppPage layout="fill" class="plugins-page">
    <PageHeader :title="t('core.plugins.title')">
      <template #actions>
        <a-button
          :loading="data.catalogRefreshing.value || loading"
          :disabled="lock.busy.value"
          @click="refresh"
          ><template #icon><ReloadOutlined /></template
          >{{
            t(tab === 'market' ? 'core.plugins.refreshCatalog' : 'core.plugins.checkUpdates')
          }}</a-button
        >
      </template>
    </PageHeader>
    <PageSurface>
      <div class="plugin-center">
        <div class="plugin-center-toolbar">
          <a-segmented :value="tab" :options="tabOptions" @change="selectTab">
            <template #label="{ value, payload }">
              <span class="plugin-center-tab">
                {{ t(`core.plugins.tab.${value}`) }}
                <span v-if="payload?.count !== null && payload?.count !== undefined">{{
                  payload.count
                }}</span>
              </span>
            </template>
          </a-segmented>
          <template v-if="tab !== 'updates'">
            <a-input
              v-model:value="query"
              class="plugin-center-search"
              allow-clear
              :aria-label="
                t(tab === 'market' ? 'core.plugins.searchMarket' : 'core.plugins.searchInstalled')
              "
              :placeholder="
                t(tab === 'market' ? 'core.plugins.searchMarket' : 'core.plugins.searchInstalled')
              "
            >
              <template #prefix><SearchOutlined /></template>
            </a-input>
            <div class="plugin-center-filters">
              <a-checkable-tag
                v-for="filter in filterOptions"
                :key="filter.value"
                :checked="filter.active"
                @change="filter.pick()"
                >{{ t(`core.plugins.filter.${filter.value}`) }}</a-checkable-tag
              >
            </div>
          </template>
          <UpdatesToolbar v-else />
        </div>
        <ApiRetryAlert :error="loadError" :loading="loading" @retry="data.reload" />
        <InstalledPane v-if="tab === 'installed'" />
        <MarketPane v-else-if="tab === 'market'" />
        <UpdatesPane v-else />
      </div>
    </PageSurface>
  </AppPage>
</template>

<style scoped>
.plugin-center {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}

.plugin-center-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.plugin-center-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.plugin-center-search {
  flex: 1 1 200px;
  min-width: 0;
}

.plugin-center-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
