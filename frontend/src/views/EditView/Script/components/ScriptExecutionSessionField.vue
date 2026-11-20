<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { fetchScriptExecutionSession } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'
import { useConfigQuery } from '@/services/configUiSync'
import { useDesktopSessionAvailability } from '@/views/desktopSession/useDesktopSessionAvailability'
import type { GeneralConfig_Run } from '@/api'

const { t } = useI18n()
const scriptId = useRoute().params.id as string
const available = useDesktopSessionAvailability()
const { data, isPending, refetch } = useConfigQuery({
  queryKey: ['script-execution-session', scriptId],
  queryFn: ({ signal }) => fetchScriptExecutionSession(scriptId, signal),
})
const { saveField, isSaving } = useScriptSaveMutation({
  scriptId,
  isInitializing: isPending,
  logger: window.electronAPI.getLogger('执行会话'),
})
const supported = computed(() => available.value && data.value?.supported === true)
const visible = computed(() => supported.value || data.value?.value === 'desktop')
watch(available, ready => {
  if (ready) void refetch()
})
const options = computed(() => [
  { value: 'main', label: t('bootstrap.desktopSession.mainFallbackMainGroup') },
  {
    value: 'desktop',
    label: t('bootstrap.desktopSession.title'),
    disabled: !supported.value,
  },
])

async function save(value: GeneralConfig_Run['ExecutionSession']) {
  if (value === data.value?.value) return
  if (await saveField('Run', 'ExecutionSession', value)) await refetch()
}
</script>

<template>
  <a-row v-if="visible" :gutter="24">
    <a-col :xs="24" :lg="12">
      <a-form-item
        html-for="desktop-execution-session"
        :label="t('bootstrap.desktopSession.executionSession')"
        :extra="t('bootstrap.desktopSession.executionSessionHint')"
        :help="supported ? undefined : t('bootstrap.desktopSession.executionSessionUnsupported')"
        :validate-status="supported ? undefined : 'warning'"
      >
        <a-select
          id="desktop-execution-session"
          :value="data?.value"
          :options="options"
          :loading="isSaving"
          :disabled="isSaving"
          @change="save"
        />
      </a-form-item>
    </a-col>
  </a-row>
</template>
