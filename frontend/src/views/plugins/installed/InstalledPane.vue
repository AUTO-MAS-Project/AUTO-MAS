<script setup lang="ts">
/**
 * 「已安装」页签：按核心、专项适配、扩展、本地源码分组的行列表。
 * 取数、锁与命令来自 usePluginCenter()；分组、筛选、用量与拦截判断一律调 pluginCenterModel。
 * 注册表或目录读取失败的重试条由外壳显示，这里只管用量读取失败（拦截要用它）。
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import NoData from '@/components/NoData.vue'
import { groupInstalled, matchesInstalledFilter, matchesSearch } from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'
import InstalledRow from './InstalledRow.vue'
import LifecycleGuardDialog from './LifecycleGuardDialog.vue'
import { useInstalledActions } from './useInstalledActions'

const SKELETON_ROWS = 3

const { t } = useI18n()
const router = useRouter()
const { data, installedQuery, installedFilter } = usePluginCenter()
const actions = useInstalledActions()

const expanded = ref<string[]>([])
const toggleExpanded = (uid: string) => {
  expanded.value = expanded.value.includes(uid)
    ? expanded.value.filter(key => key !== uid)
    : [...expanded.value, uid]
}

const firstLoad = computed(() => data.registry.loading.value && !data.registry.loaded.value)
const unfiltered = computed(() => installedFilter.value === 'all' && !installedQuery.value.trim())
const groups = computed(() =>
  groupInstalled(
    data.installed.value.filter(
      view =>
        matchesInstalledFilter(view, installedFilter.value) &&
        matchesSearch(view, installedQuery.value)
    )
  )
)
/** 读取失败且从没拿到过列表时只显示外壳的失败条，不伪装成没有插件。 */
const empty = computed<'none' | 'noMatch' | 'onlyCore' | null>(() => {
  if (!data.registry.loaded.value) return null
  const installed = data.installed.value
  if (!installed.length) return data.registry.error.value ? null : 'none'
  if (!groups.value.length) return 'noMatch'
  return unfiltered.value && installed.every(view => view.core) ? 'onlyCore' : null
})
/** 只有能对上托管类型的专项才用得上用量；没有这类插件时读取失败不打扰。 */
const usageFailed = computed(
  () => data.usageSource.value.state === 'error' && data.installed.value.some(view => view.binding)
)

const goMarket = () => router.push({ name: 'PluginMarket' })
</script>

<template>
  <div class="installed-pane">
    <a-alert
      v-if="usageFailed"
      type="warning"
      show-icon
      :message="t('core.plugins.usageLoadFailed')"
    >
      <template #action>
        <a-button size="small" :loading="data.usage.loading.value" @click="actions.retryUsage">{{
          t('core.common.retry')
        }}</a-button>
      </template>
    </a-alert>
    <div v-if="firstLoad" class="installed-skeleton" aria-busy="true">
      <a-skeleton
        v-for="index in SKELETON_ROWS"
        :key="index"
        active
        avatar
        :title="{ width: '30%' }"
        :paragraph="{ rows: 1, width: '60%' }"
      />
    </div>
    <template v-else>
      <section v-for="group in groups" :key="group.category" class="installed-group">
        <h2 class="installed-group-title">{{ t(`core.plugins.group.${group.category}`) }}</h2>
        <div class="installed-group-list">
          <InstalledRow
            v-for="view in group.views"
            :key="view.uid"
            :view="view"
            :expanded="expanded.includes(view.uid)"
            @toggle="toggleExpanded(view.uid)"
            @lifecycle="action => actions.request(view, action)"
            @upgrade="actions.upgrade(view)"
          />
        </div>
      </section>
      <NoData
        v-if="empty"
        :description="
          t(
            empty === 'none'
              ? 'core.plugins.empty'
              : empty === 'noMatch'
                ? 'core.plugins.noMatch'
                : 'core.plugins.onlyCore'
          )
        "
      >
        <a-button v-if="empty !== 'noMatch'" type="primary" @click="goMarket">{{
          t('core.plugins.goMarket')
        }}</a-button>
      </NoData>
    </template>
    <LifecycleGuardDialog
      :view="actions.guardView.value"
      :action="actions.guardAction.value"
      :decision="actions.guardDecision.value"
      :usage-loading="data.usage.loading.value"
      @close="actions.closeGuard"
      @retry="actions.retryUsage"
    />
  </div>
</template>

<style scoped>
.installed-pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}

.installed-skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.installed-group {
  display: flex;
  flex-direction: column;
}

.installed-group-title {
  margin: 0 0 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.installed-group-list {
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}
</style>
