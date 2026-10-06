// 用户页任务队列的自定义模板：存在脚本级 `Task.Templates`（JSON 文本），同一脚本的用户共用。
// 每项 `{ name, snapshot }`，快照形状同用户的 Task.TaskSnapshot，但不含虚影、受管任务与密码字段；
// 名称在脚本内唯一（去首尾空格后比较）。这里全是纯函数：解析、校验名称、生成要存的快照与增删改。

import type { MaaFWTaskOptionValue, MaaFWTaskSnapshot } from '@/types/script'
import { stripMaaFWPasswordValues, type MaaFWPasswordFields } from './maafwQueueSource'

export type MaaFWQueueTemplate = {
  name: string
  snapshot: MaaFWTaskSnapshot
}

/** 名称为什么不能用：去首尾空格后为空 / 本脚本已有同名模板 */
export type MaaFWQueueTemplateNameProblem = 'empty' | 'duplicate' | null

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const parseSnapshot = (raw: unknown): MaaFWTaskSnapshot => {
  const value = isRecord(raw) ? raw : {}
  const taskOrder = Array.isArray(value.taskOrder)
    ? value.taskOrder.filter((taskId): taskId is string => typeof taskId === 'string')
    : []
  return {
    taskOrder,
    taskChecked: isRecord(value.taskChecked) ? (value.taskChecked as Record<string, boolean>) : {},
    taskOptions: isRecord(value.taskOptions)
      ? (value.taskOptions as Record<string, Record<string, MaaFWTaskOptionValue>>)
      : {},
  }
}

/**
 * 读脚本配置里的模板列表：JSON 文本或已解析的数组都收；坏掉的项（没名字、名字重复）跳过，
 * 重名时留先出现的那份。
 */
export const parseMaaFWQueueTemplates = (raw: unknown): MaaFWQueueTemplate[] => {
  let value = raw
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value)
    } catch {
      return []
    }
  }
  if (!Array.isArray(value)) return []
  const templates: MaaFWQueueTemplate[] = []
  const names = new Set<string>()
  for (const item of value) {
    if (!isRecord(item) || typeof item.name !== 'string') continue
    const name = item.name.trim()
    if (!name || names.has(name)) continue
    names.add(name)
    templates.push({ name, snapshot: parseSnapshot(item.snapshot) })
  }
  return templates
}

/** 校验模板名称；`ignoreName` 是重命名时的原名（改回原名不算重名） */
export const checkMaaFWQueueTemplateName = (
  name: string,
  existingNames: readonly string[],
  ignoreName?: string
): MaaFWQueueTemplateNameProblem => {
  const trimmed = name.trim()
  if (!trimmed) return 'empty'
  if (trimmed !== ignoreName && existingNames.includes(trimmed)) return 'duplicate'
  return null
}

/**
 * 把当前队列存成模板快照：只收调用方给的项（已去掉虚影与受管任务），选项拷一份并去掉密码字段的值。
 */
export const buildMaaFWQueueTemplateSnapshot = (
  entries: readonly { id: string }[],
  taskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>,
  passwordFields: MaaFWPasswordFields
): MaaFWTaskSnapshot => {
  const taskOrder = entries
    .map(entry => entry.id)
    .filter((taskId, index, values) => values.indexOf(taskId) === index)
  const picked = Object.fromEntries(
    taskOrder.filter(taskId => taskOptions[taskId]).map(taskId => [taskId, taskOptions[taskId]])
  )
  return {
    taskOrder,
    taskChecked: Object.fromEntries(taskOrder.map(taskId => [taskId, true])),
    taskOptions: JSON.parse(JSON.stringify(stripMaaFWPasswordValues(picked, passwordFields))),
  }
}

/** 加一个模板（放在最后）；名称不能用时返回 null，不覆盖同名 */
export const addMaaFWQueueTemplate = (
  templates: readonly MaaFWQueueTemplate[],
  template: MaaFWQueueTemplate
): MaaFWQueueTemplate[] | null => {
  const name = template.name.trim()
  const names = templates.map(item => item.name)
  if (checkMaaFWQueueTemplateName(name, names)) return null
  return [...templates, { ...template, name }]
}

/** 重命名；原模板不在了或新名称不能用时返回 null */
export const renameMaaFWQueueTemplate = (
  templates: readonly MaaFWQueueTemplate[],
  name: string,
  nextName: string
): MaaFWQueueTemplate[] | null => {
  if (!templates.some(item => item.name === name)) return null
  const names = templates.map(item => item.name)
  if (checkMaaFWQueueTemplateName(nextName, names, name)) return null
  const trimmed = nextName.trim()
  return templates.map(item => (item.name === name ? { ...item, name: trimmed } : item))
}

/** 删除一个模板（不在就原样返回） */
export const removeMaaFWQueueTemplate = (
  templates: readonly MaaFWQueueTemplate[],
  name: string
): MaaFWQueueTemplate[] => templates.filter(item => item.name !== name)
