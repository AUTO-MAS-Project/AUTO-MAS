// 养成目标 JSON 的解析与序列化（R4 起支持精英化/专精/模组三类 goal 编辑）

export type CultivateGoalKind = 'elite' | 'mastery' | 'module'

export interface CultivateTargetRow {
  operatorId: string
  /** 原始 goals（含 state），精英化/专精/模组均按 kind 过滤展示与编辑 */
  rawGoals: unknown[]
}

export interface CultivateGoalView {
  kind: CultivateGoalKind
  targetId: string
  toLevel: number
  state: string
}

/** 专精/模组目标选项（后端 MaaCultivateGoalOptionItem；编辑器与流水线区共用） */
export interface CultivateGoalOption {
  label: string
  value: string
  maxLevel: number
}

/** 干员目录条目（后端 MaaCultivateOperatorOptionItem 归一化形状，三处消费共用） */
export interface CultivateOperatorCatalogEntry {
  value: string
  label: string
  rarity: number
  profession: string
  /** 精英化可达档位上限；0 = 该干员无精英化消耗数据（决策 40） */
  maxElite: number
  /** maxElite=0 时为真表示上游数据缺失（区别于 1/2/3★ 结构上不适用） */
  dataMissing: boolean
  skills: CultivateGoalOption[]
  modules: CultivateGoalOption[]
}

/** 把 Task.CultivateTargets JSON 解析为编辑行；坏条目跳过，非法 JSON 返回空 */
export const parseCultivateTargets = (
  plansJson: string | undefined | null
): CultivateTargetRow[] => {
  try {
    const parsed = JSON.parse(plansJson || '[]')
    if (!Array.isArray(parsed)) return []
    const rows: CultivateTargetRow[] = []
    for (const item of parsed) {
      if (typeof item?.operator_id !== 'string' || item.operator_id === '') continue
      if (!Array.isArray(item.goals)) continue
      // 同 (kind, target_id) 只留首条：手改配置可能造出重复 goal，重复条目
      // 在编辑器里不可见却在保存时原样带回（与后端 parse_cultivate_targets 同口径）
      const seen = new Set<string>()
      const goals = item.goals.filter((goal: any) => {
        if (goal?.kind !== 'elite' && goal?.kind !== 'mastery' && goal?.kind !== 'module') {
          return true
        }
        const key = `${goal.kind}|${String(goal.target_id ?? '')}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      rows.push({ operatorId: item.operator_id, rawGoals: goals })
    }
    return rows
  } catch {
    return []
  }
}

/** 序列化回 Task.CultivateTargets JSON（state 由后端注入时按缺口/达成刷新） */
export const serializeCultivateTargets = (rows: CultivateTargetRow[]): string =>
  JSON.stringify(rows.map(row => ({ operator_id: row.operatorId, goals: row.rawGoals })))

/** 按 kind 取目标视图（elite 的 targetId 恒为空串） */
export const listGoals = (rawGoals: unknown[], kind: CultivateGoalKind): CultivateGoalView[] =>
  rawGoals
    .map((goal: any) =>
      goal?.kind === kind
        ? {
            kind,
            targetId: String(goal.target_id ?? ''),
            toLevel: Number(goal.to_level) || 0,
            state: String(goal.state ?? 'not_started'),
          }
        : null
    )
    .filter((goal): goal is CultivateGoalView => goal !== null)

/** 新增或更新目标；已存在时只改档位并保留 state（避免把刷取中重置掉） */
export const upsertGoal = (
  rawGoals: unknown[],
  goal: { kind: CultivateGoalKind; targetId: string; toLevel: number }
): unknown[] => {
  const targetId = goal.kind === 'elite' ? '' : goal.targetId
  let replaced = false
  const goals = rawGoals.map(existing => {
    const g = existing as any
    if (g?.kind === goal.kind && String(g.target_id ?? '') === targetId) {
      replaced = true
      return { ...g, to_level: goal.toLevel }
    }
    return existing
  })
  if (!replaced) {
    goals.push({
      kind: goal.kind,
      target_id: targetId,
      to_level: goal.toLevel,
      state: 'not_started',
    })
  }
  return goals
}

/** 移除目标（kind+targetId 定位；elite 的 targetId 恒为空串） */
export const removeGoal = (
  rawGoals: unknown[],
  kind: CultivateGoalKind,
  targetId: string
): unknown[] => {
  const id = kind === 'elite' ? '' : targetId
  return rawGoals.filter(
    (goal: any) => !(goal?.kind === kind && String(goal.target_id ?? '') === id)
  )
}

/** 设置精英化目标档位；null = 不设精英化目标（仅专精/模组） */
export const setEliteLevel = (rawGoals: unknown[], toLevel: number | null): unknown[] =>
  toLevel == null
    ? removeGoal(rawGoals, 'elite', '')
    : upsertGoal(rawGoals, { kind: 'elite', targetId: '', toLevel })

/** 可达档位列表 1..maxLevel；maxLevel<=0（无消耗数据）时为空（决策 40） */
export const tierValues = (maxLevel: number): number[] => {
  const max = Math.floor(Number(maxLevel) || 0)
  return max > 0 ? Array.from({ length: max }, (_, index) => index + 1) : []
}

/**
 * 下拉可选档位 = 可达档位 ∪ 已存档位。
 * 已存档位超出可达上限（上游数据波动）时保留在选项里回显，绝不静默改用户配置。
 */
export const levelOptionsWithSaved = (maxLevel: number, savedLevel: number): number[] => {
  const levels = new Set<number>(tierValues(maxLevel))
  const saved = Math.floor(Number(savedLevel) || 0)
  if (saved > 0) levels.add(saved)
  return [...levels].sort((a, b) => a - b)
}

/** 追加干员；已在列表中的忽略。新行默认带"精2"目标（最常见诉求，受可达上限约束） */
export const appendOperator = (
  rows: CultivateTargetRow[],
  operatorId: string,
  rawGoals: unknown[] = [],
  maxElite = 2
): CultivateTargetRow[] => {
  if (!operatorId || rows.some(row => row.operatorId === operatorId)) return rows
  // 可达上限低于 2（低星/上游缺数据）时不预置精英化目标：设了也刷不到
  const level = Math.min(2, Math.max(0, Math.floor(Number(maxElite) || 0)))
  const goals =
    level > 0 ? upsertGoal(rawGoals, { kind: 'elite', targetId: '', toLevel: level }) : rawGoals
  return [...rows, { operatorId, rawGoals: goals }]
}

export const removeOperator = (
  rows: CultivateTargetRow[],
  operatorId: string
): CultivateTargetRow[] => rows.filter(row => row.operatorId !== operatorId)
