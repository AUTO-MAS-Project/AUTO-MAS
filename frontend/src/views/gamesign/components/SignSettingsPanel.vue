<!--
  游戏社区：签到设置区。
  只负责把本体 ToolsConfig.SignFlow 的布尔开关渲染成配置行，
  写回仍走父级传入的 onFieldChange，避免在子组件里直接操作配置对象。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { ToolsConfig_SignFlow } from '@/api'
import { SettingRow } from '@/components/ui'
import DocLink from '@/components/DocLink.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { getConfig, saveConfig } from '@/utils/config'
import { formatConfigDate } from '@/utils/configDateTime'

const props = defineProps<{
  config: ToolsConfig_SignFlow
  disabled?: boolean
  onFieldChange?: <K extends keyof ToolsConfig_SignFlow>(
    key: K,
    value: ToolsConfig_SignFlow[K]
  ) => void | Promise<void>
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('游戏社区')

const notifySaving = ref(false)
const homeActivityNotesVisible = ref(false)
const homeActivityNotesSaving = ref(false)

const lastSignDate = computed(() => {
  const formatted = formatConfigDate(props.config.LastSignDate, 8 * 60)
  return formatted && formatted !== '2000-01-01'
    ? formatted
    : t('core.signflow.section.neverSigned')
})

const handleChange = async <K extends keyof ToolsConfig_SignFlow>(
  key: K,
  value: ToolsConfig_SignFlow[K]
) => {
  if (!props.onFieldChange) return
  try {
    await props.onFieldChange(key, value)
  } catch {
    // 父级 updateTools 已提示失败并回滚，这里不重复打扰用户
  }
}

const handleNotifyEnabledChange = async (value: boolean) => {
  notifySaving.value = true
  try {
    await handleChange('NotifyEnabled', value)
  } finally {
    notifySaving.value = false
  }
}

const loadHomeActivityNotes = async () => {
  try {
    const config = await getConfig()
    homeActivityNotesVisible.value = config.homeLayout?.activityNotesVisible === true
  } catch (error) {
    logger.error(`读取首页便笺开关失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

const handleHomeActivityNotesChange = async (value: boolean) => {
  const previous = homeActivityNotesVisible.value
  homeActivityNotesVisible.value = value
  homeActivityNotesSaving.value = true
  try {
    const config = await getConfig()
    await saveConfig({
      homeLayout: {
        ...(config.homeLayout ?? { moduleOrder: [], hiddenModules: [] }),
        activityNotesVisible: value,
      },
    })
  } catch (error) {
    homeActivityNotesVisible.value = previous
    logger.error(`保存首页便笺开关失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error(t('core.signflow.toast.homeActivityEnableSaveFailed'))
  } finally {
    homeActivityNotesSaving.value = false
  }
}

onMounted(() => {
  void loadHomeActivityNotes()
})
</script>

<template>
  <section class="sign-settings">
    <div class="settings-header">
      <h3>{{ t('core.signflow.section.settings') }}</h3>
      <DocLink :url="MAS_DOC_URLS.gameSign" />
    </div>
    <p class="settings-hint">{{ t('core.signflow.section.settingsHint') }}</p>

    <SettingRow
      :label="t('core.signflow.section.enable')"
      :description="t('core.signflow.section.enableDesc')"
    >
      <a-switch
        :checked="config.Enabled === true"
        :disabled="disabled"
        @change="handleChange('Enabled', Boolean($event))"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.signflow.section.activityEnable')"
      :description="t('core.signflow.section.activityEnableDesc')"
    >
      <a-switch
        :checked="config.ActivityEnabled !== false"
        :disabled="disabled"
        @change="handleChange('ActivityEnabled', Boolean($event))"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.signflow.section.homeActivityEnable')"
      :description="t('core.signflow.section.homeActivityEnableDesc')"
    >
      <a-switch
        :checked="homeActivityNotesVisible"
        :loading="homeActivityNotesSaving"
        :disabled="disabled"
        @change="handleHomeActivityNotesChange(Boolean($event))"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.signflow.section.notify')"
      :description="t('core.signflow.section.notifyDesc')"
    >
      <a-switch
        :checked="config.NotifyEnabled === true"
        :loading="notifySaving"
        :disabled="disabled"
        @change="handleNotifyEnabledChange(Boolean($event))"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.signflow.section.runOnStartup')"
      :description="t('core.signflow.section.runOnStartupDesc')"
    >
      <a-switch
        :checked="config.RunOnStartup === true"
        :disabled="disabled"
        @change="handleChange('RunOnStartup', Boolean($event))"
      />
    </SettingRow>

    <p class="settings-footnote">{{ t('core.signflow.section.privacyNotice') }}</p>

    <SettingRow
      :label="t('core.signflow.section.lastSign')"
      :description="t('core.signflow.section.lastSignDesc')"
    >
      <span class="last-sign-value">{{ lastSignDate }}</span>
    </SettingRow>
  </section>
</template>

<style scoped>
.sign-settings {
  display: flex;
  flex-direction: column;
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.settings-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: var(--ant-color-text);
}

.settings-hint {
  margin: 4px 0 8px;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-secondary);
}

.settings-footnote {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-text-tertiary);
}

.last-sign-value {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}
</style>
