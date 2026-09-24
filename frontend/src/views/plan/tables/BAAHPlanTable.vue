<template>
  <div>
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
          <!-- 每天一类整张表只有一行，行首自己写明这一行是什么 -->
          <template v-if="baahLayout === 'single' && column.key === 'fieldName'">
            <span class="field-label">{{ record.fieldName }}</span>
          </template>

          <template v-else-if="column.key === 'fieldName'">
            <a-tooltip :title="record.fieldHint">
              <span class="field-label">
                {{ record.fieldName }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>

          <!-- 每天一类：先选今天打哪一类，选中后就地填这一类的参数，其余五类写成空数组 -->
          <div v-else-if="baahLayout === 'single'" class="key-cell">
            <a-select
              class="layout-select"
              size="small"
              :value="getSingleChoice(asTimeKey(column.key))"
              :options="singleChoiceOptions"
              :disabled="isColumnDisabled(asTimeKey(column.key))"
              :aria-label="singleSelectLabel(asTimeKey(column.key))"
              @change="handleSingleChoiceChange(asTimeKey(column.key), $event)"
            />
            <!-- 选中一类后就地填这一类的 2~3 个数字，规则与多类混打逐位相同 -->
            <a-tooltip
              v-for="part in singleParts(asTimeKey(column.key))"
              :key="part.index"
              :title="part.hint"
            >
              <a-input-number
                class="config-number"
                size="small"
                :value="singlePartValue(asTimeKey(column.key), part.index)"
                :min="part.min"
                :precision="0"
                :controls="false"
                :disabled="isColumnDisabled(asTimeKey(column.key))"
                :aria-label="`${singleRowLabel} ${part.hint}`"
                @change="handleSinglePartChange(asTimeKey(column.key), part.index, $event)"
              />
            </a-tooltip>
          </div>

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
import { message } from 'ant-design-vue'
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
  /**
   * 关卡安排：多类混打（六类都填）或每天一类（每天只选一类）。
   * 两种排法只在「一格怎么渲染、整份 key 怎么组」上分叉，表格方向都是行 = 六类
   * 关卡、列 = 全局 / 周一~周日。
   */
  baahLayout: 'mixed' | 'single'
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

/** a-table 的行主键：行对象的字段是 rowKey，Ant 默认取 key，不指定会退回索引 */
const rowKeyOf = (record: { rowKey: string }) => record.rowKey

/**
 * 关卡位：悬赏通缉 / 特殊任务 / 学园交流会允许 -1（最高关），困难 / 普通必须 >= 1，
 * 两边都不接受 0（上游按这个值算关卡坐标，0 算不出来）。后端已按位校验，
 * 但输入框的 min 拦不住手输的 0，所以在改值时当场纠正并说明，不让它静默失败。
 */
const STAGE_PART_HINT_KEYS = new Set(['plan.baah.partLevelHighest', 'plan.baah.partLevel'])

/** 多类混打视图要的六类齐全形态 */
type BAAHDayKey = Record<BAAHKeyFieldName, number[]>

/**
 * 一格实际写过的字段。字段不在这里＝**缺席**：今天这一类不干预，BAAH 沿用自己
 * 配置文件里的关卡与开关。空数组则是「今天不打这一类」。两者与「有值」是三态，
 * 前端不能把它们抹平成同一个默认值。
 */
type BAAHDayFields = Partial<Record<BAAHKeyFieldName, number[]>>

const toIntegerArray = (raw: unknown): number[] =>
  Array.isArray(raw) ? raw.map(item => Number(item)).filter(item => Number.isInteger(item)) : []

/**
 * 把一格（ALL 或某一天）读成「实际出现过的字段」，缺席的字段不补。
 *
 * 补默认值会让「今天这一类不干预」静默变成「按默认关卡打」，这是本次改动最容易
 * 丢掉的语义；空数组同样保持原样，按位数补齐会让「今天不打」变成打默认关卡。
 */
const readDayFields = (slot: unknown): BAAHDayFields => {
  const slotData = slot && typeof slot === 'object' ? (slot as Record<string, unknown>) : {}
  const rawKey = slotData.Key && typeof slotData.Key === 'object' ? slotData.Key : slotData
  const keyData = rawKey as Record<string, unknown>

  const fields: BAAHDayFields = {}
  for (const field of BAAH_KEY_FIELDS) {
    // 后端序列化时把缺席字段写成 null，与字段不在是同一种状态
    const raw = keyData[field.field]
    if (raw === null || raw === undefined) continue

    if (Array.isArray(raw) && raw.length === 0) {
      fields[field.field] = []
      continue
    }

    const items = toIntegerArray(raw).slice(0, field.maxLength)
    // 界面只编辑前几位，后端允许的可选位原样留着，不能在这里截掉
    for (let index = items.length; index < field.parts.length; index += 1) {
      items.push(field.defaultValue[index] ?? 1)
    }
    fields[field.field] = items
  }
  return fields
}

/** 多类混打视图用的六类齐全形态：缺席与空数组都按默认值填出来，输入框才有值可编 */
const fillDayFields = (fields: BAAHDayFields): BAAHDayKey => {
  const dayKey = {} as BAAHDayKey
  for (const field of BAAH_KEY_FIELDS) {
    const items = [...(fields[field.field] ?? [])].slice(0, field.maxLength)
    for (let index = items.length; index < field.parts.length; index += 1) {
      items.push(field.defaultValue[index] ?? 1)
    }
    dayKey[field.field] = items
  }
  return dayKey
}

const localTableData = ref<Partial<Record<PlanTimeKey, BAAHDayFields>>>({})

const syncLocalTableData = (tableData: Record<string, any> | null) => {
  localTableData.value = Object.fromEntries(
    PLAN_TIME_KEYS.map(timeKey => [timeKey, readDayFields(tableData?.[timeKey])])
  ) as Partial<Record<PlanTimeKey, BAAHDayFields>>
}

watch(() => props.tableData, syncLocalTableData, { immediate: true })

/** 每天一类那一行的行首文案 */
const singleRowLabel = computed(() => t('plan.baahLayout.singleRowLabel'))

const configColumns = computed(() => {
  // 每天一类整张表只有一行，行首自己写着这一行是什么，左上角不必再挂「配置项」
  const single = props.baahLayout === 'single'

  return [
    {
      title: single ? '' : t('plan.table.field'),
      dataIndex: 'fieldName',
      key: 'fieldName',
      width: single ? 88 : 130,
      fixed: 'left',
      align: 'center',
    },
    ...PLAN_TIME_KEYS.map(timeKey => ({
      title: t(`plan.week.${timeKey}`),
      dataIndex: timeKey,
      key: timeKey,
      // 每天一类时一格是「一个下拉 + 该类的 2~3 个输入框」，与多类混打一样宽
      width: single ? 300 : 190,
      align: 'center',
    })),
  ]
})

const asTimeKey = (value: string): PlanTimeKey => value as PlanTimeKey

const isColumnDisabled = (timeKey: PlanTimeKey) => {
  if (props.currentMode === 'ALL') return timeKey !== 'ALL'
  return timeKey === 'ALL'
}

const getDayKey = (timeKey: PlanTimeKey): BAAHDayKey =>
  fillDayFields(localTableData.value[timeKey] ?? {})

const configRows = computed(() => {
  // 每天一类：一天只有一个选择，整张表就一行「关卡」，八列各一组控件
  if (props.baahLayout === 'single') {
    return [{ rowKey: 'single', fieldName: singleRowLabel.value }]
  }

  return BAAH_KEY_FIELDS.map(field => ({
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
})

const toPartValue = (value: number | string | null, fallback: number): number => {
  const parsed = typeof value === 'string' ? Number(value) : value
  return typeof parsed === 'number' && Number.isInteger(parsed) ? parsed : fallback
}

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

/** 改一位：多类混打用，提交的是六类齐全的那一份 Key */
const handlePartChange = async (
  timeKey: PlanTimeKey,
  field: BAAHKeyFieldName,
  index: number,
  value: number | string | null
) => {
  const fieldSpec = BAAH_KEY_FIELD_BY_NAME[field]
  const previousFields = localTableData.value[timeKey]
  // 起手用六类齐全的那一份：多类混打提交的是整份 Key，缺项会被后端补成默认值
  const previous = fillDayFields(previousFields ?? {})
  const nextItems = [...previous[field]]
  nextItems[index] = toPartValue(value, fieldSpec.defaultValue[index] ?? 1)

  const part = fieldSpec.parts[index]
  if (part && STAGE_PART_HINT_KEYS.has(part.hintKey) && nextItems[index] === 0) {
    nextItems[index] = 1
    message.warning(t('plan.baah.partLevelZeroFixed'))
  }

  const nextDayKey: BAAHDayKey = { ...previous, [field]: nextItems }

  await submitDayKey(timeKey, nextDayKey, previousFields)
}

/**
 * 每天一类：从一格里读出「今天打哪一类」。
 *
 * 这种排法的落盘形状是「恰好一类有值、其余五类空数组」；旧数据写成「恰好一类缺席、
 * 其余五类空数组」，这里一并认出来，但**不替用户改写数据**——只有用户真的动过这一格
 * 才会按现在的规则落盘。读不出这两种形状时（多类混打的排法）显示「不打」。
 */
const getSingleChoice = (timeKey: PlanTimeKey): BAAHKeyFieldName | '' => {
  const fields = localTableData.value[timeKey]
  if (!fields) return ''

  const valued = BAAH_KEY_FIELDS.filter(field => (fields[field.field] ?? []).length > 0)
  if (valued.length === 1) return valued[0].field
  if (valued.length > 1) return ''

  const absent = BAAH_KEY_FIELDS.filter(field => !(field.field in fields))
  return absent.length === 1 ? absent[0].field : ''
}

/** 读一类的参数：空数组与缺席都按该类默认值填出来，输入框才有值可编 */
const readFieldValues = (timeKey: PlanTimeKey, field: BAAHKeyFieldName): number[] => {
  const spec = BAAH_KEY_FIELD_BY_NAME[field]
  const items = [...(localTableData.value[timeKey]?.[field] ?? [])].slice(0, spec.maxLength)
  for (let index = items.length; index < spec.parts.length; index += 1) {
    items.push(spec.defaultValue[index] ?? 1)
  }
  return items
}

/** 每天一类：选中那一类的参数位，规则与多类混打逐位相同；没选类时没有参数位 */
const singleParts = (timeKey: PlanTimeKey) => {
  const choice = getSingleChoice(timeKey)
  if (!choice) return []

  return BAAH_KEY_FIELD_BY_NAME[choice].parts.map((part, index) => ({
    index,
    min: part.min,
    hint: t(part.hintKey),
  }))
}

const singlePartValue = (timeKey: PlanTimeKey, index: number): number => {
  const choice = getSingleChoice(timeKey)
  return choice ? (readFieldValues(timeKey, choice)[index] ?? 1) : 1
}

const singleChoiceOptions = computed(() => [
  { value: '', label: t('plan.baahLayout.emptyOption') },
  ...BAAH_KEY_FIELDS.map(field => ({ value: field.field, label: t(field.labelKey) })),
])

/**
 * 每天一类整张表只有一行，八个下拉只能靠星期区分，否则读屏时每一列念出来都一样。
 */
const singleSelectLabel = (timeKey: PlanTimeKey) =>
  `${singleRowLabel.value} ${t(`plan.week.${timeKey}`)}`

/**
 * 每天一类：选一类就写这一类的**具体参数**，其余五类写空数组；选「不打」则六类全空。
 *
 * 字段缺席那一态留给别处排好的数据（运行期不覆盖，BAAH 用它自己配置里的关卡），
 * 这里的下拉不再产出缺席。
 */
const handleSingleChoiceChange = async (timeKey: PlanTimeKey, value: unknown) => {
  const choice = typeof value === 'string' ? value : ''
  const previousFields = localTableData.value[timeKey]

  const nextDayKey: BAAHDayFields = {}
  for (const field of BAAH_KEY_FIELDS) {
    nextDayKey[field.field] =
      choice && field.field === choice ? readFieldValues(timeKey, field.field) : []
  }

  await submitDayKey(timeKey, nextDayKey, previousFields)
}

/** 每天一类：改选中那一类的第 index 位，其余五类照旧写空数组 */
const handleSinglePartChange = async (
  timeKey: PlanTimeKey,
  index: number,
  value: number | string | null
) => {
  const choice = getSingleChoice(timeKey)
  if (!choice) return

  const fieldSpec = BAAH_KEY_FIELD_BY_NAME[choice]
  const previousFields = localTableData.value[timeKey]
  const nextItems = readFieldValues(timeKey, choice)
  nextItems[index] = toPartValue(value, fieldSpec.defaultValue[index] ?? 1)

  // 关卡位只认 -1（最高关）或 1 以上，手输的 0 在这里当场纠正，与多类混打同一条规则
  const part = fieldSpec.parts[index]
  if (part && STAGE_PART_HINT_KEYS.has(part.hintKey) && nextItems[index] === 0) {
    nextItems[index] = 1
    message.warning(t('plan.baah.partLevelZeroFixed'))
  }

  const nextDayKey: BAAHDayFields = {}
  for (const field of BAAH_KEY_FIELDS) {
    nextDayKey[field.field] = field.field === choice ? nextItems : []
  }

  await submitDayKey(timeKey, nextDayKey, previousFields)
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

.layout-select {
  min-width: 96px;
}

.layout-select :deep(.ant-select-selector) {
  text-align: left;
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
