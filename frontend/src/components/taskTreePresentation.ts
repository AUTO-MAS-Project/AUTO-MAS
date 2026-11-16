export interface TaskTreeScriptState {
  status: string
  user_list: readonly unknown[]
}

/** 空用户表只表示脚本尚未轮到；占位行不是实际账号。 */
export const isWaitingWithoutUsers = (script: TaskTreeScriptState): boolean =>
  script.status === '等待' && script.user_list.length === 0

interface SignatureUser {
  name?: string
  status?: string
}

interface SignatureScript {
  script_id?: string
  name?: string
  status?: string
  userList?: SignatureUser[]
}

/** 任务快照的变化签名：签名不变就不重绘任务树。 */
export const buildTaskInfoSignature = (taskInfo: readonly SignatureScript[]): string =>
  taskInfo
    .map((task, index) => {
      const users = Array.isArray(task.userList)
        ? task.userList.map(user => `${user.name || ''}:${user.status || ''}`).join(',')
        : ''
      return `${task.script_id || index}:${task.name || ''}:${task.status || ''}[${users}]`
    })
    .join('|')
