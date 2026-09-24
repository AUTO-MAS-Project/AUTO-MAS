<template>
  <div>
    <div class="config-table-wrapper">
      <a-table
        :key="`baah-config-table-${currentMode}`"
        :columns="configColumns"
        :data-source="configRows"
        :pagination="false"
        class="config-table"
        size="middle"
        :bordered="true"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'fieldName'">
            <a-tooltip :title="record.fieldHint">
              <span class="field-label">
                {{ record.fieldName }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>

          <div v-else class="key-cell">
            <a-tooltip v-for="part in record.parts" :key="part.index" :title="part.hint">
              <a-input-number
                class="config-number"
                size="small"
                :value="record[column.key][part.index]"
                :min="part.min"
                :precision="0"
                :controls="false"
                :disabled="isColumnDisabled(asTimeKey(column.key))"
                :aria-label="`${record.fieldName} ${part.hint}`"
                @change="handlePartChange(asTimeKey(column.key), record.field, part.index, $event)"
              />
            </a-tooltip>
          </div>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  /**
   * BAAH 一格要塞 2~3 个数字，拆成「简化视图」反而更难读，
   * 所以配置视图与简化视图共用这一张表。
   */
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: PlanChangeHandler
}

const props = defineProps<Props>()

type PlanTimeKey =
  | 'ALL'
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

type BAAHKeyFieldName = 'Event' | 'Wanted' | 'Special' | 'Exchange' | 'Hard' | 'Normal'

interface BAAHKeyPart {
  /** 词表 key：这一位是什么，能不能填 -1 */
  hintKey: string
  /** 允许的最小值：-1 表示「最高关」或「最大次数」，上游用滚动选择时只能填 1 */
  min: number
}

interface BAAHKeyField {
  field: BAAHKeyFieldName
  labelKey: string
  hintKey: string
  /** 与后端 BAAH_PLAN_KEY_SHAPE 一致：缺位时补的默认值，界面不暴露的位也按它补 */
  defaultValue: number[]
  /** 后端允许的最长位数；超出的位照旧保留，只是界面不编辑 */
  maxLength: number
  /** 界面暴露的前几位，顺序与计划表存储顺序一致 */
  parts: BAAHKeyPart[]
}

const PLAN_TIME_KEYS: PlanTimeKey[] = [
  'ALL',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

// 六类关卡逐位的含义固定：地区 / 关卡 / 次数。悬赏通缉、特殊任务、学园交流会的
// 关卡位可以填 -1（最高关），困难图与普通图走上游的滚动选择，只能从 1 开始。
const BAAH_KEY_FIELDS: BAAHKeyField[] = [
  {
    field: 'Event',
    labelKey: 'plan.baah.event',
    hintKey: 'plan.baah.eventHint',
    defaultValue: [1, 1],
    maxLength: 3,
    parts: [
      { hintKey: 'plan.baah.partStageIndex', min: 1 },
      { hintKey: 'plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Wanted',
    labelKey: 'plan.baah.wanted',
    hintKey: 'plan.baah.wantedHint',
    defaultValue: [1, -1, 1],
    maxLength: 4,
    parts: [
      { hintKey: 'plan.baah.partRegion', min: 1 },
      { hintKey: 'plan.baah.partLevelHighest', min: -1 },
      { hintKey: 'plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Special',
    labelKey: 'plan.baah.special',
    hintKey: 'plan.baah.specialHint',
    defaultValue: [1, -1, 1],
    maxLength: 4,
    parts: [
      { hintKey: 'plan.baah.partRegion', min: 1 },
      { hintKey: 'plan.baah.partLevelHighest', min: -1 },
      { hintKey: 'plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Exchange',
    labelKey: 'plan.baah.exchange',
    hintKey: 'plan.baah.exchangeHint',
    defaultValue: [1, -1, 1],
    maxLength: 4,
    parts: [
      { hintKey: 'plan.baah.partAcademy', min: 1 },
      { hintKey: 'plan.baah.partLevelHighest', min: -1 },
      { hintKey: 'plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Hard',
    labelKey: 'plan.baah.hard',
    hintKey: 'plan.baah.hardHint',
    defaultValue: [1, 1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'plan.baah.partChapter', min: 1 },
      { hintKey: 'plan.baah.partLevel', min: 1 },
      { hintKey: 'plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Normal',
    labelKey: 'plan.baah.normal',
    hintKey: 'plan.baah.normalHint',
    defaultValue: [1, 1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'plan.baah.partChapter', min: 1 },
      { hintKey: 'plan.baah.partLevel', min: 1 },
      { hintKey: 'plan.baah.partTimes', min: -1 },
    ],
  },
]

const BAAH_KEY_FIELD_BY_NAME = Object.fromEntries(
  BAAH_KEY_FIELDS.map(field => [field.field, field])
) as Record<BAAHKeyFieldName, BAAHKeyField>

type BAAHDayKey = Record<BAAHKeyFieldName, number[]>

const toIntegerArray = (raw: unknown): number[] =>
  Array.isArray(raw)
    ? raw.map(item => Number(item)).filter(item => Number.isInteger(item))
    : []

/** 把一格（ALL 或某一天）收敛成六个字段的整数数组，缺位补默认值 */
const normalizeBAAHDayKey = (slot: unknown): BAAHDayKey => {
  const slotData = slot && typeof slot === 'object' ? (slot as Record<string, unknown>) : {}
  const rawKey = slotData.Key && typeof slotData.Key === 'object' ? slotData.Key : slotData
  const keyData = rawKey as Record<string, unknown>

  const dayKey = {} as BAAHDayKey
  for (const field of BAAH_KEY_FIELDS) {
    const items = toIntegerArray(keyData[field.field]).slice(0, field.maxLength)
    // 界面只编辑前几位，后端允许的可选位原样留着，不能在这里截掉
    for (let index = items.length; index < field.parts.length; index += 1) {
      items.push(field.defaultValue[index] ?? 1)
    }
    dayKey[field.field] = items
  }
  return dayKey
}

const localTableData = ref<Partial<Record<PlanTimeKey, BAAHDayKey>>>({})

const syncLocalTableData = (tableData: Record<string, any> | null) => {
  localTableData.value = Object.fromEntries(
    PLAN_TIME_KEYS.map(timeKey => [timeKey, normalizeBAAHDayKey(tableData?.[timeKey])])
  ) as Partial<Record<PlanTimeKey, BAAHDayKey>>
}

watch(() => props.tableData, syncLocalTableData, { immediate: true })

const configColumns = computed(() => [
  {
    title: t('plan.table.field'),
    dataIndex: 'fieldName',
    key: 'fieldName',
    width: 130,
    fixed: 'left',
    align: 'center',
  },
  ...PLAN_TIME_KEYS.map(timeKey => ({
    title: t(`plan.week.${timeKey}`),
    dataIndex: timeKey,
    key: timeKey,
    width: 190,
    align: 'center',
  })),
])

const asTimeKey = (value: string): PlanTimeKey => value as PlanTimeKey

const isColumnDisabled = (timeKey: PlanTimeKey) => {
  if (props.currentMode === 'ALL') return timeKey !== 'ALL'
  return timeKey === 'ALL'
}

const getDayKey = (timeKey: PlanTimeKey): BAAHDayKey =>
  localTableData.value[timeKey] ?? normalizeBAAHDayKey(null)

const configRows = computed(() =>
  BAAH_KEY_FIELDS.map(field => ({
    rowKey: field.field,
    field: field.field,
    fieldName: t(field.labelKey),
    fieldHint: t(field.hintKey),
    parts: field.parts.map((part, index) => ({
      index,
      min: part.min,
      hint: t(part.hintKey),
    })),
    ...Object.fromEntries(
      PLAN_TIME_KEYS.map(timeKey => [timeKey, getDayKey(timeKey)[field.field]])
    ),
  }))
)

const toPartValue = (value: number | string | null, fallback: number): number => {
  const parsed = typeof value === 'string' ? Number(value) : value
  return typeof parsed === 'number' && Number.isInteger(parsed) ? parsed : fallback
}

/** 改一位：先落到本地让界面即时反馈，保存失败再退回原来的那一格 */
const handlePartChange = async (
  timeKey: PlanTimeKey,
  field: BAAHKeyFieldName,
  index: number,
  value: number | string | null
) => {
  const fieldSpec = BAAH_KEY_FIELD_BY_NAME[field]
  const previous = localTableData.value[timeKey]
  const nextItems = [...(previous?.[field] ?? fieldSpec.defaultValue)]
  nextItems[index] = toPartValue(value, fieldSpec.defaultValue[index] ?? 1)

  const nextDayKey = { ...(previous ?? normalizeBAAHDayKey(null)), [field]: nextItems }

  localTableData.value = {
    ...localTableData.value,
    [timeKey]: nextDayKey,
  }

  // 后端按「日期 → Key」两级写入，只能整格提交：只发单个字段会被当成整份 Key，
  // 其余五类关卡会被补成默认值
  const saved = await props.handlePlanChange(`${timeKey}.Key`, nextDayKey, false)
  if (!saved) {
    localTableData.value = {
      ...localTableData.value,
      [timeKey]: previous ?? normalizeBAAHDayKey(null),
    }
  }
}
</script>

<style scoped>
.config-table-wrapper {
  overflow: hidden;
}

.config-table :deep(.ant-table-cell) {
  vertical-align: middle;
}

.key-cell {
  display: flex;
  justify-content: center;
  gap: 4px;
}

.config-number {
  width: 56px;
}

.config-number :deep(.ant-input-number-input) {
  padding: 0 4px;
  text-align: center;
}

.field-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  cursor: help;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}
</style>
