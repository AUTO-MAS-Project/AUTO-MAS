import type { PluginConfigUi } from '@/api'
import type { DeclarativeHint } from '@/composables/useDeclarativeOptions'
import type { DeclarativeTableHint } from './DeclarativeTable.vue'

export const declarativeGroups = (ui?: PluginConfigUi | null) =>
  Object.entries(ui?.hints ?? {}).flatMap(([name, hints]) =>
    Array.isArray(hints) && hints.length ? [{ name, hints }] : []
  )

/** 接口按组分列，表单按组分行，再由表格组件应用 transpose。 */
export const declarativeTables = (ui?: PluginConfigUi | null) =>
  (ui?.tables ?? []).map(table => ({ ...table, rows: table.columns, columns: table.rows }))

export function declarativeValues(
  groups: ReturnType<typeof declarativeGroups>,
  document: Record<string, unknown>
): Record<string, Record<string, unknown>> {
  return Object.fromEntries(
    groups.map(({ name, hints }) => {
      const source = document[name]
      const values = source && typeof source === 'object' ? Object.entries(source) : []
      const fields = values.filter(
        ([field]) => !hints.some(hint => hint.field === field && hint.state !== undefined)
      )
      return [name, Object.fromEntries(fields)]
    })
  )
}

function isTileSwitch(hint: DeclarativeHint) {
  return (
    hint.component === 'switch' &&
    (!hint.widget || hint.widget === 'switch') &&
    !hint.secret &&
    !hint.masked &&
    hint.format !== 'time' &&
    hint.format !== 'datetime'
  )
}

export function isWideField(hint: DeclarativeHint) {
  return (
    hint.component === 'path' ||
    hint.component === 'textarea' ||
    hint.widget === 'textarea' ||
    (hint.multiple && hint.ordered)
  )
}

/** 孤立开关与相邻普通字段共用栅格，只有相邻开关才切换排版。 */
export function fieldRuns(hints: DeclarativeHint[]) {
  const runs: Array<{ tiles: boolean; hints: DeclarativeHint[] }> = []
  const switches = hints.map(isTileSwitch)
  for (const [index, hint] of hints.entries()) {
    const tiles = Boolean(switches[index] && (switches[index - 1] || switches[index + 1]))
    const last = runs.at(-1)
    if (last && last.tiles === tiles) last.hints.push(hint)
    else runs.push({ tiles, hints: [hint] })
  }
  return runs
}

/** 按显示坐标取列。转置后同一列可能混合多种控件，此时留给表格自适应。 */
export function tableColumnTypes(
  table: DeclarativeTableHint,
  hintFor: (group: string, field: string) => DeclarativeHint | undefined
) {
  const types: Record<string, string> = Object.create(null)
  for (const column of table.transpose ? table.rows : table.columns) {
    const cells = table.transpose
      ? table.columns.map(field => hintFor(column, field))
      : table.rows.map(group => hintFor(group, column))
    const kinds = new Set(
      cells.filter(hint => hint !== undefined).map(hint => hint.component ?? 'input')
    )
    if (kinds.size === 1) types[column] = [...kinds][0]!
  }
  return types
}
