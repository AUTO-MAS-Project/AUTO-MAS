import { TaskCreateIn } from '@/api/models/TaskCreateIn'

// 调度台状态
// 空闲：未运行；运行：任务进行中；停止中：已下发 stop，等待 WS 完成信号
// 结束：任务完成；失败：任务异常退出或 stop 失败
export type SchedulerTabStatus = '空闲' | '运行' | '停止中' | '结束' | '失败'

// 合法的调度台状态集合，供 addSchedulerTab 等校验使用，避免类型与校验集合不一致
export const SCHEDULER_TAB_STATUS_VALUES: readonly SchedulerTabStatus[] = [
  '空闲',
  '运行',
  '停止中',
  '结束',
  '失败',
] as const

// 判断字符串是否为合法的 SchedulerTabStatus
export const isValidSchedulerTabStatus = (value: string): value is SchedulerTabStatus =>
  (SCHEDULER_TAB_STATUS_VALUES as readonly string[]).includes(value)

// 调度器整体连接状态
export type SchedulerConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'reconnecting'
  | 'failed'
  | 'offline'

export const SCHEDULER_CONNECTION_STATE_LABEL: Record<SchedulerConnectionState, string> = {
  idle: '未连接',
  connecting: '连接中',
  connected: '已连接',
  disconnected: '已断开',
  reconnecting: '重连中',
  failed: '连接失败',
  offline: '离线',
}

export const SCHEDULER_CONNECTION_STATE_COLOR: Record<SchedulerConnectionState, string> = {
  idle: 'default',
  connecting: 'processing',
  connected: 'success',
  disconnected: 'warning',
  reconnecting: 'processing',
  failed: 'error',
  offline: 'default',
}

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
export const TAB_STATUS_COLOR: Record<SchedulerTabStatus, string> = {
  空闲: 'default',
  运行: 'processing',
  停止中: 'warning',
  结束: 'success',
  失败: 'error',
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
  { label: '自动代理', value: TaskCreateIn.mode.AUTO_PROXY },
  { label: '人工排查', value: TaskCreateIn.mode.MANUAL_REVIEW },
  { label: '循环运行', value: TaskCreateIn.mode.CYCLE_RUN },
]

export const getTaskModeOptions = (supportedModes?: string[] | null) => {
  if (!supportedModes) return TASK_MODE_OPTIONS
  return TASK_MODE_OPTIONS.filter(option => supportedModes.includes(option.value))
}

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
  status: SchedulerTabStatus
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  resumeFromScriptId?: string | null
  resumeScriptOptions?: Array<{ label: string; value: string }>
  resumeScriptLoading?: boolean
  websocketId: string | null
  subscriptionIds?: string[]
  /** 旧 sessionStorage 兼容；初始化时会迁移并清空。 */
  subscriptionId?: string | null
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
}

export interface TaskMessage {
  title: string
  content: string
  needInput: boolean
  messageId?: string
  taskId?: string
}
