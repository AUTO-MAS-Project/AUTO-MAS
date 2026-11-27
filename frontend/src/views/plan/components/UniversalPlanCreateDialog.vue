<template>
  <AppModal
    v-model:open="open"
    size="sm"
    :title="title"
    :submitting="busy || creating"
    :ok-disabled="!selected || busy || creating"
    :mask-closable="false"
    @ok="confirm"
  >
    <a-form layout="vertical">
      <a-form-item :label="t('core.plan.universal.script')" required>
        <a-select
          v-model:value="selected"
          :options="options"
          :loading="busy"
          :placeholder="t('core.plan.universal.chooseScript')"
        />
      </a-form-item>
      <a-alert
        v-if="universal"
        type="info"
        show-icon
        :message="t('core.plan.universal.scriptHint')"
      />
      <a-alert v-if="error" type="error" show-icon :message="error" />
    </a-form>
  </AppModal>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppModal } from '@/components/ui'
import { useScriptApi } from '@/composables/useScriptApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
const { t } = useI18n()
const props = defineProps<{ activePlanId: string; creating?: boolean }>()
const emit = defineEmits<{ create: [scriptId: string] }>()
const { getScripts } = useScriptApi()
const open = ref(false)
const busy = ref(false)
const selected = ref<string>()
const options = ref<{ label: string; value: string }[]>([])
const error = ref('')
const title = ref('')
const universal = ref(false)
async function show(scriptType: string, planName: string, configType: string) {
  universal.value = configType === PLAN_CONFIG_TYPES.UNIVERSAL
  title.value = universal.value
    ? t('core.plan.universal.create')
    : t('core.plan.createTyped', { name: planName })
  open.value = true
  selected.value = undefined
  busy.value = true
  error.value = ''
  try {
    const scripts = await getScripts()
    options.value = scripts
      .filter(script => script.type === scriptType)
      .map(script => ({ label: script.name, value: script.uid }))
    if (!options.value.length) error.value = t('core.plan.universal.noScripts')
  } catch (reason) {
    error.value = String(reason)
  } finally {
    busy.value = false
  }
}
function confirm() {
  if (!selected.value || busy.value || props.creating) return
  emit('create', selected.value)
}
watch(
  () => props.activePlanId,
  () => {
    open.value = false
  }
)
defineExpose({ show })
</script>
