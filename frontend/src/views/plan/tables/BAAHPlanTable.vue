<template>
  <div class="config-table-wrapper">
    <!-- 行对象的字段是 rowKey，Ant 默认取 key，不指定会退回索引做主键 -->
    <a-table
      :key="`baah-config-table-${currentMode}`"
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
          {{ record.fieldName }}
        </template>

        <!-- 每类头上先一行开关，关了就是这一天不跑这一类 -->
        <template v-else-if="record.rowKind === 'enabled'">
          <a-switch
            size="small"
            :checked="record[column.key]"
            :disabled="isColumnDisabled(asTimeKey(column.key))"
            :aria-label="cellLabel(record.fieldName, column.key)"
            @change="handlePartEnabledChange(asTimeKey(column.key), record.field, $event)"
          />
        </template>

        <!-- 多类混打：每类关卡的每一位各占一行，一格一个下拉，与每天一类同一套控件 -->
        <template v-else>
          <a-select
            class="config-select"
            size="small"
            :bordered="false"
            placeholder="-"
            :value="record[column.key]"
            :options="partOptions(record.hintKey, record.min)"
            :disabled="isColumnDisabled(asTimeKey(column.key))"
            :aria-label="cellLabel(record.fieldName, column.key)"
            @update:value="
              handlePartChange(asTimeKey(column.key), record.field, record.index, $event)
            "
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
  BAAH_PLAN_TIME_KEYS,
  applyMixedPart,
  isFieldEnabled,
  partOptionMax,
  readDayFields,
  readFieldValues,
  type BAAHDayFields,
  type BAAHKeyFieldName,
  type PlanTimeKey,
} from '@/utils/baahPlanKey'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  /** BAAH 的排法挤不进「简化视图」，转置只会更难读，配置视图与简化视图共用这一张表 */
  viewMode: 'config' | 'simple'
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
    ...BAAH_PLAN_TIME_KEYS.map(timeKey => ({
      title: t(`plan.week.${timeKey}`),
      dataIndex: timeKey,
      key: timeKey,
      width: 120,
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

const configRows = computed(() => {
  // 每类先一行「启用」开关，再按位各占一行，行标题写成「类名 · 位名」
  return BAAH_PLAN_KEY_FIELDS.flatMap(field => [
    {
      rowKey: `${field.field}.enabled`,
      rowKind: 'enabled',
      field: field.field,
      fieldName: `${t(field.labelKey)} · ${t('plan.baah.partEnabled')}`,
      ...Object.fromEntries(
        BAAH_PLAN_TIME_KEYS.map(timeKey => [
          timeKey,
          isFieldEnabled(localTableData.value[timeKey], field.field),
        ])
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
        BAAH_PLAN_TIME_KEYS.map(timeKey => [
          timeKey,
          // 这一类今天没启用时参数行留空，免得填了却不生效
          isFieldEnabled(localTableData.value[timeKey], field.field)
            ? readFieldValues(localTableData.value[timeKey], field.field)[index]
            : undefined,
        ])
      ),
    })),
  ])
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

/**
 * 多类混打：开关关掉就把这一类写成空数组（今天不打），打开则补回参数。
 * 打开时优先沿用原来填过的值，不会把用户改过的关卡重置成默认值。
 */
const handlePartEnabledChange = async (
  timeKey: PlanTimeKey,
  field: BAAHKeyFieldName,
  checked: unknown
) => {
  const previousFields = localTableData.value[timeKey]
  const items = checked ? readFieldValues(previousFields, field) : []

  // 只动这一类，别的类别原样带过去：界面没展示的类别不该被补成默认值
  await submitDayKey(timeKey, { ...(previousFields ?? {}), [field]: items }, previousFields)
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
