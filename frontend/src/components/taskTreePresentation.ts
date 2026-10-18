export interface TaskTreeScriptState {
  status: string
  user_list: readonly unknown[]
}

/** 空用户表只表示脚本尚未轮到；占位行不是实际账号。 */
export const isWaitingWithoutUsers = (script: TaskTreeScriptState): boolean =>
  script.status === '等待' && script.user_list.length === 0
