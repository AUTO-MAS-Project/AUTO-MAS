// 干员目标行视图构建：把 CultivateTargets 行 + 目录 + 练度快照合成为
// 纯展示数据（CultivateOperatorGroup 直接渲染），编辑器只负责状态与保存。
import type { CultivatePreviewOut } from '@/api'
import {
  levelOptionsWithSaved,
  listGoals,
  type CultivateGoalKind,
  type CultivateOperatorCatalogEntry,
  type CultivateTargetRow,
} from './cultivateTargets'

type Progression = NonNullable<CultivatePreviewOut['progressions']>[number]

export interface CultivateGoalLineOption {
  value: number
  label: string
}

export interface CultivateGoalLineState {
  i18n: string
  color: string
}

export interface CultivateGoalLine {
  key: string
  kind: CultivateGoalKind
  targetId: string
  label: string
  options: CultivateGoalLineOption[]
  savedLevel: number
  /** 达成档位的展示文案（达成行不给下拉，直接显示这个） */
  levelLabel: string
  overLimit: boolean
  current: string
  currentUnknown: boolean
  state: CultivateGoalLineState | null
  achieved: boolean
}

export interface CultivateGoalGroup {
  kind: CultivateGoalKind
  label: string
  /** 组标题旁的补充说明（专精组：选专精会同步技能目标到 7 级） */
  hint: string
  lines: CultivateGoalLine[]
}

export interface CultivateOperatorView {
  operatorId: string
  name: string
  profession: string
  rarity: number
  /** 头部摘要：如「精 2 · 技能等级 7 · 专精 ×2 · 模组 ×1」 */
  summary: string
  overLimit: boolean
  groups: CultivateGoalGroup[]
}

export interface BuildCultivateViewsOptions {
  rows: CultivateTargetRow[]
  catalog: CultivateOperatorCatalogEntry[]
  progressions: CultivatePreviewOut['progressions'] | undefined
  /** 模组组仅在开关打开时输出 */
  showModules: boolean
  t: (key: string, params?: Record<string, unknown>) => string
}

const GOAL_STATE_BADGE: Record<string, CultivateGoalLineState> = {
  in_progress: { i18n: 'edit.maaCultivateStateInProgress', color: 'processing' },
  achieved: { i18n: 'edit.maaCultivateStateAchieved', color: 'success' },
  pending_confirm: { i18n: 'edit.maaCultivateStatePending', color: 'warning' },
}

const goalStateBadge = (state: string) => GOAL_STATE_BADGE[state] ?? null

const ELITE_LABEL_KEYS: Record<number, string> = {
  0: 'edit.maaCultivateElite0',
  1: 'edit.maaCultivateElite1',
  2: 'edit.maaCultivateElite2',
}

const SKILL_LABEL_KEYS: Record<number, string> = {
  1: 'edit.maaCultivateSkill1',
  2: 'edit.maaCultivateSkill2',
  3: 'edit.maaCultivateSkill3',
}

// 精英化只认 local/default 也算未知（无任何档案）；专精/模组只有
// 森空岛/手填源携带观测，local（OperBox 结构性无此字段）与 default
// （兜底）的空表是"未观测"而非"当前 0"，按 0 展示会误导用户重刷已达档位
const MASTERY_MODULE_SOURCES = new Set(['skland', 'manual'])

// 职业枚举转中文展示（一图流目录透传，缺失时原样显示）
const PROFESSION_LABELS: Record<string, string> = {
  WARRIOR: '近卫',
  TANK: '重装',
  PIONEER: '先锋',
  SNIPER: '狙击',
  CASTER: '术师',
  MEDIC: '医疗',
  SUPPORT: '辅助',
  SUPPORTER: '辅助',
  SPECIAL: '特种',
  SPECIALIST: '特种',
}

const professionLabel = (profession: string) => PROFESSION_LABELS[profession] ?? profession ?? ''

const currentUnknownOf = (prog: Progression | undefined) => !prog || prog.source === 'default'

// 专精/模组维度的未知判定：与后端 build_requirements 的暂停口径一致
const dimensionUnknownOf = (prog: Progression | undefined, kind: CultivateGoalKind) =>
  kind === 'skill'
    ? !MASTERY_MODULE_SOURCES.has(prog?.source ?? 'default') || prog?.skillLevel == null
    : kind !== 'elite' && !MASTERY_MODULE_SOURCES.has(prog?.source ?? 'default')

const currentTextOf = (
  t: BuildCultivateViewsOptions['t'],
  prog: Progression | undefined,
  kind: CultivateGoalKind,
  targetId: string
): string => {
  const unknown = kind === 'elite' ? currentUnknownOf(prog) : dimensionUnknownOf(prog, kind)
  if (unknown) return t('edit.maaCultivateCurrentUnknown')
  if (kind === 'elite') {
    const eliteLabel = ELITE_LABEL_KEYS[prog!.elite]
    return `${t('edit.maaCultivateCurrent')} ${eliteLabel ? t(eliteLabel) : prog!.elite}`
  }
  if (kind === 'skill') return `${t('edit.maaCultivateCurrent')} ${prog!.skillLevel}`
  const levels = kind === 'mastery' ? prog!.masteries : prog!.modules
  return `${t('edit.maaCultivateCurrent')} ${levels?.[targetId] ?? 0}`
}

// 当前档位数值；维度未知（精英化无档案 / 专精模组非森空岛观测）返回 null
const currentLevelOf = (
  prog: Progression | undefined,
  kind: CultivateGoalKind,
  targetId: string
): number | null => {
  if (kind === 'elite' ? currentUnknownOf(prog) : dimensionUnknownOf(prog, kind)) return null
  if (kind === 'elite') return prog!.elite
  if (kind === 'skill') return prog!.skillLevel ?? null
  const levels = kind === 'mastery' ? prog!.masteries : prog!.modules
  return levels?.[targetId] ?? 0
}

// 达成判定：存的目标档位已被当前练度覆盖（编辑器即时判定，不等后端运行标记）；
// 达成行灰掉下拉只展示档位，避免"当前 3 / 目标三级"却仍可改的违和
const achievedOf = (
  prog: Progression | undefined,
  kind: CultivateGoalKind,
  targetId: string,
  savedLevel: number,
  savedState: string | null
): boolean => {
  if (savedState === 'achieved') return true
  if (!savedLevel) return false
  const current = currentLevelOf(prog, kind, targetId)
  return current !== null && current >= savedLevel
}

// 当前已达档位上限：设任何目标都会被立即达成，行没有可做的事 → 整行隐藏
const maxedOf = (
  prog: Progression | undefined,
  kind: CultivateGoalKind,
  targetId: string,
  maxLevel: number
): boolean => {
  if (kind === 'elite') return false
  const unknown = dimensionUnknownOf(prog, kind)
  const current = currentLevelOf(prog, kind, targetId)
  return !unknown && current !== null && maxLevel >= 1 && current >= maxLevel
}

interface GoalContext {
  t: BuildCultivateViewsOptions['t']
  entry: CultivateOperatorCatalogEntry | undefined
  prog: Progression | undefined
}

// 已存超限档位（数据波动导致）保留在选项里回显，标记"不会被自动刷取"，
// 不因数据变化删用户配置；未设目标走下拉 placeholder+clear（0 档不再是选项）
const buildOptions = (
  ctx: GoalContext,
  kind: CultivateGoalKind,
  targetId: string,
  savedLevel: number
): CultivateGoalLineOption[] => {
  if (kind === 'elite') {
    const max = ctx.entry?.maxElite ?? 2
    return levelOptionsWithSaved(max, savedLevel || 0).map(level => {
      const key = ELITE_LABEL_KEYS[level]
      return { label: key ? ctx.t(key) : String(level), value: level }
    })
  }
  if (kind === 'skill') {
    const max = ctx.entry?.maxSkillLevel ?? 0
    return levelOptionsWithSaved(max, savedLevel)
      .filter(level => level >= 2)
      .map(level => ({ value: level, label: ctx.t('edit.maaCultivateSkillLevel', { level }) }))
  }
  const options = kind === 'mastery' ? (ctx.entry?.skills ?? []) : (ctx.entry?.modules ?? [])
  const max = options.find(option => option.value === targetId)?.maxLevel ?? 3
  return levelOptionsWithSaved(max, savedLevel).map(level => ({
    value: level,
    label: ctx.t(`edit.maaCultivateGoalLevel${level}`),
  }))
}

const maxLevelOf = (ctx: GoalContext, kind: CultivateGoalKind, targetId: string): number => {
  if (kind === 'elite') return ctx.entry?.maxElite ?? 2
  if (kind === 'skill') return ctx.entry?.maxSkillLevel ?? 0
  const options = kind === 'mastery' ? (ctx.entry?.skills ?? []) : (ctx.entry?.modules ?? [])
  return options.find(option => option.value === targetId)?.maxLevel ?? 3
}

const goalOverLimit = (
  ctx: GoalContext,
  kind: CultivateGoalKind,
  targetId: string,
  savedLevel: number
) => savedLevel > maxLevelOf(ctx, kind, targetId)

// ── 平铺目标行：目录全量（精英化+技能等级+专精+模组），无需"添加目标" ──
// 已存目标不在目录里（目录缺失/上游未收录）时合成孤儿行兜底，
// 保证不留看不见又清不掉的配置
const itemsOf = (row: CultivateTargetRow, ctx: GoalContext, kind: 'mastery' | 'module') => {
  const options = kind === 'mastery' ? (ctx.entry?.skills ?? []) : (ctx.entry?.modules ?? [])
  const known = new Set(options.map(option => option.value))
  const orphans = listGoals(row.rawGoals, kind)
    .filter(goal => !known.has(goal.targetId))
    .map(goal => ({ value: goal.targetId, label: goal.targetId, maxLevel: 3, skillIndex: null }))
  return [...options, ...orphans]
}

const buildLine = (
  ctx: GoalContext,
  kind: CultivateGoalKind,
  targetId: string,
  saved: { toLevel: number; state: string } | undefined,
  label: string,
  options: CultivateGoalLineOption[]
): CultivateGoalLine => {
  const savedLevel = saved?.toLevel ?? 0
  const achieved = achievedOf(ctx.prog, kind, targetId, savedLevel, saved?.state ?? null)
  const levelLabel =
    kind === 'elite'
      ? savedLevel
        ? ELITE_LABEL_KEYS[savedLevel]
          ? ctx.t(ELITE_LABEL_KEYS[savedLevel])
          : String(savedLevel)
        : ''
      : savedLevel >= 1 && savedLevel <= 3
        ? ctx.t(`edit.maaCultivateGoalLevel${savedLevel}`)
        : String(savedLevel)
  return {
    key: kind === 'elite' || kind === 'skill' ? kind : `${kind}-${targetId}`,
    kind,
    targetId,
    label,
    options,
    savedLevel,
    levelLabel,
    overLimit: goalOverLimit(ctx, kind, targetId, savedLevel),
    current: currentTextOf(ctx.t, ctx.prog, kind, targetId),
    currentUnknown:
      kind === 'elite' ? currentUnknownOf(ctx.prog) : dimensionUnknownOf(ctx.prog, kind),
    // 后端未及时打标时按当前练度即时补「已达成」徽标
    state: saved
      ? (goalStateBadge(saved.state) ?? (achieved ? GOAL_STATE_BADGE.achieved : null))
      : null,
    achieved,
  }
}

// 精英化行常驻（达成时静态显示档位，与原头部行为一致），由卡片按 achieved 渲染；
// 无可达档位且未设目标（1-3★/缺数据）时整组隐藏
const eliteGroupOf = (row: CultivateTargetRow, ctx: GoalContext): CultivateGoalGroup | null => {
  const saved = listGoals(row.rawGoals, 'elite')[0]
  const options = buildOptions(ctx, 'elite', '', saved?.toLevel ?? 0)
  if (!options.length && !saved) return null
  return {
    kind: 'elite',
    label: ctx.t('edit.maaCultivateGoalElite'),
    hint: '',
    lines: [buildLine(ctx, 'elite', '', saved, ctx.t('edit.maaCultivateGoalElite'), options)],
  }
}

const skillGroupOf = (row: CultivateTargetRow, ctx: GoalContext): CultivateGoalGroup | null => {
  const maxLevel = ctx.entry?.maxSkillLevel ?? 0
  const saved = listGoals(row.rawGoals, 'skill')[0]
  if (maxLevel <= 1 && !saved) return null
  const line = buildLine(
    ctx,
    'skill',
    '',
    saved,
    ctx.t('edit.maaCultivateGoalSkill'),
    buildOptions(ctx, 'skill', '', saved?.toLevel ?? 0)
  )
  if (line.achieved || maxedOf(ctx.prog, 'skill', '', maxLevel)) return null
  return { kind: 'skill', label: ctx.t('edit.maaCultivateGoalSkill'), hint: '', lines: [line] }
}

const itemGroupOf = (
  row: CultivateTargetRow,
  ctx: GoalContext,
  kind: 'mastery' | 'module'
): CultivateGoalGroup => {
  const lines = itemsOf(row, ctx, kind)
    .map(item => {
      const skillLabel = kind === 'mastery' ? SKILL_LABEL_KEYS[item.skillIndex ?? 0] : null
      const saved = listGoals(row.rawGoals, kind).find(goal => goal.targetId === item.value)
      const label = skillLabel
        ? ctx.t('edit.maaCultivateSkillName', { name: item.label, skill: ctx.t(skillLabel) })
        : item.label
      return {
        item,
        line: buildLine(
          ctx,
          kind,
          item.value,
          saved,
          label,
          buildOptions(ctx, kind, item.value, saved?.toLevel ?? 0)
        ),
      }
    })
    .filter(
      ({ item, line }) => !line.achieved && !maxedOf(ctx.prog, kind, item.value, item.maxLevel)
    )
    .map(({ line }) => line)
  const hint = kind === 'mastery' ? ctx.t('edit.maaCultivateMasterySkillHint') : ''
  return { kind, label: ctx.t(`maaCopilot.kinds.${kind}`), hint, lines }
}

// 头部摘要：全部已存目标的密度概览（折叠时也能一眼看清培养内容）
const summaryOf = (row: CultivateTargetRow, ctx: GoalContext): string => {
  const parts: string[] = []
  const elite = listGoals(row.rawGoals, 'elite')[0]
  if (elite?.toLevel) {
    const key = ELITE_LABEL_KEYS[elite.toLevel]
    parts.push(key ? ctx.t(key) : String(elite.toLevel))
  }
  const skill = listGoals(row.rawGoals, 'skill')[0]
  if (skill?.toLevel) parts.push(`${ctx.t('edit.maaCultivateGoalSkill')} ${skill.toLevel}`)
  const masteryCount = listGoals(row.rawGoals, 'mastery').length
  if (masteryCount) parts.push(ctx.t('maaCopilot.summaryMastery', { count: masteryCount }))
  const moduleCount = listGoals(row.rawGoals, 'module').length
  if (moduleCount) parts.push(ctx.t('maaCopilot.summaryModule', { count: moduleCount }))
  return parts.length ? parts.join(' · ') : ctx.t('maaCopilot.summaryNoGoals')
}

/** 把目标行 + 目录 + 练度快照合成干员卡片视图（达成分组剔除、模组按开关）。 */
export const buildCultivateOperatorViews = (
  options: BuildCultivateViewsOptions
): CultivateOperatorView[] => {
  const { t } = options
  const catalogById = new Map(options.catalog.map(entry => [entry.value, entry]))
  const progressionById = new Map((options.progressions ?? []).map(item => [item.operatorId, item]))
  const views: CultivateOperatorView[] = []
  for (const row of options.rows) {
    const entry = catalogById.get(row.operatorId)
    const ctx: GoalContext = { t, entry, prog: progressionById.get(row.operatorId) }
    const groups = [
      eliteGroupOf(row, ctx),
      skillGroupOf(row, ctx),
      itemGroupOf(row, ctx, 'mastery'),
      ...(options.showModules ? [itemGroupOf(row, ctx, 'module')] : []),
    ].filter((group): group is CultivateGoalGroup => !!group && group.lines.length > 0)
    views.push({
      operatorId: row.operatorId,
      name: entry?.label ?? row.operatorId,
      profession: professionLabel(entry?.profession ?? ''),
      rarity: entry?.rarity ?? 0,
      summary: summaryOf(row, ctx),
      overLimit: groups.some(group => group.lines.some(line => line.overLimit)),
      groups,
    })
  }
  return views
}

/** 已绑定但快照缺专精/模组观测（森空岛拉取失败降级本地档案）时提示用。 */
export const hasUnknownDimensionGoals = (
  rows: CultivateTargetRow[],
  progressions: CultivatePreviewOut['progressions'] | undefined
): boolean => {
  const progressionById = new Map((progressions ?? []).map(item => [item.operatorId, item]))
  return rows.some(row =>
    (['skill', 'mastery', 'module'] as const).some(
      kind =>
        listGoals(row.rawGoals, kind).length > 0 &&
        dimensionUnknownOf(progressionById.get(row.operatorId), kind)
    )
  )
}
