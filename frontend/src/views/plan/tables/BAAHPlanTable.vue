<template>
  <div class="config-table-wrapper">
    <!-- 行对象的字段是 rowKey，Ant 默认取 key，不指定会退回索引做主键 -->
    <a-table
      :key="`baah-config-table-${currentMode}-${baahLayout}`"
      :columns="configColumns"
      :data-source="configRows"
      :row-key="rowKeyOf"
      :pagination="false"
      class="config-table"
      size="middle"
      :bordered="true"
      :scroll="{ x: 'max-content' }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'fieldName'">
          <a-tooltip :title="record.fieldHint">{{ record.fieldName }}</a-tooltip>
        </template>

        <!-- 每天一类：选今天打哪一类，选中后下面两行填这一类的关卡与次数 -->
        <template v-else-if="record.rowKind === 'kind'">
          <a-select
            class="config-select"
            size="small"
            :bordered="false"
            :value="singleCells[asTimeKey(column.key)].kind"
            :options="kindOptions"
            :disabled="isColumnDisabled(asTimeKey(column.key))"
            :aria-label="cellLabel(record.fieldName, column.key)"
            @update:value="handleSingleKindChange(asTimeKey(column.key), $event)"
          />
        </template>

        <!-- 关卡名称与战斗次数都是下拉：-1 那项读作「最高关」或「最大」，其余是具体数字 -->
        <template v-else-if="record.rowKind === 'stage' || record.rowKind === 'times'">
          <a-select
            class="config-select"
            size="small"
            :bordered="false"
            placeholder="-"
            :value="singleCellValue(asTimeKey(column.key), record.rowKind)"
            :options="rowOptions(asTimeKey(column.key), record.rowKind)"
            :disabled="singleCellNumberDisabled(asTimeKey(column.key))"
            :aria-label="cellLabel(record.fieldName, column.key)"
            @update:value="handleSingleNumberChange(asTimeKey(column.key), record.rowKind, $event)"
          />
        </template>

        <!-- 多类混打：一行一类，一格放这一类的 2~3 个数字，顺序与后端存的一致 -->
        <div v-else class="part-cell">
          <a-input-number
            v-for="part in record.parts"
            :key="part.index"
            class="config-input-number part-number"
            size="small"
            :bordered="false"
            :controls="false"
            :precision="0"
            :value="record[column.key][part.index]"
            :min="part.min"
            :disabled="isColumnDisabled(asTimeKey(column.key))"
            :aria-label="cellLabel(`${record.fieldName} ${part.hint}`, column.key)"
            @update:value="
              handlePartChange(asTimeKey(column.key), record.field, part.index, $event)
            "
          />
        </div>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'
import {
  allowsHighestStage,
  BAAH_KEY_FIELD_BY_NAME,
  BAAH_PLAN_KEY_FIELDS,
  BAAH_PLAN_TIME_KEYS,
  BAAH_STAGE_OPTION_MAX,
  BAAH_TIMES_OPTION_MAX,
  applyMixedPart,
  applySingleNumber,
  buildSingleDayKey,
  fillDayFields,
  readDayFields,
  readSingleCell,
  type BAAHDayFields,
  type BAAHKeyFieldName,
  type BAAHSingleCell,
  type BAAHSingleRowKind,
  type PlanTimeKey,
} from '@/utils/baahPlanKey'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  /**
   * BAAH 两种排法都挤不进「简化视图」：多类混打一格 2~3 个数字，每天一类一格三行，
   * 转置只会更难读，所以配置视图与简化视图共用这一张表。
   */
  viewMode: 'config' | 'simple'
  /**
   * 关卡安排：每天一类（默认，三行各管一件事）或多类混打（六类都填）。
   * 多类混打一行一类、一格 2~3 个数字；每天一类三行各管一件事，一格一个控件。
   * 两种排法只在「一格怎么渲染、整份 key 怎么组」上分叉，表格方向都是列 = 全局 / 周一~周日。
   */
  baahLayout: 'mixed' | 'single'
  planId?: string
  handlePlanChange: PlanChangeHandler
}

const props = defineProps<Props>()

/** a-table 的行主键：行对象的字段是 rowKey，Ant 默认取 key，不指定会退回索引 */
const rowKeyOf = (record: { rowKey: string }) => record.rowKey

const localTableData = ref<Partial<Record<PlanTimeKey, BAAHDayFields>>>({})

const syncLocalTableData = (tableData: Record<string, any> | null) => {
  localTableData.value = Object.fromEntries(
    BAAH_PLAN_TIME_KEYS.map(timeKey => [timeKey, readDayFields(tableData?.[timeKey])])
  ) as Partial<Record<PlanTimeKey, BAAHDayFields>>
}

watch(() => props.tableData, syncLocalTableData, { immediate: true })

const configColumns = computed(() => {
  // 每天一类一格只有一个控件，列宽与 MAA 的配置视图一致；多类混打一格塞 2~3 个数字
  const dayWidth = props.baahLayout === 'single' ? 120 : 150

  return [
    {
      title: t('plan.table.field'),
      dataIndex: 'fieldName',
      key: 'fieldName',
      width: 120,
      fixed: 'left',
      align: 'center',
    },
    ...BAAH_PLAN_TIME_KEYS.map(timeKey => ({
      title: t(`plan.week.${timeKey}`),
      dataIndex: timeKey,
      key: timeKey,
      width: dayWidth,
      align: 'center',
    })),
  ]
})

const asTimeKey = (value: string): PlanTimeKey => value as PlanTimeKey

/** 格的读屏标签：行标题 + 星期，八个一模一样的控件否则念出来分不清 */
const cellLabel = (name: string, timeKey: string) => `${name} ${t(`plan.week.${timeKey}`)}`

const isColumnDisabled = (timeKey: PlanTimeKey) => {
  if (props.currentMode === 'ALL') return timeKey !== 'ALL'
  return timeKey === 'ALL'
}

const singleCells = computed(
  () =>
    Object.fromEntries(
      BAAH_PLAN_TIME_KEYS.map(timeKey => [timeKey, readSingleCell(localTableData.value[timeKey])])
    ) as Record<PlanTimeKey, BAAHSingleCell>
)

/** 没选今天打哪一类时这一格没有值，下拉显示占位符 */
const singleCellValue = (timeKey: PlanTimeKey, rowKind: BAAHSingleRowKind) =>
  singleCells.value[timeKey].kind ? singleCells.value[timeKey][rowKind] : undefined

const rangeOptions = (max: number) =>
  Array.from({ length: max }, (_, index) => ({ value: index + 1, label: String(index + 1) }))

/** 关卡名称：-1 读作「最高关」，困难图与普通图没有这一项 */
const stageOptions = (timeKey: PlanTimeKey) => {
  const { kind } = singleCells.value[timeKey]

  return [
    ...(allowsHighestStage(kind) ? [{ value: -1, label: t('plan.baah.stageHighest') }] : []),
    ...rangeOptions(BAAH_STAGE_OPTION_MAX),
  ]
}

/** 战斗次数：-1 读作「最大」 */
const timesOptions = computed(() => [
  { value: -1, label: t('plan.baah.timesMax') },
  ...rangeOptions(BAAH_TIMES_OPTION_MAX),
])

const rowOptions = (timeKey: PlanTimeKey, rowKind: BAAHSingleRowKind) =>
  rowKind === 'stage' ? stageOptions(timeKey) : timesOptions.value

/** 还没选今天打哪一类时，关卡与次数无从填起，下拉跟着禁用 */
const singleCellNumberDisabled = (timeKey: PlanTimeKey) =>
  isColumnDisabled(timeKey) || !singleCells.value[timeKey].kind

const kindOptions = computed(() => [
  { value: '', label: t('plan.baahLayout.emptyOption') },
  ...BAAH_PLAN_KEY_FIELDS.map(field => ({
    value: field.field as string,
    label: t(field.labelKey),
  })),
])

const configRows = computed(() => {
  // 每天一类：三行各管一件事，八列各一组控件
  if (props.baahLayout === 'single') {
    return [
      {
        rowKey: 'kind',
        rowKind: 'kind',
        fieldName: t('plan.baah.rowKind'),
        fieldHint: t('plan.baah.rowKindHint'),
      },
      {
        rowKey: 'stage',
        rowKind: 'stage',
        fieldName: t('plan.baah.rowStage'),
        fieldHint: t('plan.baah.rowStageHint'),
      },
      {
        rowKey: 'times',
        rowKind: 'times',
        fieldName: t('plan.baah.rowTimes'),
        fieldHint: t('plan.baah.rowTimesHint'),
      },
    ]
  }

  return BAAH_PLAN_KEY_FIELDS.map(field => ({
    rowKey: field.field,
    rowKind: 'parts',
    field: field.field,
    fieldName: t(field.labelKey),
    fieldHint: t(field.hintKey),
    parts: field.parts.map((part, index) => ({
      index,
      min: part.min,
      hint: t(part.hintKey),
    })),
    ...Object.fromEntries(
      BAAH_PLAN_TIME_KEYS.map(timeKey => [
        timeKey,
        fillDayFields(localTableData.value[timeKey] ?? {})[field.field],
      ])
    ),
  }))
})

/**
 * 整格提交：先落到本地让界面即时反馈，保存失败再退回原来的那一格。
 *
 * 后端按「日期 → Key」两级写入，一格只能整份提交：只发一个字段会被当成整份 Key，
 * 其余五类关卡会被 validator 补成默认值，静默丢掉取值。
 */
const submitDayKey = async (
  timeKey: PlanTimeKey,
  nextDayKey: BAAHDayFields,
  previousFields: BAAHDayFields | undefined
) => {
  localTableData.value = {
    ...localTableData.value,
    [timeKey]: nextDayKey,
  }

  const saved = await props.handlePlanChange(`${timeKey}.Key`, nextDayKey, false)
  if (!saved) {
    localTableData.value = {
      ...localTableData.value,
      [timeKey]: previousFields ?? {},
    }
  }
}

const handlePartChange = async (
  timeKey: PlanTimeKey,
  field: BAAHKeyFieldName,
  index: number,
  value: number | string | null
) => {
  const previousFields = localTableData.value[timeKey]
  const write = applyMixedPart(previousFields, field, index, value)

  if (write.corrected) message.warning(t('plan.baah.partLevelZeroFixed'))

  await submitDayKey(timeKey, write.fields, previousFields)
}

const handleSingleKindChange = async (timeKey: PlanTimeKey, value: unknown) => {
  const previousFields = localTableData.value[timeKey]
  const choice = (typeof value === 'string' ? value : '') as BAAHKeyFieldName | ''
  // 换类时带上这一类的默认参数，切过去就有值可改，不会先落一份空
  const items = choice ? [...BAAH_KEY_FIELD_BY_NAME[choice].defaultValue] : []

  await submitDayKey(timeKey, buildSingleDayKey(choice, items), previousFields)
}

const handleSingleNumberChange = async (
  timeKey: PlanTimeKey,
  rowKind: BAAHSingleRowKind,
  value: number | string | null
) => {
  const previousFields = localTableData.value[timeKey]
  const write = applySingleNumber(previousFields, rowKind, value)
  if (!write) return

  if (write.corrected) message.warning(t('plan.baah.partLevelZeroFixed'))

  await submitDayKey(timeKey, write.fields, previousFields)
}
</script>

<style scoped>
.config-table-wrapper {
  overflow: hidden;
}

.config-table :deep(.ant-table-cell) {
  vertical-align: middle;
}

:deep(.config-table .ant-table-tbody > tr > td) {
  text-align: center;
}

/* 控件一律去掉边框与底色，一格里只剩数值本身，与 MAA 的配置视图一致 */
.config-select {
  width: 100%;
  min-width: 100px;
}

.config-select :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.config-select :deep(.ant-select-selection-item),
.config-select :deep(.ant-select-selection-placeholder) {
  width: 100%;
  text-align: center;
  margin-inline-start: 0 !important;
}

.config-input-number {
  width: 100%;
  min-width: 100px;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}

.config-input-number input {
  text-align: center;
}

.config-input-number :deep(.ant-input-number-input) {
  text-align: center;
}

.config-input-number :deep(.ant-input-number-handler-wrap) {
  display: none;
}

/* 多类混打一格并排 2~3 个数字，按格内可用宽度平分 */
.part-cell {
  display: flex;
  justify-content: center;
  gap: 4px;
}

.part-cell .config-input-number {
  width: 42px;
  min-width: 0;
}
</style>
