<script setup lang="ts">
import { onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'

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

const handleChange = async (change: Promise<void>): Promise<void> => {
  try {
    await change
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存关闭应用设置失败: ${errorMsg}`)
    message.error(t('core.setting.toast.saveFailed'))
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="close-settings">
    <a-radio-group
      :value="lastAction"
      name="close-action"
      class="close-action-options"
      :disabled="!loaded || saving"
      :aria-busy="saving"
      :aria-label="t('core.setting.basic.closeBehavior')"
      @change="(event: RadioChangeEvent) => handleChange(chooseAction(event.target.value, false))"
    >
      <a-radio value="quit" class="close-action-row">
        {{ t('core.setting.basic.closeQuit') }}
      </a-radio>
      <a-radio value="tray" class="close-action-row">
        {{ t('core.setting.basic.closeToTray') }}
      </a-radio>
    </a-radio-group>
    <a-checkbox
      class="close-confirmation"
      :checked="confirmBeforeClose"
      :disabled="!loaded || saving"
      :aria-busy="saving"
      @change="
        (event: CheckboxChangeEvent) => handleChange(setConfirmationEnabled(event.target.checked))
      "
    >
      {{ t('core.setting.basic.closeConfirmation') }}
    </a-checkbox>
  </div>
</template>

<style scoped>
.close-action-options {
  display: flex;
  flex-direction: column;
}

.close-action-row,
.close-confirmation {
  display: flex;
  align-items: center;
  min-height: 36px;
  margin: 0;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 500;
}

.close-confirmation {
  padding-left: 24px;
}
</style>
