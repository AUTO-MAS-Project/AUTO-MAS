<template>
  <a-table
    class="oknte-plan-table"
    size="small"
    table-layout="fixed"
    row-key="day"
    :columns="columns"
    :data-source="days.map(day => ({ day }))"
    :pagination="false"
    :scroll="{ x: 848 }"
    bordered
  >
    <template v-if="catalogError" #title>
      <a-alert type="error" :message="catalogError">
        <template #action
          ><a-button @click="loadCatalog">{{ t('core.apiErrors.retry') }}</a-button></template
        >
      </a-alert>
    </template>
    <template #bodyCell="{ column, record }">
      <span v-if="column.key === 'day'">{{ label(record.day) }}</span>
      <a-button
        v-else-if="column.key === 'detail'"
        type="link"
        :disabled="isSaving"
        @click="detail(record.day)"
        >{{ t('core.plan.oknte.detail') }}</a-button
      >
      <span v-else-if="disabled(record.day, column.key)" class="not-applicable">—</span>
      <a-input-number
        v-else-if="column.key === '目标消耗体力' || column.key === '材料序号'"
        :value="value(record.day, column.key)"
        class="plan-field"
        :bordered="false"
        :aria-label="`${label(record.day)} ${column.title}`"
        :disabled="disabled(record.day, column.key)"
        :min="definition(record.day, column.key)?.min ?? 0"
        :max="definition(record.day, column.key)?.max ?? undefined"
        :placeholder="t('core.plan.oknte.inheritShort')"
        @change="save(record.day, column.key, $event)"
      />
      <a-select
        v-else
        :value="value(record.day, column.key)"
        :disabled="disabled(record.day, column.key)"
        :placeholder="t('core.plan.oknte.inheritShort')"
        :options="options(record.day, column.key)"
        class="plan-field"
        :bordered="false"
        :aria-label="`${label(record.day)} ${column.title}`"
        @change="save(record.day, column.key, $event)"
      />
    </template>
  </a-table>
</template>
<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useI18n } from 'vue-i18n'
import { OknteService, type OkNtePlanConfig } from '@/api'
import type { OverrideField } from '../oknteOverrideTypes'
import { navigateTo } from '@/router'
import { planDayKeys, planDayLabel, type PlanMode } from '@/utils/planDays'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'
const props = defineProps<{
  tableData: OkNtePlanConfig
  currentMode: PlanMode
  planId: string
  handlePlanChange: PlanChangeHandler
}>()
const { t } = useI18n()
const { enqueue, isSaving } = useSaveQueue()
const catalog = ref<{ filename: string; fields: OverrideField[] }[]>([])
const catalogError = ref('')
let catalogRequest = 0
async function loadCatalog() {
  const request = ++catalogRequest
  catalog.value = []
  catalogError.value = ''
  try {
    const response = await OknteService.getOkntePlanConfigsApiScriptsOkntePlanConfigsPost(
      props.planId,
      'ALL'
    )
    if (response.code !== 200) throw new Error(response.message)
    if (request === catalogRequest) catalog.value = response.data ?? []
  } catch (error) {
    if (request === catalogRequest) catalogError.value = String(error)
  }
}
watch(() => props.planId, loadCatalog, { immediate: true })
const drafts = shallowRef<Record<string, Record<string, Record<string, any>>>>({})
watch(
  () => props.planId,
  () => {
    drafts.value = {}
  }
)
defineExpose({ beforeLeave: () => !isSaving.value })
const days = computed(() =>
  props.currentMode === 'ALL'
    ? ['ALL']
    : planDayKeys(props.currentMode, props.tableData.Info?.RotateDays)
)
const columns = computed(() => [
  {
    title: t('core.plan.oknte.date'),
    key: 'day',
    dataIndex: 'day',
    width: 64,
    align: 'center' as const,
  },
  ...[
    { key: '体力任务', width: 112 },
    { key: '目标消耗体力', width: 108 },
    { key: '任务类型', width: 144 },
    { key: '具体奖励目标', width: 120 },
    { key: '材料序号', width: 88 },
    { key: '追猎目标', width: 112 },
  ].map(column => ({ ...column, title: column.key, align: 'center' as const })),
  { title: t('core.plan.oknte.detail'), key: 'detail', width: 100, align: 'center' as const },
])
function label(day: string) {
  const x = planDayLabel(day)
  return t(x.key, x.params)
}
function configs(day: string): Record<string, Record<string, any>> {
  if (drafts.value[day]) return drafts.value[day]
  const group = props.tableData[day as keyof OkNtePlanConfig]
  return group && 'Key' in group ? (group.Key?.Configs ?? {}) : {}
}
function activity(day: string) {
  const items = configs(day)['DailyRoutineTask.json']?.['Routine Items'] ?? []
  return items.find(
    (item: { id: string; enabled: boolean }) =>
      item.enabled && ['daily_anomaly', 'daily_anomaly_hunter'].includes(item.id)
  )?.id as string | undefined
}
function value(day: string, field: string) {
  const task = activity(day)
  const cfg = task ? (configs(day)['DailyRoutineTaskConfigs.json']?.[task] ?? {}) : {}
  if (field === '体力任务') {
    const items = configs(day)['DailyRoutineTask.json']?.['Routine Items'] ?? []
    if (task) return task
    const overrides = items.filter((item: { id: string }) =>
      ['daily_anomaly', 'daily_anomaly_hunter'].includes(item.id)
    )
    return overrides.length === 2 ? '__off' : overrides.length ? '__custom' : undefined
  }
  if (field === '材料序号')
    return cfg[
      cfg['任务类型'] === '异能升级材料'
        ? '异能材料序号'
        : cfg['任务类型'] === '空幕'
          ? '空幕序号'
          : '弧盘材料序号'
    ]
  return cfg[field]
}
function definition(day: string, field: string) {
  const task = activity(day)
  const kind = task ? configs(day)['DailyRoutineTaskConfigs.json']?.[task]?.['任务类型'] : undefined
  const name =
    field === '材料序号'
      ? kind === '异能升级材料'
        ? '异能材料序号'
        : kind === '空幕'
          ? '空幕序号'
          : '弧盘材料序号'
      : field
  return catalog.value
    .find(file => file.filename === 'DailyRoutineTaskConfigs.json')
    ?.fields.find(field => field.name === task)
    ?.children?.find(field => field.name === name)
}
function options(day: string, field: string) {
  if (field === '体力任务')
    return [
      ...(
        catalog.value
          .find(file => file.filename === 'DailyRoutineTask.json')
          ?.fields.find(field => field.type === 'routine_items')?.itemDefinitions ?? []
      )
        .filter(item => ['daily_anomaly', 'daily_anomaly_hunter'].includes(item.id))
        .map(item => ({ value: item.id, label: item.label })),
      { value: '__off', label: t('core.plan.oknte.off') },
      { value: '__custom', label: t('core.plan.oknte.detail'), disabled: true },
    ]
  return (definition(day, field)?.options ?? []).map(value => ({ value, label: value }))
}
function disabled(day: string, field: string) {
  if (!catalog.value.length) return true
  if (field === '体力任务') return false
  if (!activity(day)) return true
  if (field === '目标消耗体力') return false
  if (field === '追猎目标') return activity(day) !== 'daily_anomaly_hunter'
  if (activity(day) === 'daily_anomaly_hunter') return true
  const kind = configs(day)['DailyRoutineTaskConfigs.json']?.daily_anomaly?.['任务类型']
  return field === '具体奖励目标'
    ? kind !== '经验与甲硬币'
    : field === '材料序号' && kind === '经验与甲硬币'
}
async function save(day: string, field: string, input: unknown) {
  if (input === null || input === undefined) return
  const next = JSON.parse(JSON.stringify(configs(day)))
  if (field === '体力任务') {
    const items = next['DailyRoutineTask.json']?.['Routine Items'] ?? []
    for (const id of ['daily_anomaly', 'daily_anomaly_hunter']) {
      const found = items.find((x: { id: string }) => x.id === id)
      const enabled = id === input
      if (found) found.enabled = enabled
      else items.push({ id, enabled })
    }
    next['DailyRoutineTask.json'] = { ...next['DailyRoutineTask.json'], 'Routine Items': items }
  } else {
    const tasks = (next['DailyRoutineTaskConfigs.json'] ??= {})
    const active = activity(day)
    if (!active) return
    const task = (tasks[active] ??= {})
    if (field === '材料序号') {
      const key = definition(day, field)?.name
      if (!key) return
      task[key] = Number(input)
    } else task[field] = input
  }
  drafts.value = { ...drafts.value, [day]: next }
  try {
    await enqueue(() => props.handlePlanChange(`${day}.Key.Configs`, next))
  } finally {
    if (drafts.value[day] === next) {
      const remaining = { ...drafts.value }
      delete remaining[day]
      drafts.value = remaining
    }
  }
}
function detail(day: string) {
  navigateTo(`/plans/${props.planId}/oknte/${day}`)
}
</script>

<style scoped>
.plan-field {
  width: 100%;
  min-width: 0;
}
.not-applicable {
  color: var(--ant-color-text-tertiary);
}
/* 网格承担字段边界，键盘聚焦仍提供清晰轮廓。 */
.plan-field:focus-within {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
  border-radius: 4px;
}
.plan-field :deep(.ant-select-selection-item),
.plan-field :deep(.ant-input-number-input) {
  text-align: center;
}
/* 左右对称留出箭头位置，选中值按整列中心对齐。 */
.oknte-plan-table :deep(.ant-select-single .ant-select-selector) {
  padding-inline: 24px;
}
.oknte-plan-table :deep(.ant-select-single .ant-select-selector .ant-select-selection-item) {
  padding-inline: 0;
}
.oknte-plan-table :deep(.ant-table-cell) {
  vertical-align: middle;
}
</style>
