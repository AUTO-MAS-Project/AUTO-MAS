<template>
  <a-space direction="vertical" style="width: 100%" :size="16">
    <a-descriptions :column="1" size="small"
      ><a-descriptions-item :label="t('core.plan.universal.script')">{{
        scriptName || '—'
      }}</a-descriptions-item></a-descriptions
    >
    <a-alert type="info" show-icon :message="t('core.plan.universal.intro')" />
    <a-space>
      <span>{{ t('core.plan.universal.reset') }}</span>
      <a-input-number
        :value="info?.ResetHour ?? 4"
        :min="0"
        :max="23"
        :disabled="busy || locked"
        :aria-label="t('core.plan.universal.hourLabel')"
        @change="saveTime('ResetHour', $event)"
      />
      <span>{{ t('core.plan.universal.hour') }}</span>
      <a-input-number
        :value="info?.ResetMinute ?? 0"
        :min="0"
        :max="59"
        :disabled="busy || locked"
        :aria-label="t('core.plan.universal.minuteLabel')"
        @change="saveTime('ResetMinute', $event)"
      />
      <span>{{ t('core.plan.universal.minute') }}</span>
    </a-space>
    <a-alert
      v-if="taskId"
      type="warning"
      show-icon
      :message="t('core.plan.universal.session', { day: editingLabel })"
    >
      <template #action
        ><a-button :loading="busy" @click="saveSession">{{
          t('core.plan.universal.save')
        }}</a-button></template
      >
    </a-alert>
    <a-alert v-if="sessionError" type="error" :message="sessionError" show-icon />
    <a-list bordered :data-source="days">
      <template #renderItem="{ item }">
        <a-list-item>
          <span
            >{{ label(item) }} ·
            {{
              savedDays.includes(planColumnGroup(item))
                ? t('core.plan.universal.configured')
                : t('core.plan.universal.unconfigured')
            }}</span
          >
          <a-button :disabled="Boolean(taskId) || busy || locked" @click="editDay(item)">{{
            t('core.plan.universal.configure')
          }}</a-button>
        </a-list-item>
      </template>
    </a-list>
  </a-space>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { TaskCreateIn, type UniversalPlanConfig } from '@/api'
import { requestTaskStart, stopNativeConfig, readTaskStatus } from '@/composables/useTaskApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { readUniversalPlanState } from '@/composables/usePlanApi'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { planDayKeys, planColumnGroup, planDayLabel, type PlanMode } from '@/utils/planDays'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'

const props = defineProps<{
  tableData: UniversalPlanConfig
  currentMode: PlanMode
  planId: string
  handlePlanChange: PlanChangeHandler
}>()
const { t } = useI18n()
const { getScript } = useScriptApi()
const scriptName = ref('')
const info = computed(() => props.tableData.Info)
const { configLocked: locked } = useScriptConfigLock(() => info.value?.ScriptId ?? '')
const days = computed(() =>
  props.currentMode === 'ALL' ? ['ALL'] : planDayKeys(props.currentMode, info.value?.RotateDays)
)
const savedDays = ref<string[]>([])
async function refreshDays() {
  const id = props.planId
  try {
    const days = await readUniversalPlanState(id)
    if (props.planId === id && !disposed) savedDays.value = days
  } catch (error) {
    if (!disposed && props.planId === id) sessionError.value = String(error)
  }
}
const busy = ref(false)
const taskId = ref('')
const editingLabel = ref('')
const sessionError = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
function label(day: string) {
  if (day === 'ALL') return t('core.plan.modeAll')
  const value = planDayLabel(day)
  return t(value.key, value.params)
}
async function saveTime(field: 'ResetHour' | 'ResetMinute', value: number | string | null) {
  if (typeof value !== 'number') return
  busy.value = true
  try {
    await props.handlePlanChange(`Info.${field}`, value)
  } finally {
    busy.value = false
  }
}
async function pollSession() {
  const id = taskId.value
  if (!id || disposed) return
  try {
    const result = await readTaskStatus(id)
    if (taskId.value !== id || disposed) return
    if (result.code !== 200)
      throw new Error(result.message || t('core.plan.universal.sessionReadFailed'))
    if (result.status !== 'running') {
      taskId.value = ''
      await refreshDays()
      sessionError.value =
        result.status === 'error'
          ? result.error || result.detail || t('core.plan.universal.sessionFailed')
          : ''
      return
    }
    sessionError.value = ''
  } catch (error) {
    sessionError.value = String(error)
  }
  if (!disposed) timer = setTimeout(pollSession, 2000)
}
async function editDay(day: string) {
  if (!info.value?.ScriptId) return
  busy.value = true
  sessionError.value = ''
  try {
    const result = await requestTaskStart({
      taskId: info.value.ScriptId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
      planId: props.planId,
      planDay: planColumnGroup(day),
    })
    if (result.code !== 200) throw new Error(result.message || t('core.plan.universal.startFailed'))
    taskId.value = result.taskId
    editingLabel.value = label(day)
    void pollSession()
  } catch (error) {
    message.error(String(error))
  } finally {
    busy.value = false
  }
}
async function saveSession() {
  busy.value = true
  try {
    const result = await stopNativeConfig(taskId.value, 'save')
    if (result.code !== 200) throw new Error(result.message || t('core.plan.universal.saveFailed'))
  } catch (error) {
    message.error(String(error))
  } finally {
    busy.value = false
  }
}
defineExpose({
  beforeLeave: () => {
    if (!taskId.value && !busy.value) return true
    message.warning(t('core.plan.universal.finishFirst'))
    return false
  },
})
watch(
  () => props.planId,
  () => {
    savedDays.value = []
    void refreshDays()
  },
  { immediate: true }
)
watch(
  () => info.value?.ScriptId,
  async id => {
    scriptName.value = ''
    if (!id) return
    const script = await getScript(id)
    if (info.value?.ScriptId === id && !disposed) scriptName.value = script?.name ?? ''
  },
  { immediate: true }
)
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>
