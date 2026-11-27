import type { PluginConfigUi, UiSection, UiStep } from '@/api'
import { computed, reactive, ref, watch, type ComputedRef } from 'vue'
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

type LayoutGroup = { name: string; hints: DeclarativeHint[] }
type CardContent =
  | { table: DeclarativeTableHint; columnTypes: Record<string, string> }
  | { group: LayoutGroup; runs: ReturnType<typeof fieldRuns> }

/** 先从可见字段中提取行内动作、表格，再按插件声明分步。 */
export function declarativeLayout(
  groups: LayoutGroup[],
  tables: DeclarativeTableHint[],
  steps: UiStep[] = [],
  sections: Record<string, UiSection> = {}
) {
  const fields = new Map<string, { group: string; hint: DeclarativeHint }>(
    groups.flatMap(({ name, hints }) =>
      hints.map(hint => [`${name}.${hint.field}`, { group: name, hint }] as const)
    )
  )
  const actions = new Map<string, { group: string; hint: DeclarativeHint }>()
  const referenced = new Set<string>()
  for (const [key, { hint }] of fields) {
    const ref = hint.action_ref
    const target = ref && fields.get(ref)
    if (
      target &&
      !referenced.has(ref) &&
      ['button', 'dropdown-button'].includes(target.hint.component ?? '')
    ) {
      actions.set(key, target)
      referenced.add(ref)
    }
  }
  const hintFor = (group: string, field: string) => {
    const key = `${group}.${field}`
    return referenced.has(key) ? undefined : fields.get(key)?.hint
  }
  const card = (key: string, fields: string[], content: CardContent) => ({
    key,
    fields,
    ...content,
    step: sections[key]?.step ?? steps[0]?.key ?? '',
    collapsible: !!sections[key]?.collapsible,
    defaultCollapsed: !!sections[key]?.default_collapsed,
  })
  const tableFields = new Set<string>()
  const cards = tables.flatMap((source, index) => {
    const rows = source.rows.filter(group => source.columns.some(field => hintFor(group, field)))
    const columns = source.columns.filter(field => rows.some(group => hintFor(group, field)))
    if (!rows.length) return []
    const table = { ...source, rows, columns }
    const keys = rows.flatMap(group =>
      columns.filter(field => hintFor(group, field)).map(field => `${group}.${field}`)
    )
    for (const key of keys) tableFields.add(key)
    return [
      card(table.key == null ? `anonymous-table:${index}` : `table:${table.key}`, keys, {
        table,
        columnTypes: tableColumnTypes(table, hintFor),
      }),
    ]
  })
  for (const { name, hints } of groups) {
    const remaining = hints.filter(
      ({ field }) => !referenced.has(`${name}.${field}`) && !tableFields.has(`${name}.${field}`)
    )
    if (remaining.length)
      cards.push(
        card(
          `group:${name}`,
          remaining.map(hint => `${name}.${hint.field}`),
          { group: { name, hints: remaining }, runs: fieldRuns(remaining) }
        )
      )
  }
  const visibleSteps = (steps.length ? steps : [{ key: '' }])
    .map(step => ({
      ...step,
      cards: cards.filter(card => card.step === step.key),
    }))
    .filter(step => step.cards.length)
  return { steps: visibleSteps, cards, actions, hintFor }
}

/** 同一 UID 重读布局时保留折叠选择；后台字段错误优先于当前步骤。 */
export function useDeclarativeSteps(
  layout: ComputedRef<ReturnType<typeof declarativeLayout>>,
  uid: () => string,
  errors: () => Record<string, string>
) {
  const selected = ref('')
  const collapsedByUid = reactive(new Map<string, Record<string, boolean>>())
  watch(
    [uid, layout],
    ([id, { cards }], previous) => {
      if (id !== previous?.[0]) selected.value = ''
      if (!collapsedByUid.has(id)) collapsedByUid.set(id, {})
      const state = collapsedByUid.get(id)!
      for (const card of cards) state[card.key] ??= card.defaultCollapsed
    },
    { immediate: true, flush: 'sync' }
  )
  const collapsed = computed(() => collapsedByUid.get(uid())!)
  const current = computed({
    get: () =>
      Math.max(
        0,
        layout.value.steps.findIndex(step => step.key === selected.value)
      ),
    set: index => {
      selected.value = layout.value.steps[index].key
    },
  })
  watch(
    errors,
    fields => {
      for (const field of Object.keys(fields)) {
        const card = layout.value.cards.find(card => card.fields.includes(field))
        if (card) {
          selected.value = card.step
          collapsed.value[card.key] = false
          break
        }
      }
    },
    { immediate: true }
  )
  return { current, collapsed }
}
