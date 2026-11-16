import type { MaaFWGroupInfo, MaaFWTaskInfo } from '@/types/script'

/** interface 没给分组、或任务没写 group 时归到这一档 */
export const MAAFW_ADD_TASK_UNGROUPED_KEY = '__ungrouped__'

export type MaaFWAddTaskMenuGroup = {
  key: string
  /** 声明过的分组取 label（没有 label 用 name）；没声明的用原名；「未分组」由调用方换成界面文案 */
  label: string
  tasks: MaaFWTaskInfo[]
}

/**
 * 「添加任务」按分组归档候选任务（PI v2 `task.group`）：一个任务写了几个分组就出现在几个分组里，
 * 分组只是归属关系，任务身份仍按 `task.name`。没写分组的归「未分组」。
 *
 * 顺序：顶层 `group` 声明的分组按声明顺序在前，任务里写了、顶层没声明的分组与「未分组」按第一次
 * 出现的顺序跟在后面（没声明的分组照样列出、显示原名，不把任务藏起来）。没有任务的分组不列。
 */
export function buildMaaFWAddTaskMenuGroups(
  tasks: readonly MaaFWTaskInfo[],
  declaredGroups: readonly MaaFWGroupInfo[]
): MaaFWAddTaskMenuGroup[] {
  const groupMap = new Map<string, MaaFWAddTaskMenuGroup>()
  for (const group of declaredGroups) {
    if (groupMap.has(group.name)) continue
    groupMap.set(group.name, { key: group.name, label: group.label || group.name, tasks: [] })
  }
  const ensureGroup = (key: string) => {
    const existing = groupMap.get(key)
    if (existing) return existing
    const group: MaaFWAddTaskMenuGroup = { key, label: key, tasks: [] }
    groupMap.set(key, group)
    return group
  }

  for (const task of tasks) {
    const groupKeys = [...new Set((task.group || []).map(name => name.trim()).filter(Boolean))]
    for (const key of groupKeys.length > 0 ? groupKeys : [MAAFW_ADD_TASK_UNGROUPED_KEY]) {
      ensureGroup(key).tasks.push(task)
    }
  }

  return Array.from(groupMap.values()).filter(group => group.tasks.length > 0)
}

/**
 * 「添加任务」搜索时一个任务能被哪些文字搜到：显示名、任务名（name）与入口名（entry）。
 * 前置任务的 entry 是统一的占位符，不算。各项用换行隔开，关键词不会跨项拼出匹配。
 */
export function maafwAddTaskSearchText(task: MaaFWTaskInfo, displayName: string) {
  const parts = [displayName, task.name]
  if (task.entry && task.entry !== 'MXU_PRETASK') parts.push(task.entry)
  return [...new Set(parts.filter(Boolean))].join('\n')
}

/** 级联菜单搜索：路径上任一项（分组或任务）的搜索文字含关键词即算命中，不分大小写 */
export function matchesMaaFWAddTaskKeyword(
  inputValue: string,
  path: readonly { label?: unknown; searchText?: string }[]
) {
  const keyword = inputValue.trim().toLowerCase()
  if (!keyword) return true
  return path.some(option =>
    String(option.searchText ?? option.label ?? '')
      .toLowerCase()
      .includes(keyword)
  )
}
