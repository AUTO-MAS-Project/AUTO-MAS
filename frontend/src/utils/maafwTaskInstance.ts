/**
 * MFW 专项任务队列的「任务实例 id」。
 *
 * 同一个任务可以被重复加入队列，队列元素因此是实例 id 而不是任务名：
 * 首份沿用裸任务名，第二份起是 `<任务名>__MAS_DUP__<随机后缀>`，
 * 旧配置里的任务名天然就是首份，无需迁移。
 *
 * 分隔符需与后端 `automas_maafw_interface/models.py` 的
 * `DUPLICATE_TASK_SUFFIX_SEPARATOR` 保持一致。
 */
export const MAAFW_DUPLICATE_TASK_SEPARATOR = '__MAS_DUP__'

type TaskNameLookup = { has: (value: string) => boolean }

/**
 * 把任务实例 id 解析回 ProjectInterface 里的任务名。
 * 任务名自身含分隔符时按原名解析，不会被误判成副本。
 */
export const resolveMaaFWTaskName = (taskId: string, validTaskNames: TaskNameLookup) => {
  if (validTaskNames.has(taskId)) return taskId
  const separatorIndex = taskId.lastIndexOf(MAAFW_DUPLICATE_TASK_SEPARATOR)
  if (separatorIndex <= 0) return taskId
  const taskName = taskId.slice(0, separatorIndex)
  return validTaskNames.has(taskName) ? taskName : taskId
}

/** 生成一个未被占用的任务实例 id：首份用裸任务名，其后是 `<任务名>__MAS_DUP__<随机后缀>`。 */
export const buildMaaFWTaskInstanceId = (taskName: string, usedTaskIds: TaskNameLookup) => {
  if (!usedTaskIds.has(taskName)) return taskName
  let candidate = ''
  do {
    const suffix = Math.random().toString(36).slice(2, 10)
    candidate = `${taskName}${MAAFW_DUPLICATE_TASK_SEPARATOR}${suffix}`
  } while (usedTaskIds.has(candidate))
  return candidate
}
