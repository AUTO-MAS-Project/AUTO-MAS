<template>
  <div class="form-item-vertical">
    <div class="form-label-wrapper">
      <span class="form-label">{{ t('core.setting.basic.closeConfirmation') }}</span>
      <a-switch
        :checked="confirmBeforeClose"
        :loading="saving"
        :disabled="!loaded || saving"
        @change="handleChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'

const logger = window.electronAPI.getLogger('关闭应用设置')
const { t } = useI18n()
const { confirmBeforeClose, loaded, saving, load, setConfirmationEnabled } =
  useAppClosePreferences()

const handleChange = async (enabled: boolean): Promise<void> => {
  try {
    await setConfirmationEnabled(enabled)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存关闭确认设置失败: ${errorMsg}`)
    message.error(t('core.setting.toast.saveFailed'))
  }
}

onMounted(() => {
  void load()
})
</script>
