<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import NoData from '@/components/NoData.vue'
import { installPhaseLabelKey } from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'
import UpdateRow from './UpdateRow.vue'
import { restartTask, upToDateCount } from './updatesModel'

/** 「更新」页签：可更新插件列表、需要重启的集中提示、全部最新时的空状态。 */
const { t } = useI18n()
const { data, installation, lock } = usePluginCenter()

const firstLoading = computed(() => data.catalog.loading.value && !data.catalog.loaded.value)
/** 目录读失败时不说「全部最新」，失败条由外壳显示。 */
const allLatest = computed(
  () => data.catalog.loaded.value && !data.catalog.error.value && !data.updates.value.length
)
const othersLatest = computed(() =>
  data.updates.value.length ? upToDateCount(data.market.value) : 0
)

const restarting = computed(() => restartTask(installation.active.value))
const restartName = computed(() => {
  const task = restarting.value
  if (!task) return null
  return data.market.value.find(entry => entry.uid === task.uid)?.name ?? task.pluginId
})
const restartText = computed(() =>
  restarting.value ? t(installPhaseLabelKey(restarting.value.phase, restarting.value.upgrade)) : ''
)
</script>

<template>
  <div class="updates-pane">
    <a-alert
      v-if="restarting"
      :type="restarting.phase === 'restarting' ? 'info' : 'warning'"
      show-icon
      role="status"
    >
      <template #message>
        <span class="updates-restart">
          <strong v-if="restartName">{{ restartName }}</strong>
          <span>{{ restartText }}</span>
        </span>
      </template>
    </a-alert>
    <div v-if="firstLoading" class="updates-loading"><a-spin /></div>
    <NoData v-else-if="allLatest" :description="t('core.plugins.updates.allLatest')" />
    <template v-else-if="data.updates.value.length">
      <div class="updates-list">
        <UpdateRow
          v-for="item in data.updates.value"
          :key="item.entry.uid"
          :item="item"
          :task="installation.taskOf(item.entry.uid)"
          :busy="lock.busy.value"
          @update="installation.install(item.entry.document)"
        />
      </div>
      <p v-if="othersLatest" class="updates-others">
        {{ t('core.plugins.updates.othersLatest', { count: othersLatest }) }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.updates-pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
}

.updates-loading {
  display: flex;
  min-height: 160px;
  align-items: center;
  justify-content: center;
}

.updates-list {
  display: flex;
  flex-direction: column;
}

.updates-restart {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
}

.updates-others {
  margin: 0;
  font-size: 12px;
  line-height: 20px;
  color: var(--ant-color-text-secondary);
}
</style>
