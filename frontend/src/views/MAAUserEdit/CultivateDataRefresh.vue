<template>
  <a-button
    size="large"
    :loading="controller.refreshing.value"
    :disabled="disabled || controller.refreshing.value"
    :aria-label="t('core.maaCopilot.refreshData')"
    :aria-busy="controller.refreshing.value"
    @click="refresh"
  >
    <template #icon><ReloadOutlined aria-hidden="true" /></template>
    {{ t('core.maaCopilot.refreshData') }}
  </a-button>
</template>

<script setup lang="ts">
import { inject, onScopeDispose } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { CultivateDataRefreshError } from '@/composables/useMaaCultivateDataApi'
import { cultivateDataRefreshKey } from './cultivateDataRefresh'

defineProps<{ disabled: boolean }>()
const { t } = useI18n()
const controller = inject(cultivateDataRefreshKey)
if (!controller) throw new Error('CultivateDataRefresh requires a cultivation controller')
const logger = window.electronAPI.getLogger('MAA 养成数据刷新')
let active = true
onScopeDispose(() => {
  active = false
})
const refresh = async () => {
  try {
    const result = await controller.refresh()
    if (!active) return
    if (result === 'success') message.success(t('core.maaCopilot.refreshDataSucceeded'))
    else if (result === 'partial') message.warning(t('core.maaCopilot.refreshDataDisplayFailed'))
  } catch (error) {
    logger.error(`刷新养成数据失败: ${error instanceof Error ? error.message : String(error)}`)
    if (active) {
      const key =
        error instanceof CultivateDataRefreshError && error.reason === 'cache'
          ? 'core.maaCopilot.refreshDataCacheFailed'
          : error instanceof CultivateDataRefreshError && error.reason === 'source'
            ? 'core.maaCopilot.refreshDataSourceFailed'
            : 'core.maaCopilot.refreshDataFailed'
      message.error(t(key))
    }
  }
}
</script>
