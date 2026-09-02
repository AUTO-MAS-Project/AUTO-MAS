import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { PowerIn } from '@/api/models/PowerIn'
import type { WSTaskCyclePreviewData } from '@/services/websocket/types'

// 调度台状态
export type SchedulerStatus = '空闲' | '运行' | '结束' | '异常'

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
  空闲: 'default',
  运行: 'processing',
  结束: 'success',
  异常: 'error',
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
  { labelKey: 'scheduler.mode.autoProxy', value: TaskCreateIn.mode.AUTO_PROXY },
  { labelKey: 'scheduler.mode.cycleRun', value: TaskCreateIn.mode.CYCLE_RUN },
]

export const getTaskModeOptions = (supportedModes?: string[] | null) => {
  if (!supportedModes) return TASK_MODE_OPTIONS
  return TASK_MODE_OPTIONS.filter(option => supportedModes.includes(option.value))
}

// 电源操作 -> 词表 key（信号值本身是后端枚举，不动）
export const POWER_ACTION_LABEL_KEY: Record<PowerIn.signal, string> = {
  [PowerIn.signal.NO_ACTION]: 'scheduler.power.noAction',
  [PowerIn.signal.SHUTDOWN]: 'scheduler.power.shutdown',
  [PowerIn.signal.SHUTDOWN_FORCE]: 'scheduler.power.shutdownForce',
  [PowerIn.signal.REBOOT]: 'scheduler.power.reboot',
  [PowerIn.signal.HIBERNATE]: 'scheduler.power.hibernate',
  [PowerIn.signal.SLEEP]: 'scheduler.power.sleep',
  [PowerIn.signal.KILL_SELF]: 'scheduler.power.killSelf',
  [PowerIn.signal.LOGOFF]: 'scheduler.power.logoff',
}
export const getPowerActionLabelKey = (action: PowerIn.signal) =>
  POWER_ACTION_LABEL_KEY[action] || 'scheduler.power.noAction'

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
  resumeFromScriptId?: string | null
  resumeScriptOptions?: Array<{ label: string; value: string }>
  resumeScriptLoading?: boolean
  taskId: string | null
  subscriptionIds?: string[]
  taskQueue: QueueItem[]
  userQueue: QueueItem[]
  logs: LogEntry[]
  isLogAtBottom: boolean
  lastLogContent: string
  // 新增：任务总览快照（用于路由返回时快速恢复显示）
  overviewData?: Script[]
  // 新增：消息去重相关字段
  lastMessageHash?: string
  lastMessageTime?: number
  // 新增：运行时任务/模式文本快照（用于持久化显示）
  runningTaskLabel?: string
  runningModeLabel?: string
  // 新增：日志显示模式
  logMode?: 'follow' | 'browse'
  // 所选任务是否为循环队列，决定是否给出「循环运行」模式
  isCycleQueue?: boolean
  // 循环运行的待运行条目预览
  cycleNextList?: WSTaskCyclePreviewData[]
}
