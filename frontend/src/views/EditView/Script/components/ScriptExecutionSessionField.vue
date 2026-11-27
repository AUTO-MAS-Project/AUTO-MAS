<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import type { GeneralConfig_Run } from '@/api'
import { fetchScriptExecutionSession } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'
import { useConfigQuery } from '@/services/configUiSync'

type ExecutionSession = NonNullable<GeneralConfig_Run['ExecutionSession']>

const { t } = useI18n()
const scriptId = useRoute().params.id as string
const { data, isPending, refetch } = useConfigQuery({
  queryKey: ['script-execution-session', scriptId],
  queryFn: ({ signal }) => fetchScriptExecutionSession(scriptId, signal),
})
const { saveField, isSaving } = useScriptSaveMutation({
  scriptId,
  isInitializing: isPending,
  logger: window.electronAPI.getLogger('执行会话'),
  afterFieldSave: async () => {
    await refetch({ throwOnError: true })
  },
})
const unavailableSelection = computed(
  () => data.value?.value === 'desktop' && !data.value.supported
)
const options = computed(() => [
  { value: 'main', label: t('bootstrap.desktopSession.mainFallbackMainGroup') },
  {
    value: 'desktop',
    label: t('bootstrap.desktopSession.title'),
    disabled: !data.value?.supported,
  },
])

function save(value: ExecutionSession) {
  if (value === data.value?.value) return
  return saveField('Run', 'ExecutionSession', value)
}
</script>

<template>
  <a-row v-if="data?.configurable" :gutter="24">
    <a-col :xs="24" :lg="12">
      <a-form-item
        html-for="desktop-execution-session"
        :label="t('bootstrap.desktopSession.executionSession')"
        :help="data.reason ? t(`bootstrap.desktopSession.reasons.${data.reason}`) : undefined"
        :extra="
          unavailableSelection ? undefined : t('bootstrap.desktopSession.executionSessionHint')
        "
        :validate-status="unavailableSelection ? 'warning' : undefined"
      >
        <a-select
          id="desktop-execution-session"
          :value="data.value"
          :placeholder="t('bootstrap.desktopSession.chooseExecutionSession')"
          :options="options"
          :loading="isSaving"
          :disabled="isSaving"
          @change="save"
        />
      </a-form-item>
    </a-col>
  </a-row>
</template>
