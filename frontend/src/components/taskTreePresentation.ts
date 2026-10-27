export interface TaskTreeScriptState {
  status: string
  user_list: readonly unknown[]
}

/** 空用户表只表示脚本尚未轮到；占位行不是实际账号。 */
export const isWaitingWithoutUsers = (script: TaskTreeScriptState): boolean =>
  script.status === '等待' && script.user_list.length === 0

/** 用户正在跑的任务进度（目前只有 MFW 给），与后端 WSTaskUserProgressData 同形。 */
export interface TaskTreeUserProgress {
  current: number
  total: number
  task: string
}

/** 调度台用户行「3/12 · 当前任务」的插值参数；没有进度或数字不成立时不显示。 */
export const userProgressParams = (
  progress: TaskTreeUserProgress | null | undefined
): TaskTreeUserProgress | null => {
  if (!progress) return null
  const { current, total, task } = progress
  if (!Number.isInteger(current) || !Number.isInteger(total) || current < 1 || total < 1) {
    return null
  }
  return { current: Math.min(current, total), total, task: task.trim() }
}

interface SignatureUser {
  name?: string
  status?: string
  progress?: TaskTreeUserProgress | null
}

interface SignatureScript {
  script_id?: string
  name?: string
  status?: string
  userList?: SignatureUser[]
}

/**
 * 任务快照的变化签名：签名不变就不重绘任务树。
 * 进度要算进去，否则 MFW 用户换任务时状态没变、界面会停在上一个任务。
 */
export const buildTaskInfoSignature = (taskInfo: readonly SignatureScript[]): string =>
  taskInfo
    .map((task, index) => {
      const users = Array.isArray(task.userList)
        ? task.userList
            .map(user => {
              const progress = user.progress
                ? `${user.progress.current}/${user.progress.total}/${user.progress.task}`
                : ''
              return `${user.name || ''}:${user.status || ''}:${progress}`
            })
            .join(',')
        : ''
      return `${task.script_id || index}:${task.name || ''}:${task.status || ''}[${users}]`
    })
    .join('|')
