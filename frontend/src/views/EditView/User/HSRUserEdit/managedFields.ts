import type { HSREngine, HSRManagedField } from '@/composables/useHSRPluginApi'

/**
 * HSR 模块设置里字段的分组、显示条件与摘要。后端新加的 group / overridden /
 * native_value / visible_when 全部可选：没给时一律按「common、未覆盖、无原值、恒显示」退化。
 */

export const COMMON_GROUP = 'common'

export const fieldGroupOf = (field: HSRManagedField): string =>
  typeof field.group === 'string' && field.group ? field.group : COMMON_GROUP

export const isFieldOverridden = (field: HSRManagedField): boolean => field.overridden === true

/** 单项恢复需要知道原值：后端没给 native_value 时不提供单项恢复。 */
export const canResetField = (field: HSRManagedField): boolean =>
  isFieldOverridden(field) && field.native_value !== undefined

const sameValue = (a: unknown, b: unknown): boolean =>
  a === b || JSON.stringify(a) === JSON.stringify(b)

/**
 * visible_when 按同表单里依赖字段的当前生效值判断；依赖字段不在表单里时照常显示，
 * 免得后端字段表调整时把整片设置藏起来。
 */
export const isFieldVisible = (
  field: HSRManagedField,
  fields: readonly HSRManagedField[]
): boolean => {
  const rule = field.visible_when
  if (!rule || typeof rule.key !== 'string' || !Array.isArray(rule.values)) return true
  const dependency = fields.find(item => item.key === rule.key)
  if (!dependency) return true
  return rule.values.some(value => sameValue(value, dependency.value))
}

export interface HSRFieldGroupLayout {
  key: string
  fields: HSRManagedField[]
  /** 该组里在 MAS 中改过的字段数（含当前被 visible_when 隐藏的）。 */
  overriddenCount: number
}

/**
 * 按分组拆字段：common 平铺，其余分组按首次出现的顺序排；组内保持后端给的顺序。
 * 被 visible_when 隐藏的字段不进 fields，但仍计入「已改」数。
 */
export const splitFieldsByGroup = (
  fields: readonly HSRManagedField[]
): { common: HSRManagedField[]; groups: HSRFieldGroupLayout[] } => {
  const common: HSRManagedField[] = []
  const groups = new Map<string, HSRFieldGroupLayout>()
  for (const field of fields) {
    const key = fieldGroupOf(field)
    const visible = isFieldVisible(field, fields)
    if (key === COMMON_GROUP) {
      if (visible) common.push(field)
      continue
    }
    let group = groups.get(key)
    if (!group) {
      group = { key, fields: [], overriddenCount: 0 }
      groups.set(key, group)
    }
    if (visible) group.fields.push(field)
    if (isFieldOverridden(field)) group.overriddenCount += 1
  }
  return {
    common,
    // 整组字段都被隐藏时不出空面板
    groups: [...groups.values()].filter(group => group.fields.length > 0),
  }
}

export interface HSRValueLabels {
  on: string
  off: string
  empty: string
}

/** 把字段值格式化成一小段可读文字（摘要、原值悬停提示用）。 */
export const formatManagedValue = (
  field: Pick<HSRManagedField, 'type' | 'options'>,
  value: unknown,
  labels: HSRValueLabels
): string => {
  if (typeof value === 'boolean') return value ? labels.on : labels.off
  const option = field.options?.find(item => sameValue(item.value, value))
  if (option) return option.label
  if (value === null || value === undefined || value === '') return labels.empty
  if (Array.isArray(value) && value.length === 0) return labels.empty
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 60 ? `${text.slice(0, 57)}...` : text
}

/**
 * 模块在列表里的一句摘要：列出最多 2 个在 MAS 里改过的设置，没改过返回 null
 * （调用方显示「沿用三月七 / SRA 里的设置」）。
 */
export const summarizeOverriddenFields = (
  fields: readonly HSRManagedField[],
  labels: HSRValueLabels,
  limit = 2
): { items: { label: string; value: string }[]; rest: number } | null => {
  const overridden = fields.filter(isFieldOverridden)
  if (!overridden.length) return null
  return {
    items: overridden.slice(0, limit).map(field => ({
      label: field.label,
      value: formatManagedValue(field, field.value, labels),
    })),
    rest: Math.max(0, overridden.length - limit),
  }
}

/** 两个引擎各自的「培养目标」开关：开启后刷取副本被忽略（SRA）或只作兜底（三月七）。 */
const BUILD_TARGET_KEYS: Record<HSREngine, string> = {
  SRA: 'useBuildTarget',
  M7A: 'build_target_enable',
}

export const findEnabledBuildTargetField = (
  engine: HSREngine | undefined,
  fields: readonly HSRManagedField[] | undefined
): HSRManagedField | null => {
  if (!engine || !fields) return null
  const field = fields.find(item => item.key === BUILD_TARGET_KEYS[engine])
  return field && field.value === true ? field : null
}

// ── 三月七两个列表字段的行编辑器数据 ──

/** 用行编辑器代替 JSON 文本框的字段（值不是数组时仍退回 JSON 文本框）。 */
export const ROW_LIST_FIELD_KEYS = new Set(['instance_teams', 'borrow_friends'])

export const isRowListField = (field: HSRManagedField): boolean =>
  ROW_LIST_FIELD_KEYS.has(field.key) && Array.isArray(field.value)

export interface HSRListRow {
  /** instance_teams：副本名；borrow_friends：角色名 */
  first: string
  /** instance_teams：队伍号；borrow_friends：好友名 */
  second: string
  /** instance_teams 条目里前端不认识的其余键，原样带回 */
  rest?: Record<string, unknown>
}

const text = (value: unknown): string =>
  value === null || value === undefined ? '' : String(value)

export const listFieldToRows = (key: string, value: unknown): HSRListRow[] => {
  if (!Array.isArray(value)) return []
  if (key === 'instance_teams') {
    return value
      .filter(
        (item): item is Record<string, unknown> =>
          !!item && typeof item === 'object' && !Array.isArray(item)
      )
      .map(item => {
        const { instance_name: name, team_number: team, ...rest } = item
        return {
          first: text(name),
          second: text(team),
          ...(Object.keys(rest).length ? { rest } : {}),
        }
      })
  }
  return value
    .filter((item): item is unknown[] => Array.isArray(item))
    .map(item => ({ first: text(item[0]), second: text(item[1]) }))
}

/**
 * 行 → 三月七原生结构。没填完的行（副本名 / 队伍号 / 角色名为空）不写入，
 * 让用户先加空行再慢慢填，而不是把半行存进配置。
 */
export const rowsToListField = (key: string, rows: readonly HSRListRow[]): unknown[] => {
  if (key === 'instance_teams') {
    return rows
      .filter(row => row.first.trim() && row.second.trim())
      .map(row => ({
        ...(row.rest ?? {}),
        instance_name: row.first.trim(),
        team_number: row.second.trim(),
      }))
  }
  return rows.filter(row => row.first.trim()).map(row => [row.first.trim(), row.second.trim()])
}
