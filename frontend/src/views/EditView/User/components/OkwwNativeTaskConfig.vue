<template>
  <a-alert v-if="error" type="error" show-icon :message="error">
    <template #action
      ><a-button @click="load">{{ t('core.edit.okwwEchoRetry') }}</a-button></template
    >
  </a-alert>
  <a-spin :spinning="loading || saving">
    <a-typography-paragraph v-if="!overlayEnabled" type="secondary">{{
      t('core.edit.okwwEchoOverlayOff')
    }}</a-typography-paragraph>
    <NativeConfigForm
      :fields="visibleFields"
      :labels="labels"
      :hints="hints"
      :values="values"
      :disabled="disabled || loading || saving"
      label-prefix="core.edit.okwwEcho"
      option-prefix="core.edit.okwwEchoOption"
      @change="change"
    />
  </a-spin>
</template>
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useOkwwNativeConfigApi } from '@/composables/useOkwwNativeConfigApi'
import NativeConfigForm from '@/components/NativeConfigForm.vue'
import type { OkwwPanelKind } from '@/types/nativeConfig'
import type { OkwwConfigField } from '@/api'
const props = defineProps<{
  scriptId: string
  userId: string
  snapshot: Record<string, unknown>
  kind: OkwwPanelKind
  disabled: boolean
  overlayEnabled: boolean
}>()
const emit = defineEmits<{ saved: []; busy: [value: boolean] }>()
const { t, locale } = useI18n()
const hints = computed((): Record<string, string> => {
  if (props.kind === 'daily') return { 'Exit After Task': t('core.edit.okwwDailyExitHint') }
  if (props.kind === 'monthly')
    return {
      'Check Monthly Card': t('core.edit.okwwMonthlyCheckHint'),
      'Monthly Card Time': t('core.edit.okwwMonthlyTimeHint'),
    }
  return {}
})

const { readConfig, saveConfig } = useOkwwNativeConfigApi()
const { isSaving: saving, enqueue } = useSaveQueue()
watch(saving, value => emit('busy', value), { flush: 'sync' })
const loading = ref(false)
const error = ref('')
const fields = ref<OkwwConfigField[]>([])
// 每日附加任务不读取4C退出选项，仅隐藏控件，保留原生值。
const visibleFields = computed(() =>
  fields.value.filter(field => props.kind !== 'echo' || field.name !== 'Exit After Task')
)
const labels = ref<Record<string, string>>({})
const values = ref<Record<string, unknown>>({})
let revision = 0
watch(() => [props.scriptId, props.userId, props.kind, props.snapshot, locale.value], load, {
  immediate: true,
})
onBeforeUnmount(() => {
  revision++
  emit('busy', false)
})
async function load() {
  const current = ++revision
  if (!props.userId) return
  loading.value = true
  error.value = ''
  try {
    const response = await readConfig(props.scriptId, props.userId, props.kind)
    if (current === revision) {
      values.value = response.values ?? {}
      fields.value = response.fields ?? []
      labels.value = response.labels ?? {}
    }
  } catch (e) {
    if (current === revision) error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (current === revision) loading.value = false
  }
}
async function change(name: string, value: unknown) {
  error.value = ''
  values.value = { ...values.value, [name]: value }
  const snapshot = JSON.parse(JSON.stringify(values.value)) as Record<string, unknown>
  // 不将只读的计划显示值作为账号默认值提交。
  for (const field of fields.value) {
    if (field.disabled) delete snapshot[field.name]
  }
  const current = revision
  await enqueue(async () => {
    try {
      await saveConfig(props.scriptId, props.userId, props.kind, snapshot)
      if (current === revision) emit('saved')
      return true
    } catch (e) {
      if (current === revision) error.value = e instanceof Error ? e.message : String(e)
      return false
    }
  })
}
</script>
