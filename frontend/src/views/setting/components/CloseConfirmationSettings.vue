<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'
import type { AppCloseAction } from '@/utils/appClosePreferences'
import SettingRow from '@/components/ui/SettingRow.vue'

const logger = window.electronAPI.getLogger('关闭应用设置')
const { t } = useI18n()
const {
  confirmBeforeClose,
  lastAction,
  loaded,
  saving,
  load,
  setConfirmationEnabled,
  chooseAction,
} = useAppClosePreferences()

const closeActionOptions = computed(() => [
  { label: t('core.setting.basic.closeQuit'), value: 'quit' },
  { label: t('core.setting.basic.closeToTray'), value: 'tray' },
])

// 「关闭后再提示」只在最小化到托盘时有意义；直接退出时整行置灰，
// 但保留已保存的值，切回托盘不会丢掉用户之前的选择。
const confirmationAvailable = () => lastAction.value === 'tray'

const handleChange = async (change: Promise<void>): Promise<void> => {
  try {
    await change
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存关闭应用设置失败: ${errorMsg}`)
    message.error(t('core.setting.toast.saveFailed'))
  }
}

const handleActionChange = (value: string | number | boolean) =>
  handleChange(chooseAction(value as AppCloseAction, false))

const handleConfirmationChange = (event: CheckboxChangeEvent) =>
  handleChange(setConfirmationEnabled(event.target.checked === true))

onMounted(() => {
  void load()
})
</script>

<template>
  <SettingRow
    :label="t('core.setting.basic.closeAction')"
    :aria-busy="saving"
  >
    <a-segmented
      class="close-action-options"
      :value="lastAction"
      :options="closeActionOptions"
      :disabled="!loaded"
      :loading="saving"
      :block="false"
      :aria-label="t('core.setting.basic.closeAction')"
      @change="handleActionChange"
    />
  </SettingRow>

  <SettingRow
    child
    :disabled="!confirmationAvailable()"
    :label="t('core.setting.basic.closeConfirmation')"
    :description="t('core.setting.basic.closeConfirmationTip')"
  >
    <a-checkbox
      :checked="confirmBeforeClose"
      :disabled="!loaded || saving || !confirmationAvailable()"
      :aria-busy="saving"
      :aria-label="t('core.setting.basic.closeConfirmation')"
      @change="handleConfirmationChange"
    />
  </SettingRow>
</template>

<style scoped>
.close-action-options {
  min-width: 0;
}
</style>
