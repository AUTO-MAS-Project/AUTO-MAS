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
        :disabled="busy || Boolean(taskId) || locked"
        :aria-label="t('core.plan.universal.hourLabel')"
        @change="saveTime('ResetHour', $event)"
      />
      <span>{{ t('core.plan.universal.hour') }}</span>
      <a-input-number
        :value="info?.ResetMinute ?? 0"
        :min="0"
        :max="59"
        :disabled="busy || Boolean(taskId) || locked"
        :aria-label="t('core.plan.universal.minuteLabel')"
        @change="saveTime('ResetMinute', $event)"
      />
      <span>{{ t('core.plan.universal.minute') }}</span>
    </a-space>
    <a-alert
      v-if="taskId"
      type="warning"
      show-icon
      :message="t('core.plan.universal.sessionRunning', { day: editingLabel })"
    >
      <template #action
        ><a-button :loading="stopping" :disabled="starting" @click="finishSession">{{
          t('core.plan.universal.save')
        }}</a-button></template
      >
    </a-alert>
    <a-list bordered :data-source="days">
      <template #renderItem="{ item }">
        <a-list-item>
          <a-space size="small">
            <span>{{ label(item) }}</span>
            <a-tag :color="isConfigured(item) ? 'success' : undefined">
              {{
                isConfigured(item)
                  ? t('core.plan.universal.configured')
                  : t('core.plan.universal.unconfigured')
              }}
            </a-tag>
          </a-space>
          <a-button
            :disabled="Boolean(taskId) || starting || stopping || locked"
            @click="editDay(item)"
            >{{ t('core.plan.universal.gotoConfig') }}</a-button
          >
        </a-list-item>
      </template>
    </a-list>
  </a-space>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { type UniversalPlanConfig } from '@/api'
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
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
const busy = ref(false)
const editingLabel = ref('')
let disposed = false

// 复用脚本页的原生设置会话：同一个「保存并结束」语义、超时自动保存与丢弃提示
const {
  taskId,
  configLoading: starting,
  stopping,
  saveSession,
  dispose: disposeSession,
} = useNativeGuiSession({
  loggerName: '计划管理',
  keys: {
    stopFailed: 'core.plan.universal.stopFailed',
    startFailed: 'core.plan.universal.startFailed',
    setupFailed: 'core.plan.universal.setupFailed',
    opened: 'core.plan.universal.sessionOpened',
    viewOpened: 'core.plan.universal.sessionOpened',
    timeoutWarn: 'core.plan.universal.sessionTimeoutWarn',
    saved: 'core.plan.universal.sessionSaved',
    saveFailed: 'core.plan.universal.saveFailed',
  },
})

function label(day: string) {
  if (day === 'ALL') return t('core.plan.modeAll')
  const value = planDayLabel(day)
  return t(value.key, value.params)
}

function isConfigured(day: string) {
  return savedDays.value.includes(planColumnGroup(day))
}

async function refreshDays() {
  const id = props.planId
  try {
    const days = await readUniversalPlanState(id)
    if (props.planId === id && !disposed) savedDays.value = days
  } catch (error) {
    if (!disposed && props.planId === id) message.error(String(error))
  }
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

/** 计划日期编辑延期，当前不创建配置会话。 */
function editDay(_day: string) {
  // TODO(插件迁移，#1845)：计划日期编辑不接入旧平铺任务参数，保留计划配置与模板基础能力。
  message.warning(t('core.plan.universal.migrationPending'))
}

async function finishSession() {
  await saveSession()
  if (!taskId.value) editingLabel.value = ''
}

defineExpose({
  beforeLeave: () => {
    if (!taskId.value && !starting.value && !stopping.value) return true
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
watch(taskId, value => {
  if (value) return
  editingLabel.value = ''
  void refreshDays()
})
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
  void disposeSession()
})
</script>
