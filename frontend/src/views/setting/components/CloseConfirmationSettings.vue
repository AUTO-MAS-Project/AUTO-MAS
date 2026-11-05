<script setup lang="ts">
import { onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'

const logger = window.electronAPI.getLogger('关闭应用设置')
const { t } = useI18n()
const { confirmBeforeClose, loaded, saving, load, setConfirmationEnabled } =
  useAppClosePreferences()

const handleChange = async (checked: boolean): Promise<void> => {
  try {
    await setConfirmationEnabled(checked)
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
  <!-- 只输出控件本体：标签与提示由父级 SettingRow 承担 -->
  <a-switch
    :checked="confirmBeforeClose"
    :loading="saving"
    :disabled="!loaded || saving"
    :aria-busy="saving"
    :aria-label="t('core.setting.basic.closeConfirmation')"
    @change="(checked: boolean | string | number) => handleChange(!!checked)"
  />
</template>
