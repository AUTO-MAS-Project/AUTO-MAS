// 养成目标 JSON 的解析与序列化（PR2 仅精英化目标；结构保留三类 goal，决策 32）

export interface CultivateTargetRow {
  operatorId: string
  toLevel: number
  /** 原始 goals 原样携带：PR2 只编辑 elite 档位，非 elite 目标原样保留 */
  rawGoals: unknown[]
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
      const eliteGoal = item.goals.find(
        (goal: any) => goal?.kind === 'elite' && (goal.to_level === 1 || goal.to_level === 2)
      )
      rows.push({
        operatorId: item.operator_id,
        toLevel: eliteGoal ? eliteGoal.to_level : 2,
        rawGoals: item.goals,
      })
    }
    return rows
  } catch {
    return []
  }
}

/** 在原始 goals 里替换（或追加）elite 档位，其余目标原样保留 */
const upsertEliteGoal = (rawGoals: unknown[], toLevel: number): unknown[] => {
  let replaced = false
  const goals = rawGoals.map(goal => {
    if ((goal as any)?.kind === 'elite') {
      replaced = true
      return { ...(goal as any), to_level: toLevel }
    }
    return goal
  })
  if (!replaced) {
    goals.push({ kind: 'elite', target_id: '', to_level: toLevel, state: 'not_started' })
  }
  return goals
}

/** 序列化回 Task.CultivateTargets JSON（active 状态由后端注入时按缺口刷新） */
export const serializeCultivateTargets = (rows: CultivateTargetRow[]): string =>
  JSON.stringify(
    rows.map(row => ({
      operator_id: row.operatorId,
      goals: upsertEliteGoal(row.rawGoals, row.toLevel),
    }))
  )

/** 追加干员；已在列表中的忽略（保持原有档位不重置） */
export const appendOperator = (
  rows: CultivateTargetRow[],
  operatorId: string,
  rawGoals: unknown[] = []
): CultivateTargetRow[] => {
  if (!operatorId || rows.some(row => row.operatorId === operatorId)) return rows
  return [...rows, { operatorId, toLevel: 2, rawGoals }]
}

export const removeOperator = (
  rows: CultivateTargetRow[],
  operatorId: string
): CultivateTargetRow[] => rows.filter(row => row.operatorId !== operatorId)

export const updateLevel = (
  rows: CultivateTargetRow[],
  operatorId: string,
  toLevel: number
): CultivateTargetRow[] =>
  rows.map(row => (row.operatorId === operatorId ? { ...row, toLevel } : row))
