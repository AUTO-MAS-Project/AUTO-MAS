// BAAH 计划表 key 的前端契约：六类关卡每一位的含义、缺席 / 空 / 有值三态的读法，
// 以及「每天一类」那三行与整份 key 之间的换算。
// 取值规则与后端 app/models/config.py 的 BAAH_PLAN_KEY_SHAPE 一一对应，改一处要改两处。

export type PlanTimeKey =
  | 'ALL'
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

export type BAAHKeyFieldName = 'Event' | 'Wanted' | 'Special' | 'Exchange' | 'Hard' | 'Normal'

/** 参数里的一位：词表 key 说明这一位是什么，min 是允许的最小值（-1 = 最高关或最大次数） */
export interface BAAHKeyPart {
  hintKey: string
  min: number
}

export interface BAAHKeyField {
  field: BAAHKeyFieldName
  labelKey: string
  hintKey: string
  /** 界面暴露那几位的默认值，顺序与 parts 一致 */
  defaultValue: number[]
  /** 后端允许的最长位数；多出来的位照旧保留，只是界面不编辑 */
  maxLength: number
  /** 界面暴露的位，顺序与存储顺序一致 */
  parts: BAAHKeyPart[]
}

export const BAAH_PLAN_TIME_KEYS: PlanTimeKey[] = [
  'ALL',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

// 六类关卡的参数都是「… / 关卡 / 次数」收尾：悬赏通缉、特殊任务、学园交流会前面是
// 地区或学院，困难图与普通图前面是章节，活动关卡没有前面那位。关卡位只有悬赏通缉、
// 特殊任务、学园交流会能填 -1（最高关），困难图与普通图走上游的滚动选择，只能从 1 起。
export const BAAH_PLAN_KEY_FIELDS: BAAHKeyField[] = [
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

export const BAAH_KEY_FIELD_BY_NAME = Object.fromEntries(
  BAAH_PLAN_KEY_FIELDS.map(field => [field.field, field])
) as Record<BAAHKeyFieldName, BAAHKeyField>

/** 多类混打要的六类齐全形态 */
export type BAAHDayKey = Record<BAAHKeyFieldName, number[]>

/**
 * 一格（ALL 或某一天）实际写过的字段。字段不在这里＝缺席：今天这一类不干预，
 * BAAH 沿用自己配置文件里的关卡与开关。空数组则是「今天不打这一类」。
 */
export type BAAHDayFields = Partial<Record<BAAHKeyFieldName, number[]>>

/** 「每天一类」那三行分别是打哪类、第几关、打几次 */
export type BAAHSingleRowKind = 'stage' | 'times'

/**
 * 每一位在下拉里能选到几：次数最少，章节最多，地区与学院居中，其余按关卡给。
 * -1（倒数第一个可扫荡关卡 / 最大次数）不在这里，由各位自己的 min 决定要不要列。
 */
export const partOptionMax = (hintKey: string): number => {
  if (hintKey === 'plan.baah.partTimes') return 10
  if (hintKey === 'plan.baah.partRegion' || hintKey === 'plan.baah.partAcademy') return 10
  if (hintKey === 'plan.baah.partChapter') return 30
  return 15
}

export interface BAAHSingleCell {
  kind: BAAHKeyFieldName | ''
  stage: number
  times: number
}

/** 关卡位：填 0 算不出关卡坐标，上游只认 -1（最高关）或 1 以上 */
const STAGE_PART_HINT_KEYS = new Set(['plan.baah.partLevelHighest', 'plan.baah.partLevel'])

export const isStagePart = (part: BAAHKeyPart | undefined): boolean =>
  part !== undefined && STAGE_PART_HINT_KEYS.has(part.hintKey)

const toIntegerArray = (raw: unknown): number[] =>
  Array.isArray(raw) ? raw.map(item => Number(item)).filter(item => Number.isInteger(item)) : []

/** 输入框给回来的值：空字符串与非法值都退回 fallback */
export const toPlanInt = (raw: number | string | null | undefined, fallback: number): number => {
  const parsed = typeof raw === 'string' ? Number(raw) : raw
  return typeof parsed === 'number' && Number.isInteger(parsed) ? parsed : fallback
}

/**
 * 把一格读成「实际出现过的字段」，缺席的字段不补。
 *
 * 补默认值会让「今天这一类不干预」静默变成「按默认关卡打」；空数组按位数补齐会让
 * 「今天不打」变成打默认关卡。这两种状态必须原样带过去。
 */
export const readDayFields = (slot: unknown): BAAHDayFields => {
  const slotData = slot && typeof slot === 'object' ? (slot as Record<string, unknown>) : {}
  const rawKey = slotData.Key && typeof slotData.Key === 'object' ? slotData.Key : slotData
  const keyData = rawKey as Record<string, unknown>

  const fields: BAAHDayFields = {}
  for (const field of BAAH_PLAN_KEY_FIELDS) {
    // 后端序列化时把缺席字段写成 null，与字段不在是同一种状态
    const raw = keyData[field.field]
    if (raw === null || raw === undefined) continue

    if (Array.isArray(raw) && raw.length === 0) {
      fields[field.field] = []
      continue
    }

    const items = toIntegerArray(raw).slice(0, field.maxLength)
    // 界面只编辑前几位，后端允许的可选位原样留着
    for (let index = items.length; index < field.parts.length; index += 1) {
      items.push(field.defaultValue[index] ?? 1)
    }
    fields[field.field] = items
  }
  return fields
}

/** 多类混打要的六类齐全形态：缺席与空数组都按默认值填出来，输入框才有值可编 */
export const fillDayFields = (fields: BAAHDayFields): BAAHDayKey => {
  const dayKey = {} as BAAHDayKey
  for (const field of BAAH_PLAN_KEY_FIELDS) {
    const items = [...(fields[field.field] ?? [])].slice(0, field.maxLength)
    for (let index = items.length; index < field.parts.length; index += 1) {
      items.push(field.defaultValue[index] ?? 1)
    }
    dayKey[field.field] = items
  }
  return dayKey
}

/**
 * 从一格读出「今天打哪一类」。
 *
 * 这种排法的落盘形状是恰好一类有值、其余五类空数组；旧数据写成恰好一类缺席、其余五类
 * 空数组，这里一并认出来，但不替用户改写数据——只有用户真的动过这一格才会按现在的规则
 * 落盘。读不出这两种形状时（多类混打的排法）返回空。
 */
export const resolveDayKind = (fields: BAAHDayFields | undefined): BAAHKeyFieldName | '' => {
  if (!fields) return ''

  const valued = BAAH_PLAN_KEY_FIELDS.filter(field => (fields[field.field] ?? []).length > 0)
  if (valued.length === 1) return valued[0].field
  if (valued.length > 1) return ''

  const absent = BAAH_PLAN_KEY_FIELDS.filter(field => !(field.field in fields))
  return absent.length === 1 ? absent[0].field : ''
}

/** 读一类的参数：空数组与缺席都按该类默认值填出来，输入框才有值可编 */
export const readFieldValues = (
  fields: BAAHDayFields | undefined,
  field: BAAHKeyFieldName
): number[] => {
  const spec = BAAH_KEY_FIELD_BY_NAME[field]
  const items = [...(fields?.[field] ?? [])].slice(0, spec.maxLength)
  for (let index = items.length; index < spec.parts.length; index += 1) {
    items.push(spec.defaultValue[index] ?? 1)
  }
  return items
}

/**
 * 「关卡」与「次数」各对应这一类参数的第几位。
 *
 * 六类都以「… / 关卡 / 次数」收尾，所以从后往前数与类别无关；前面的地区 / 章节 /
 * 学院位沿用原值或默认值，不在这三行里编辑。
 */
export const partIndexOf = (spec: BAAHKeyField, rowKind: BAAHSingleRowKind): number =>
  rowKind === 'stage' ? spec.parts.length - 2 : spec.parts.length - 1

/**
 * 这一类的关卡位能不能选「最高关」（-1）。
 * 悬赏通缉 / 特殊任务 / 学园交流会可以，困难与普通关卡走上游的滚动选择，只能填具体关卡号。
 */
export const allowsHighestStage = (kind: BAAHKeyFieldName | ''): boolean => {
  const spec = kind ? BAAH_KEY_FIELD_BY_NAME[kind] : undefined
  if (!spec) return false
  return spec.parts[partIndexOf(spec, 'stage')].min === -1
}

/** 每天一类：一格读成三行要显示的那三个值 */
export const readSingleCell = (fields: BAAHDayFields | undefined): BAAHSingleCell => {
  const kind = resolveDayKind(fields)
  if (!kind) return { kind: '', stage: 1, times: 1 }

  const spec = BAAH_KEY_FIELD_BY_NAME[kind]
  const values = readFieldValues(fields, kind)
  return {
    kind,
    stage: values[spec.parts.length - 2] ?? 1,
    times: values[spec.parts.length - 1] ?? 1,
  }
}

/** 这一类今天要不要跑：空数组与缺席都算不打 */
export const isFieldEnabled = (
  fields: BAAHDayFields | undefined,
  field: BAAHKeyFieldName
): boolean => (fields?.[field] ?? []).length > 0

/** 每天一类：选中那一类有值，其余五类空数组（今天不打），选「不打」则六类全空 */
export const buildSingleDayKey = (kind: BAAHKeyFieldName | '', items: number[]): BAAHDayFields => {
  const dayKey: BAAHDayFields = {}
  for (const field of BAAH_PLAN_KEY_FIELDS) {
    dayKey[field.field] = kind && field.field === kind ? items : []
  }
  return dayKey
}

export interface BAAHCellWrite {
  fields: BAAHDayFields
  /** 手输的 0 被改成 1 时为 true，界面据此提示用户 */
  corrected: boolean
}

/** 每天一类：改选中那一类的关卡或次数，其余五类照旧空数组 */
export const applySingleNumber = (
  fields: BAAHDayFields | undefined,
  rowKind: BAAHSingleRowKind,
  raw: number | string | null | undefined
): BAAHCellWrite | null => {
  const { kind } = readSingleCell(fields)
  if (!kind) return null

  const spec = BAAH_KEY_FIELD_BY_NAME[kind]
  const index = partIndexOf(spec, rowKind)
  const items = readFieldValues(fields, kind)
  // 输入框清空时给回 null，这时保持原来的取值，不能退回默认值把用户填过的数字抹掉
  const value = toPlanInt(raw, items[index] ?? spec.defaultValue[index] ?? 1)
  const corrected = isStagePart(spec.parts[index]) && value === 0

  items[index] = corrected ? 1 : value
  return { fields: buildSingleDayKey(kind, items), corrected }
}

/** 多类混打：改某一类的某一位，提交的是六类齐全的那一份 key */
export const applyMixedPart = (
  fields: BAAHDayFields | undefined,
  field: BAAHKeyFieldName,
  index: number,
  raw: number | string | null | undefined
): BAAHCellWrite => {
  const spec = BAAH_KEY_FIELD_BY_NAME[field]
  const filled = fillDayFields(fields ?? {})
  const items = [...filled[field]]
  // 同上：清空输入框时保持这一位原来的取值
  const value = toPlanInt(raw, items[index] ?? spec.defaultValue[index] ?? 1)
  const corrected = isStagePart(spec.parts[index]) && value === 0

  items[index] = corrected ? 1 : value
  return { fields: { ...filled, [field]: items }, corrected }
}
