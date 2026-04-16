import { POWER_SIGNAL, TASK_CREATE_MODE, type PowerSignal, type TaskCreateMode } from '@/api'

export type SchedulerStatus = '空闲' | '运行' | '结束'

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

export const TAB_STATUS_COLOR: Record<SchedulerStatus, string> = {
  空闲: 'default',
  运行: 'processing',
  结束: 'success',
}

export const getQueueStatusColor = (status: string): string => {
  if (/成功|完成|已完成/.test(status)) return 'green'
  if (/失败|错误|异常/.test(status)) return 'red'
  if (/等待|排队|挂起/.test(status)) return 'orange'
  if (/进行|执行|运行/.test(status)) return 'blue'
  return 'default'
}

export const TASK_MODE_OPTIONS = [
  { label: '自动代理', value: TASK_CREATE_MODE.AUTO_PROXY },
  { label: '人工排查', value: TASK_CREATE_MODE.MANUAL_REVIEW },
]

export const POWER_ACTION_TEXT: Record<PowerSignal, string> = {
  [POWER_SIGNAL.NO_ACTION]: '无动作',
  [POWER_SIGNAL.SHUTDOWN]: '关机',
  [POWER_SIGNAL.SHUTDOWN_FORCE]: '强制关机',
  [POWER_SIGNAL.REBOOT]: '重启',
  [POWER_SIGNAL.HIBERNATE]: '休眠',
  [POWER_SIGNAL.SLEEP]: '睡眠',
  [POWER_SIGNAL.KILL_SELF]: '退出软件',
}

export const getPowerActionText = (action: PowerSignal) => POWER_ACTION_TEXT[action] || '无动作'

export const LOG_MAX_LENGTH = 2000

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
  selectedMode: TaskCreateMode | null
  websocketId: string | null
  subscriptionId?: string | null
  taskQueue: QueueItem[]
  userQueue: QueueItem[]
  logs: LogEntry[]
  isLogAtBottom: boolean
  lastLogContent: string
  overviewData?: Script[]
  lastMessageHash?: string
  lastMessageTime?: number
  runningTaskLabel?: string
  runningModeLabel?: string
  logMode?: 'follow' | 'browse'
}

export interface TaskMessage {
  title: string
  content: string
  needInput: boolean
  messageId?: string
  taskId?: string
}
