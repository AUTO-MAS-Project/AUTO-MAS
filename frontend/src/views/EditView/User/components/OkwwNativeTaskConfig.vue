<template>
  <a-alert v-if="error" type="error" show-icon :message="error">
    <template #action
      ><a-button @click="load(true)">{{ t('core.edit.okwwEchoRetry') }}</a-button></template
    >
  </a-alert>
  <a-spin :spinning="initialLoading" :delay="200">
    <a-typography-paragraph v-if="!overlayEnabled" type="secondary">{{
      t('core.edit.okwwEchoOverlayOff')
    }}</a-typography-paragraph>
    <NativeConfigForm
      :fields="visibleFields"
      :labels="labels"
      :hints="hints"
      :values="displayValues"
      :disabled="disabled || initialLoading"
      :label-prefix="labelPrefix"
      :option-prefix="optionPrefix"
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
  contextKey: string
  snapshot: Record<string, unknown>
  kind: OkwwPanelKind
  customArguments?: boolean
  disabled: boolean
  overlayEnabled: boolean
}>()
const emit = defineEmits<{ saved: []; busy: [value: boolean] }>()
const { t, locale } = useI18n()
const labelPrefix = 'core.edit.okwwEcho.'
const optionPrefix = 'core.edit.okwwEchoOption.'
const forcedExit = computed(() => props.kind === 'daily' && !props.customArguments)
const hints = computed((): Record<string, string> => {
  if (props.kind === 'daily')
    return {
      'Exit After Task': t(
        forcedExit.value ? 'core.edit.okwwForcedExitHint' : 'core.edit.okwwDailyExitHint'
      ),
    }
  if (props.kind === 'monthly')
    return {
      'Check Monthly Card': t('core.edit.okwwMonthlyCheckHint'),
      'Monthly Card Time': t('core.edit.okwwMonthlyTimeHint'),
    }
  return {}
})

const { readConfig, saveConfig } = useOkwwNativeConfigApi()
const { isSaving: saving, enqueue } = useSaveQueue()
let needsRefresh = false
let saveFailed = false
watch(
  saving,
  value => {
    emit('busy', value)
    if (!value && needsRefresh) {
      needsRefresh = false
      emit('saved')
    }
  },
  { flush: 'sync' }
)
const loading = ref(false)
const error = ref('')
const fields = ref<OkwwConfigField[]>([])
const initialLoading = computed(() => loading.value && fields.value.length === 0)
// 三种传送序号按当前传送类型显示，共用第三个位置。
const echoFieldOrder = [
  'Teleport to Boss',
  'Boss Level',
  'Which Weekly Boss to Teleport',
  'Which Boss Challenge to Teleport',
  'Which Special Nightmare to Teleport',
  'Repeat Farm Count',
  'Boss',
  'Combat Wait Time',
]
const echoPosition = (name: string) => {
  const index = echoFieldOrder.indexOf(name)
  return index < 0 ? echoFieldOrder.length : index
}
// 每日附加任务不读取4C退出选项，仅隐藏控件，保留原生值。
const visibleFields = computed(() =>
  fields.value
    .filter(field => props.kind !== 'echo' || field.name !== 'Exit After Task')
    .sort((a, b) => (props.kind === 'echo' ? echoPosition(a.name) - echoPosition(b.name) : 0))
    .map(field =>
      forcedExit.value && field.name === 'Exit After Task' ? { ...field, disabled: true } : field
    )
)
const labels = ref<Record<string, string>>({})
const values = ref<Record<string, unknown>>({})
const displayValues = computed(() =>
  forcedExit.value ? { ...values.value, 'Exit After Task': true } : values.value
)
let revision = 0
let draftRevision = 0
watch(
  () => [
    props.scriptId,
    props.userId,
    props.kind,
    JSON.stringify(props.snapshot),
    props.contextKey,
    locale.value,
  ],
  (current, previous) => {
    if (!previous || current.some((value, index) => value !== previous[index])) void load()
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  revision++
  emit('busy', false)
})
async function load(discardDraft = false) {
  if (!props.userId || saving.value || (saveFailed && !discardDraft)) return
  if (discardDraft) saveFailed = false
  const current = ++revision
  const draft = draftRevision
  loading.value = true
  error.value = ''
  try {
    const response = await readConfig(props.scriptId, props.userId, props.kind)
    if (current === revision) {
      if (draft === draftRevision && !saving.value) values.value = response.values ?? {}
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
  draftRevision++
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
      if (current === revision) {
        saveFailed = false
        needsRefresh = true
      }
      return true
    } catch (e) {
      if (current === revision) {
        needsRefresh = false
        saveFailed = true
        error.value = e instanceof Error ? e.message : String(e)
      }
      return false
    }
  })
}
</script>
