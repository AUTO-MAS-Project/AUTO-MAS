<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { McpStatusData } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'

const props = defineProps<{ status: McpStatusData }>()
const { t } = useI18n()
const { getSettings, updateSettings } = useSettingsApi()
const enabled = ref<boolean | null>(null)
const loadFailed = ref(false)
const saving = ref(false)
let generation = 0

const restartRequired = computed(
  () =>
    enabled.value !== null &&
    (enabled.value && props.status.environmentEnabled) !== props.status.enabled
)

async function loadSetting() {
  const current = ++generation
  enabled.value = null
  loadFailed.value = false
  const settings = await getSettings()
  if (current !== generation) return
  enabled.value = settings?.Function?.IfEnableMCP ?? null
  loadFailed.value = enabled.value === null
}

async function saveEnabled(value: boolean | string | number) {
  const current = generation
  saving.value = true
  try {
    const saved = await updateSettings({ Function: { IfEnableMCP: !!value } })
    if (saved && current === generation) enabled.value = !!value
  } finally {
    saving.value = false
  }
}

// 后端重启后重新读取设置，避免把旧进程的待重启选择继续显示为当前值。
watch(() => props.status.instanceId, loadSetting, { immediate: true })
</script>

<template>
  <a-form layout="horizontal">
    <a-form-item :label="t('core.tools.mcp.startupEnabled')">
      <a-space wrap>
        <a-switch
          :checked="enabled === true"
          :loading="saving || (enabled === null && !loadFailed)"
          :disabled="enabled === null || saving || !status.environmentEnabled"
          :aria-label="t('core.tools.mcp.startupEnabled')"
          @change="saveEnabled"
        />
        <a-typography-text v-if="!status.environmentEnabled" type="secondary">
          {{ t('core.tools.mcp.environmentDisabled') }}
        </a-typography-text>
        <a-typography-text v-else-if="restartRequired" type="secondary">
          {{ t('core.tools.mcp.restartRequired') }}
        </a-typography-text>
      </a-space>
    </a-form-item>
    <a-alert
      v-if="loadFailed"
      type="error"
      show-icon
      :message="t('core.tools.mcp.settingsLoadFailed')"
    >
      <template #action>
        <a-button size="small" @click="loadSetting">{{ t('core.tools.mcp.refresh') }}</a-button>
      </template>
    </a-alert>
  </a-form>
</template>
