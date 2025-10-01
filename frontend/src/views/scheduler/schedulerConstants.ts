import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'

// 调度台状态
export type SchedulerStatus = '新建' | '运行' | '结束'

// 新增：任务总览数据类型
export interface User {
  user_id: string
  status: string
  name: string
}

export interface Script {
  script_id: string
  status: string
  name: string
  user_list: User[]
}

// 状态颜色映射
export const TAB_STATUS_COLOR: Record<SchedulerStatus, string> = {
  新建: 'default',
  运行: 'processing',
  结束: 'success',
}

// 队列状态 -> 颜色
export const getQueueStatusColor = (status: string): string => {
  if (/成功|完成|已完成/.test(status)) return 'green'
  if (/失败|错误|异常/.test(status)) return 'red'
  if (/等待|排队|挂起/.test(status)) return 'orange'
  if (/进行|执行|运行/.test(status)) return 'blue'
  return 'default'
}

// 任务模式选项（直接复用后端枚举值）
export const TASK_MODE_OPTIONS = [
  { label: TaskCreateIn.mode.AutoMode, value: TaskCreateIn.mode.AutoMode },
  { label: TaskCreateIn.mode.ManualMode, value: TaskCreateIn.mode.ManualMode },
  { label: TaskCreateIn.mode.SettingScriptMode, value: TaskCreateIn.mode.SettingScriptMode },
]

// 电源操作映射
export const POWER_ACTION_TEXT: Record<PowerIn.signal, string> = {
  [PowerIn.signal.NO_ACTION]: '无动作',
  [PowerIn.signal.KILL_SELF]: '退出软件',
  [PowerIn.signal.SLEEP]: '睡眠',
  [PowerIn.signal.HIBERNATE]: '休眠',
  [PowerIn.signal.SHUTDOWN]: '关机',
  [PowerIn.signal.SHUTDOWN_FORCE]: '强制关机',
}

export const getPowerActionText = (action: PowerIn.signal) => POWER_ACTION_TEXT[action] || '无动作'

// 日志相关
export const LOG_MAX_LENGTH = 2000 // 最多保留日志条数

export type LogType = 'info' | 'error' | 'warning' | 'success'

export interface QueueItem {
  name: string
  status: string
}

export interface LogEntry {
  time: string
  message: string
  type: LogType
  timestamp: number
}

export interface SchedulerTab {
  key: string
  title: string
  closable: boolean
  status: SchedulerStatus
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  websocketId: string | null
  subscriptionId?: string | null
  taskQueue: QueueItem[]
  userQueue: QueueItem[]
  logs: LogEntry[]
  isLogAtBottom: boolean
  lastLogContent: string
  // 新增：任务总览快照（用于路由返回时快速恢复显示）
  overviewData?: Script[]
}

export interface TaskMessage {
  title: string
  content: string
  needInput: boolean
  messageId?: string
  taskId?: string
}
