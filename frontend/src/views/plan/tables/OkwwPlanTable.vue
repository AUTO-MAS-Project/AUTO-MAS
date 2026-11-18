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
        :disabled="isSaving || Boolean(error)"
        :placeholder="t('core.plan.oknte.inheritShort')"
        :aria-label="`${label(record.day)} ${column.title}`"
        @change="(value: any) => save(record.day, numberField(record.day), value)"
      />
      <a-popover
        v-else-if="column.key === 'AdditionalTasks'"
        trigger="click"
        placement="bottomRight"
      >
        <template #content>
          <div class="additional-task-editor">
            <a-checkbox-group
              :value="key(record.day).AdditionalTasks ?? []"
              :disabled="isSaving || Boolean(error)"
              class="additional-task-options"
              @change="(tasks: unknown) => save(record.day, 'AdditionalTasks', tasks)"
            >
              <a-checkbox
                v-for="task in additionalTaskOptions"
                :key="task.value"
                :value="task.value"
                >{{ task.label }}</a-checkbox
              >
            </a-checkbox-group>
            <div class="additional-task-footer">
              <a-button
                type="text"
                size="small"
                class="inherit-option"
                :disabled="isSaving || Boolean(error)"
                @click="save(record.day, 'AdditionalTasks', null)"
                >{{ t('core.plan.oknte.inheritShort') }}</a-button
              >
            </div>
          </div>
        </template>
        <a-button
          type="text"
          :disabled="isSaving || Boolean(error)"
          class="plan-field additional-task-trigger"
          :class="{ 'inherit-option': key(record.day).AdditionalTasks == null }"
        >
          <span class="additional-task-summary">{{ additionalTaskSummary(record.day) }}</span>
          <DownOutlined />
        </a-button>
      </a-popover>
      <a-select
        v-else
        :value="value(record.day, column.key)"
        :options="options(column.key)"
        :disabled="isSaving || Boolean(error)"
        :bordered="false"
        allow-clear
        :placeholder="t('core.plan.oknte.inheritShort')"
        class="plan-field"
        :class="{ 'plan-field--inherited': value(record.day, column.key) === '__inherit' }"
        :aria-label="`${label(record.day)} ${column.title}`"
        @change="(value: any) => save(record.day, column.key, value)"
      >
        <template #option="{ value: optionValue, label: optionLabel }">
          <span :class="{ 'inherit-option': optionValue === '__inherit' }">{{ optionLabel }}</span>
        </template>
      </a-select>
    </template>
  </a-table>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { DownOutlined } from '@ant-design/icons-vue'
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
    { title: t('core.plan.okww.farm'), key: 'WhichToFarm', width: 136 },
    { title: t('core.plan.okww.number'), key: 'number', width: 104 },
    { title: t('core.plan.okww.material'), key: 'MaterialSelection', width: 136 },
    {
      title: t('core.plan.okww.nightmare'),
      key: 'FarmNightmareNestForDailyEcho',
      width: 144,
    },
    { title: t('core.plan.okww.additional'), key: 'AdditionalTasks', width: 260 },
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
  if (field === 'FarmNightmareNestForDailyEcho') {
    return result == null ? '__inherit' : String(result)
  }
  return result ?? undefined
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
function additionalTaskSummary(day: string) {
  const tasks: string[] | null = key(day).AdditionalTasks
  if (tasks == null) return t('core.plan.oknte.inheritShort')
  if (!tasks.length) return t('core.plan.oknte.off')
  return additionalTaskOptions
    .filter(task => tasks.includes(task.value))
    .map(task => t(task.shortLabelKey))
    .join('、')
}
function options(field: string) {
  return field === 'WhichToFarm'
    ? farmOptions
    : field === 'MaterialSelection'
      ? materialOptions
      : [
          { label: t('core.plan.oknte.inheritShort'), value: '__inherit' },
          { label: t('core.plan.oknte.on'), value: 'true' },
          { label: t('core.plan.oknte.off'), value: 'false' },
        ]
}
async function save(day: string, field: string, input: unknown) {
  if (!field) return
  const next = {
    ...key(day),
    [field]:
      field === 'FarmNightmareNestForDailyEcho'
        ? input == null || input === '__inherit'
          ? null
          : input === 'true'
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
.additional-task-editor {
  width: 280px;
}
.additional-task-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.additional-task-options :deep(.ant-checkbox-wrapper) {
  margin-inline-start: 0;
}
.additional-task-footer {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--ant-color-border-secondary);
  text-align: right;
}
.additional-task-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.additional-task-trigger.inherit-option .additional-task-summary,
.additional-task-trigger.inherit-option :deep(.anticon) {
  color: var(--ant-color-text-placeholder);
}
.additional-task-summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plan-field {
  width: 100%;
  min-width: 0;
}
.plan-field--inherited :deep(.ant-select-selection-item),
.inherit-option {
  color: var(--ant-color-text-placeholder);
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
