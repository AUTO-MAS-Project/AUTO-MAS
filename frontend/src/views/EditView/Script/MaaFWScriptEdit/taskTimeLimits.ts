/**
 * 按任务名单独设置的单任务时限（Run.TaskTimeLimitOverrides）：任务名 → 分钟，0 表示该任务不限；
 * 没有这个键就跟随 Run.TaskTimeLimit。配置里以 JSON 字符串保存。
 */
export type TaskTimeLimitOverrides = Record<string, number>

/** 弹窗里的草稿：null / undefined 表示这一行留空（跟随默认） */
export type TaskTimeLimitDraft = Record<string, number | null | undefined>

export const normalizeTaskLimitMinutes = (value: unknown): number => {
  const minutes = Math.trunc(Number(value))
  return Number.isFinite(minutes) && minutes > 0 ? minutes : 0
}

// ConfigBase 把 JSON 项以字符串保存、读回也是字符串；兼容后端某天直接返回对象、
// 以及分钟被存成字符串的情况。写坏的分钟数按 0（不限）读，与后端换算一致。
export const parseTaskLimitOverrides = (value: unknown): TaskTimeLimitOverrides => {
  let source: unknown = value
  if (typeof source === 'string') {
    if (!source.trim()) return {}
    try {
      source = JSON.parse(source)
    } catch {
      return {}
    }
  }
  if (!source || typeof source !== 'object' || Array.isArray(source)) return {}
  return Object.fromEntries(
    Object.entries(source as Record<string, unknown>)
      .filter(([name]) => Boolean(name))
      .map(([name, minutes]) => [name, normalizeTaskLimitMinutes(minutes)])
  )
}

export const stringifyTaskLimitOverrides = (overrides: TaskTimeLimitOverrides): string =>
  JSON.stringify(overrides)

/** 草稿 → 要保存的覆盖表：留空的行不存键，填了数字（含 0、含等于默认值）就存 */
export const taskLimitDraftToOverrides = (draft: TaskTimeLimitDraft): TaskTimeLimitOverrides =>
  Object.fromEntries(
    Object.entries(draft)
      .filter(
        (entry): entry is [string, number] =>
          Boolean(entry[0]) && typeof entry[1] === 'number' && Number.isFinite(entry[1])
      )
      .map(([name, minutes]) => [name, normalizeTaskLimitMinutes(minutes)])
  )

/** 只留当前 interface 里还有的任务名（读到 interface 后修剪用） */
export const pruneTaskLimitOverrides = (
  overrides: TaskTimeLimitOverrides,
  available: Set<string>
): TaskTimeLimitOverrides =>
  Object.fromEntries(Object.entries(overrides).filter(([name]) => available.has(name)))

/** 摘要用：单独设置了几个任务 */
export const countTaskLimitOverrides = (overrides: TaskTimeLimitOverrides): number =>
  Object.keys(overrides).length
