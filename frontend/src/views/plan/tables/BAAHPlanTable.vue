<template>
  <div class="config-table-wrapper">
    <!-- 行对象的字段是 rowKey，Ant 默认取 key，不指定会退回索引做主键 -->
    <a-table
      :key="`baah-config-table-${currentMode}-${columnKeys.length}`"
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
          <!-- 三态那一行有说明，参数行没有：有说明才套浮层 -->
          <a-tooltip v-if="record.fieldHint" :title="record.fieldHint">
            {{ record.fieldName }}
          </a-tooltip>
          <span v-else>{{ record.fieldName }}</span>
        </template>

        <!-- 每类头上先一行状态：开＝按这里的参数打，关＝今天不打，交给 BAAH＝沿用上游配置 -->
        <template v-else-if="record.rowKind === 'state'">
          <a-select
            class="config-select"
            size="small"
            :bordered="false"
            :value="record[column.key]"
            :options="fieldStateOptions"
            :disabled="isColumnDisabled(column.key)"
            :aria-label="cellLabel(record.fieldName, column.key)"
            @update:value="handleFieldStateChange(column.key, record.field, $event)"
          />
        </template>

        <!-- 多类混打：每类关卡的每一位各占一行，一格一个下拉 -->
        <template v-else>
          <a-select
            class="config-select"
            size="small"
            :bordered="false"
            placeholder="-"
            :value="record[column.key]"
            :options="partOptions(record.hintKey, record.min)"
            :disabled="isColumnDisabled(column.key)"
            :aria-label="cellLabel(record.fieldName, column.key)"
            @update:value="handlePartChange(column.key, record.field, record.index, $event)"
          />
        </template>
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
  BAAH_PLAN_KEY_FIELDS,
  applyFieldState,
  applyMixedPart,
  partOptionMax,
  readDayFields,
  readFieldState,
  readFieldValues,
  type BAAHDayFields,
  type BAAHFieldState,
  type BAAHKeyFieldName,
} from '@/utils/baahPlanKey'
import {
  planColumnKeys,
  planColumnPath,
  planDayLabel,
  readPlanColumn,
  type PlanMode,
} from '@/utils/planDays'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: PlanMode
  /** BAAH 的排法挤不进「简化视图」，转置只会更难读，配置视图与简化视图共用这一张表 */
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: PlanChangeHandler
}

const props = defineProps<Props>()

/** a-table 的行主键：行对象的字段是 rowKey，Ant 默认取 key，不指定会退回索引 */
const rowKeyOf = (record: { rowKey: string }) => record.rowKey

/** 列键：ALL 加当天的天键；周计划是星期名，多天轮换是 "1"~"N" */
const columnKeys = computed(() =>
  planColumnKeys(props.currentMode, props.tableData?.Info?.RotateDays)
)

const columnTitle = (key: string) =>
  key === 'ALL' ? t('plan.week.ALL') : t(planDayLabel(key).key, planDayLabel(key).params)

const localTableData = ref<Record<string, BAAHDayFields>>({})

const syncLocalTableData = (tableData: Record<string, any> | null) => {
  localTableData.value = Object.fromEntries(
    columnKeys.value.map(key => [key, readDayFields(readPlanColumn(tableData, key))])
  ) as Record<string, BAAHDayFields>
}

// 列键同时取决于模式与轮换天数，任何一个变了都要重读一遍
watch(
  () => [props.tableData, props.currentMode, props.tableData?.Info?.RotateDays] as const,
  () => syncLocalTableData(props.tableData),
  { immediate: true }
)

const configColumns = computed(() => {
  // 一格一个控件，列宽与 MAA 的配置视图一致
  // 行标题是「悬赏通缉 · 地区」这样的两段式，首列得留宽一点
  const titleWidth = 160

  return [
    {
      title: t('plan.table.field'),
      dataIndex: 'fieldName',
      key: 'fieldName',
      width: titleWidth,
      fixed: 'left',
      align: 'center',
    },
    ...columnKeys.value.map(key => ({
      title: columnTitle(key),
      dataIndex: key,
      key,
      width: 120,
      align: 'center',
    })),
  ]
})

/** 格的读屏标签：行标题 + 天，八个一模一样的控件否则念出来分不清 */
const cellLabel = (name: string, key: string) => `${name} ${columnTitle(key)}`

const isColumnDisabled = (key: string) => {
  if (props.currentMode === 'ALL') return key !== 'ALL'
  return key === 'ALL'
}

const rangeOptions = (max: number) =>
  Array.from({ length: max }, (_, index) => ({ value: index + 1, label: String(index + 1) }))

/**
 * 一位的下拉：允许负数时先给一项文本（关卡位是「倒数第一个」，次数位是「最大次数」），
 * 再按这一位的上限列出具体数字。
 */
const partOptions = (hintKey: string, min: number) => [
  ...(min === -1
    ? [
        {
          value: -1,
          label: t(
            hintKey === 'plan.baah.partTimes' ? 'plan.baah.timesMax' : 'plan.baah.stageHighest'
          ),
        },
      ]
    : []),
  ...rangeOptions(partOptionMax(hintKey)),
]

/** 一类关卡在某一天的三态：开 / 关 / 交给 BAAH */
const fieldStateOptions = computed(() => [
  { value: 'on', label: t('plan.baah.stateOn') },
  { value: 'off', label: t('plan.baah.stateOff') },
  { value: 'auto', label: t('plan.baah.stateAuto') },
])

const configRows = computed(() => {
  // 每类先一行状态，再按位各占一行，行标题写成「类名 · 位名」
  return BAAH_PLAN_KEY_FIELDS.flatMap(field => [
    {
      rowKey: `${field.field}.state`,
      rowKind: 'state',
      field: field.field,
      fieldName: `${t(field.labelKey)} · ${t('plan.baah.rowState')}`,
      fieldHint: t('plan.baah.rowStateHint'),
      ...Object.fromEntries(
        columnKeys.value.map(key => [key, readFieldState(localTableData.value[key], field.field)])
      ),
    },
    ...field.parts.map((part, index) => ({
      rowKey: `${field.field}.${index}`,
      rowKind: 'part',
      field: field.field,
      index,
      hintKey: part.hintKey,
      min: part.min,
      fieldName: `${t(field.labelKey)} · ${t(part.hintKey)}`,
      ...Object.fromEntries(
        columnKeys.value.map(key => [
          key,
          // 这一类今天没在打时参数行留空，免得填了却不生效
          readFieldState(localTableData.value[key], field.field) === 'on'
            ? readFieldValues(localTableData.value[key], field.field)[index]
            : undefined,
        ])
      ),
    })),
  ])
})

/**
 * 整格提交：先落到本地让界面即时反馈，保存失败再退回原来的那一格。
 *
 * 后端按「天 → Key」两级写入，一格只能整份提交：只发一个字段会被当成整份 Key，
 * 其余五类关卡会跟着变成「交给 BAAH」，静默丢掉原本的取值。
 */
const submitDayKey = async (
  key: string,
  nextDayKey: BAAHDayFields,
  previousFields: BAAHDayFields | undefined
) => {
  localTableData.value = {
    ...localTableData.value,
    [key]: nextDayKey,
  }

  const saved = await props.handlePlanChange(planColumnPath(key, 'Key'), nextDayKey, false)
  if (!saved) {
    localTableData.value = {
      ...localTableData.value,
      [key]: previousFields ?? {},
    }
  }
}

const handlePartChange = async (
  key: string,
  field: BAAHKeyFieldName,
  index: number,
  value: number | string | null
) => {
  const previousFields = localTableData.value[key]
  const write = applyMixedPart(previousFields, field, index, value)

  if (write.corrected) message.warning(t('plan.baah.partLevelZeroFixed'))

  await submitDayKey(key, write.fields, previousFields)
}

/** 三态切换：开＝按这里的参数打，关＝今天不打，交给 BAAH＝今天不干预这一类 */
const handleFieldStateChange = async (
  key: string,
  field: BAAHKeyFieldName,
  state: BAAHFieldState
) => {
  const previousFields = localTableData.value[key]

  // 只动这一类，别的类别原样带过去：界面没展示的类别不该被补成默认值
  await submitDayKey(key, applyFieldState(previousFields, field, state), previousFields)
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
</style>
