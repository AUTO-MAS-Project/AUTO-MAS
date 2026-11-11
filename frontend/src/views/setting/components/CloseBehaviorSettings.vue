<script setup lang="ts">
import { onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
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
  <a-radio-group
    :value="lastAction"
    name="close-action"
    class="close-action-options"
    :disabled="!loaded || saving"
    :aria-busy="saving"
    :aria-label="t('core.setting.basic.closeBehavior')"
    @change="(event: RadioChangeEvent) => handleChange(event.target.value)"
  >
    <a-radio value="quit" class="close-action-row">{{ t('core.setting.basic.closeQuit') }}</a-radio>
    <a-radio value="tray" class="close-action-row">{{
      t('core.setting.basic.closeToTray')
    }}</a-radio>
  </a-radio-group>
</template>

<style scoped>
.close-action-options {
  display: flex;
  flex-direction: column;
}

.close-action-row {
  display: flex;
  align-items: center;
  min-height: 42px;
  margin: 0 -6px;
  padding: 0 6px;
  border-radius: var(--ant-border-radius-sm);
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.close-action-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.close-action-row + .close-action-row {
  border-top: 1px solid var(--ant-color-split);
}
</style>
