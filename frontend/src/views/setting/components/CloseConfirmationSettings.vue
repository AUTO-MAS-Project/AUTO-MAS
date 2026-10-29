<script setup lang="ts">
import { onMounted } from 'vue'
import { message } from 'ant-design-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import { useI18n } from 'vue-i18n'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'

const logger = window.electronAPI.getLogger('关闭应用设置')
const { t } = useI18n()
const { confirmBeforeClose, loaded, saving, load, setConfirmationEnabled } =
  useAppClosePreferences()

const handleChange = async (event: CheckboxChangeEvent): Promise<void> => {
  try {
    await setConfirmationEnabled(event.target.checked)
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

<template>
  <div class="setting-check-row" :aria-busy="saving">
    <a-checkbox :checked="confirmBeforeClose" :disabled="!loaded || saving" @change="handleChange">
      {{ t('core.setting.basic.closeConfirmation') }}
    </a-checkbox>
  </div>
</template>

<style scoped>
.setting-check-row {
  display: flex;
  align-items: center;
  min-height: 28px;
}

.setting-check-row :deep(.ant-checkbox-wrapper) {
  color: var(--ant-color-text);
  font-size: 14px;
}
</style>
