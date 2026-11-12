<template>
  <a-alert v-if="error" type="error" :message="error" show-icon
    ><template #action
      ><a-button :loading="isSaving" @click="retry">{{
        t('core.apiErrors.retry')
      }}</a-button></template
    ></a-alert
  >
  <a-table
    class="okww-plan-table"
    size="small"
    table-layout="fixed"
    row-key="day"
    :columns="columns"
    :data-source="days.map(day => ({ day }))"
    :pagination="false"
    :scroll="{ x: 844 }"
    bordered
  >
    <template #bodyCell="{ column, record }">
      <span v-if="column.key === 'day'">{{ label(record.day) }}</span>
      <span v-else-if="notApplicable(record.day, column.key)" class="not-applicable">—</span>
      <a-input-number
        v-else-if="column.key === 'number'"
        :value="number(record.day)"
        class="plan-field"
        :bordered="false"
        :min="1"
        :max="99"
        :disabled="isSaving"
        :placeholder="t('core.plan.oknte.inheritShort')"
        :aria-label="`${label(record.day)} 序号`"
        @change="(value: any) => save(record.day, numberField(record.day), value)"
      />
      <a-select
        v-else
        :value="value(record.day, column.key)"
        :mode="column.key === 'AdditionalTasks' ? 'multiple' : undefined"
        :options="options(column.key)"
        :disabled="isSaving"
        :bordered="false"
        allow-clear
        :placeholder="t('core.plan.oknte.inheritShort')"
        class="plan-field"
        :aria-label="`${label(record.day)} ${column.title}`"
        @change="(value: any) => save(record.day, column.key, value)"
      />
    </template>
  </a-table>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { OkwwPlanConfig } from '@/api'
import { planDayKeys, planDayLabel, planColumnGroup, type PlanMode } from '@/utils/planDays'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { farmOptions, materialOptions, additionalTaskOptions } from '@/utils/okwwTaskOptions'
defineOptions({ inheritAttrs: false })
const props = defineProps<{
  tableData: OkwwPlanConfig
  currentMode: PlanMode
  planId: string
  handlePlanChange: PlanChangeHandler
}>()
const { t } = useI18n()
const { enqueue, isSaving } = useSaveQueue()
const drafts = ref<Record<string, Record<string, any>>>({})
const error = ref('')
let retry = () => {}

watch(
  () => props.planId,
  () => {
    drafts.value = {}
    error.value = ''
  }
)
const days = computed(() =>
  props.currentMode === 'ALL'
    ? ['ALL']
    : planDayKeys(props.currentMode, props.tableData.Info?.RotateDays)
)
const columns = computed(() =>
  [
    { title: t('core.plan.oknte.date'), key: 'day', width: 64 },
    { title: t('core.plan.okww.farm'), key: 'WhichToFarm', width: 144 },
    { title: t('core.plan.okww.number'), key: 'number', width: 112 },
    { title: t('core.plan.okww.material'), key: 'MaterialSelection', width: 144 },
    {
      title: t('core.plan.okww.nightmare'),
      key: 'FarmNightmareNestForDailyEcho',
      width: 160,
    },
    { title: t('core.plan.okww.additional'), key: 'AdditionalTasks', width: 220 },
  ].map(column => ({ ...column, align: 'center' as const }))
)
function label(day: string) {
  if (day === 'ALL') return t('core.plan.modeAll')
  const x = planDayLabel(day)
  return t(x.key, x.params)
}
function key(day: string): Record<string, any> {
  if (drafts.value[day]) return drafts.value[day]
  const group = props.tableData[planColumnGroup(day) as keyof OkwwPlanConfig]
  return group && 'Key' in group ? (group.Key ?? {}) : {}
}
function value(day: string, field: string) {
  const result = key(day)[field]
  return typeof result === 'boolean' ? String(result) : (result ?? undefined)
}
function numberField(day: string) {
  return value(day, 'WhichToFarm') === 'Tacet Suppression'
    ? 'WhichTacetSuppressionToFarm'
    : value(day, 'WhichToFarm') === 'Forgery Challenge'
      ? 'WhichForgeryChallengeToFarm'
      : ''
}
function notApplicable(day: string, field: string) {
  return field === 'number'
    ? !numberField(day)
    : field === 'MaterialSelection' && value(day, 'WhichToFarm') !== 'Simulation Challenge'
}
function number(day: string) {
  return key(day)[numberField(day)] ?? undefined
}
function options(field: string) {
  return field === 'WhichToFarm'
    ? farmOptions
    : field === 'MaterialSelection'
      ? materialOptions
      : field === 'AdditionalTasks'
        ? additionalTaskOptions
        : [
            { label: t('core.plan.oknte.on'), value: 'true' },
            { label: t('core.plan.oknte.off'), value: 'false' },
          ]
}
async function save(day: string, field: string, input: unknown) {
  if (!field) return
  const next = {
    ...key(day),
    [field]:
      field === 'FarmNightmareNestForDailyEcho' && input != null
        ? input === 'true'
        : (input ?? null),
  }
  drafts.value[day] = next
  const saved = await enqueue(() => props.handlePlanChange(`${planColumnGroup(day)}.Key`, next))
  error.value = saved ? '' : t('core.misc.couldNotUpdatePlan')
  retry = () => {
    void save(day, field, input)
  }
}

defineExpose({ beforeLeave: () => !isSaving.value && !error.value })
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
.okww-plan-table :deep(.ant-select-single .ant-select-selector) {
  padding-inline: 24px;
}
.okww-plan-table :deep(.ant-select-single .ant-select-selector .ant-select-selection-item) {
  padding-inline: 0;
}
.okww-plan-table :deep(.ant-table-cell) {
  vertical-align: middle;
}
</style>
