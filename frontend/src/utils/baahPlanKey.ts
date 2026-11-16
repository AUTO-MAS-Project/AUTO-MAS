// BAAH 计划表 key 的前端契约：五类关卡每一位的含义、缺席 / 空 / 有值三态的读法与换算。
// 取值规则与后端 app/models/config.py 的 BAAH_PLAN_KEY_SHAPE 一一对应，改一处要改两处。

export type BAAHKeyFieldName = 'Wanted' | 'Special' | 'Exchange' | 'Hard' | 'Normal'

/** 参数里的一位：词表 key 说明这一位是什么，min 是允许的最小值（-1 = 最高关或最大次数） */
export interface BAAHKeyPart {
  hintKey: string
  min: number
}

export interface BAAHKeyField {
  field: BAAHKeyFieldName
  labelKey: string
  /** 界面暴露那几位的默认值，顺序与 parts 一致 */
  defaultValue: number[]
  /** 后端允许的最长位数；多出来的位照旧保留，只是界面不编辑 */
  maxLength: number
  /** 界面暴露的位，顺序与存储顺序一致 */
  parts: BAAHKeyPart[]
}

// 五类关卡的参数都是「… / 关卡 / 次数」收尾：悬赏通缉、特别委托、学园交流会前面是
// 地区或学院，困难图与普通图前面是章节。关卡位只有悬赏通缉、
// 特殊任务、学园交流会能填 -1（最高关），困难图与普通图走上游的滚动选择，只能从 1 起。
export const BAAH_PLAN_KEY_FIELDS: BAAHKeyField[] = [
  {
    field: 'Wanted',
    labelKey: 'core.plan.baah.wanted',
    defaultValue: [1, -1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'core.plan.baah.partRegion', min: 1 },
      { hintKey: 'core.plan.baah.partLevelHighest', min: -1 },
      { hintKey: 'core.plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Special',
    labelKey: 'core.plan.baah.special',
    defaultValue: [1, -1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'core.plan.baah.partRegion', min: 1 },
      { hintKey: 'core.plan.baah.partLevelHighest', min: -1 },
      { hintKey: 'core.plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Exchange',
    labelKey: 'core.plan.baah.exchange',
    defaultValue: [1, -1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'core.plan.baah.partAcademy', min: 1 },
      { hintKey: 'core.plan.baah.partLevelHighest', min: -1 },
      { hintKey: 'core.plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Hard',
    labelKey: 'core.plan.baah.hard',
    defaultValue: [1, 1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'core.plan.baah.partChapter', min: 1 },
      { hintKey: 'core.plan.baah.partLevel', min: 1 },
      { hintKey: 'core.plan.baah.partTimes', min: -1 },
    ],
  },
  {
    field: 'Normal',
    labelKey: 'core.plan.baah.normal',
    defaultValue: [1, 1, -1],
    maxLength: 4,
    parts: [
      { hintKey: 'core.plan.baah.partChapter', min: 1 },
      { hintKey: 'core.plan.baah.partLevel', min: 1 },
      { hintKey: 'core.plan.baah.partTimes', min: -1 },
    ],
  },
]

export const BAAH_KEY_FIELD_BY_NAME = Object.fromEntries(
  BAAH_PLAN_KEY_FIELDS.map(field => [field.field, field])
) as Record<BAAHKeyFieldName, BAAHKeyField>

/**
 * 一格（ALL 或某一天）实际写过的字段。字段不在这里＝缺席：今天这一类不干预，
 * BAAH 沿用自己配置文件里的关卡与开关。空数组则是「今天不打这一类」。
 */
export type BAAHDayFields = Partial<Record<BAAHKeyFieldName, number[]>>

/**
 * 每一位在下拉里能选到几：次数最少，章节最多，地区与学院居中，其余按关卡给。
 * -1（倒数第一个可扫荡关卡 / 最大次数）不在这里，由各位自己的 min 决定要不要列。
 */
export const partOptionMax = (hintKey: string, field?: BAAHKeyFieldName): number => {
  if (hintKey === 'core.plan.baah.partTimes') return 10
  if (hintKey === 'core.plan.baah.partRegion') return field === 'Special' ? 2 : 3
  if (hintKey === 'core.plan.baah.partAcademy') return 3
  if (hintKey === 'core.plan.baah.partChapter') return 30
  return 15
}

const toIntegerArray = (raw: unknown): number[] =>
  Array.isArray(raw) ? raw.map(item => Number(item)).filter(item => Number.isInteger(item)) : []

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
 * 一类关卡在某一天的状态：开＝按这里的参数打，关＝今天不打这一类，
 * 交给 BAAH＝今天不干预，沿用上游配置文件里的关卡与开关。
 */
export type BAAHFieldState = 'on' | 'off' | 'auto'

export const readFieldState = (
  fields: BAAHDayFields | undefined,
  field: BAAHKeyFieldName
): BAAHFieldState => {
  const items = fields?.[field]
  // 字段不在就是交给 BAAH：后端读到缺席会沿用上游配置，补一份出来就成了按默认关卡打
  if (items === undefined) return 'auto'
  return items.length > 0 ? 'on' : 'off'
}

/**
 * 切换一类关卡的状态，只动这一类，其余类别原样带过去。
 *
 * 「交给 BAAH」要把字段整个从这一天的 key 里去掉：后端按整份 key 覆写，字段不在才
 * 表示不干预；写成空数组会被上游当成「今天不打」，写成 null 则要看后端是否剔除。
 */
export const applyFieldState = (
  fields: BAAHDayFields | undefined,
  field: BAAHKeyFieldName,
  state: BAAHFieldState
): BAAHDayFields => {
  const next: BAAHDayFields = { ...(fields ?? {}) }

  if (state === 'auto') {
    delete next[field]
    return next
  }

  // 打开时优先沿用原来填过的值，不会把用户改过的关卡重置成默认值
  next[field] = state === 'on' ? readFieldValues(fields, field) : []
  return next
}
