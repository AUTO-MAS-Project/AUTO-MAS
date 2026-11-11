<script setup lang="ts">
import { onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'
import type { AppCloseAction } from '@/utils/appClosePreferences'

const logger = window.electronAPI.getLogger('关闭应用设置')
const { t } = useI18n()
const { lastAction, loaded, saving, load, setDefaultAction } = useAppClosePreferences()

const handleChange = async (action: AppCloseAction): Promise<void> => {
  try {
    await setDefaultAction(action)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存关闭行为设置失败: ${errorMsg}`)
    message.error(t('core.setting.toast.saveFailed'))
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <a-segmented
    :value="lastAction"
    :options="[
      { label: t('core.setting.basic.closeQuit'), value: 'quit' },
      { label: t('core.setting.basic.closeToTray'), value: 'tray' },
    ]"
    :disabled="!loaded || saving"
    :aria-busy="saving"
    :aria-label="t('core.setting.basic.closeBehavior')"
    @change="(value: string | number) => handleChange(value as AppCloseAction)"
  />
</template>
