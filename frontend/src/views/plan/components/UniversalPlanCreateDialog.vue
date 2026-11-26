<template>
  <AppModal
    v-model:open="open"
    size="sm"
    :title="t('core.plan.universal.create')"
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
      <a-alert type="info" show-icon :message="t('core.plan.universal.scriptHint')" />
      <a-alert v-if="error" type="error" show-icon :message="error" />
    </a-form>
  </AppModal>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AppModal } from '@/components/ui'
import { useScriptApi } from '@/composables/useScriptApi'
const { t } = useI18n()
// 通用脚本计划表仅供 General 使用
const UNIVERSAL_PLAN_SCRIPT_TYPE = 'General'
const props = defineProps<{ activePlanId: string; creating?: boolean }>()
const emit = defineEmits<{ create: [scriptId: string] }>()
const { getScripts } = useScriptApi()
const open = ref(false)
const busy = ref(false)
const selected = ref<string>()
const options = ref<{ label: string; value: string }[]>([])
const error = ref('')
async function show() {
  open.value = true
  selected.value = undefined
  busy.value = true
  error.value = ''
  try {
    const scripts = await getScripts()
    options.value = scripts
      .filter(script => script.type === UNIVERSAL_PLAN_SCRIPT_TYPE)
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
