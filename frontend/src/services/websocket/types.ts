// WebSocket 统一消息协议类型
// 与后端 app/core/ws/protocol.py、app/models/schema.py 保持一致

// ==================== 信封 ====================

export type WSJsonValue = string | number | boolean | null | WSJsonValue[] | WSJsonObject
export interface WSJsonObject {
  [key: string]: WSJsonValue
}

/** 主 WebSocket 统一消息信封，前后端均按 id + type 路由 */
export interface WSEnvelope<T = WSJsonObject> {
  /** 路由ID，标识任务、请求或业务会话，如 Main、TaskManager、任务UUID */
  id: string
  /** 消息类别，点分小写命名，如 task.info.updated、backend.shutdown.ready */
  type: string
  /** 消息数据 */
  data: T
}

// ==================== 固定路由 ID ====================

export const WS_ID_MAIN = 'Main'
export const WS_ID_TASK_MANAGER = 'TaskManager'
export const WS_ID_UPDATE = 'Update'
export const WS_ID_GAME_SIGN = 'GameSign'
export const WS_ID_EMULATOR_MANAGER = 'EmulatorManager'
export const WS_ID_ARKNIGHTS_PC_TOOLKIT = 'ArknightsPCToolkit'

// ==================== 消息类别 ====================

// 任务消息（id 为任务 UUID）
export const WS_TASK_INFO_UPDATED = 'task.info.updated'
export const WS_TASK_LOG_UPDATED = 'task.log.updated'
export const WS_TASK_NOTICE = 'task.notice'
export const WS_TASK_COMPLETED = 'task.completed'

// 任务创建通知（id=TaskManager）
export const WS_TASK_CREATED = 'task.created'

// 应用生命周期与电源（id=Main）
export const WS_BACKEND_SHUTDOWN_READY = 'backend.shutdown.ready'
export const WS_FRONTEND_CLOSE_REQUESTED = 'frontend.close.requested'
export const WS_POWER_COUNTDOWN_UPDATED = 'power.countdown.updated'
export const WS_POWER_COUNTDOWN_CANCELLED = 'power.countdown.cancelled'
export const WS_POWER_SIGN_UPDATED = 'power.sign.updated'

// 更新下载（id=Update）
export const WS_UPDATE_PROGRESS = 'update.progress'
export const WS_UPDATE_COMPLETED = 'update.completed'
export const WS_UPDATE_FAILED = 'update.failed'
export const WS_UPDATE_CANCELLED = 'update.cancelled'

// MFW 运行环境准备（id=<scriptId>）
export const WS_MAAFW_ENV_PREPARE_PROGRESS = 'maafw.env-prepare.progress'

// 游戏签到结果（id=GameSign）
export const WS_GAMESIGN_RESULT_UPDATED = 'gamesign.result.updated'

// 通用错误提示（id=EmulatorManager / ArknightsPCToolkit）
export const WS_EMULATOR_NOTICE = 'emulator.notice'
export const WS_TOOLKIT_NOTICE = 'toolkit.notice'

// ==================== 关键消息数据类型 ====================

/** 任务提示消息数据 (type=task.notice) */
export interface WSTaskNoticeData {
  level: 'info' | 'warning' | 'error'
  message: string
}

export interface WSTaskUserInfoData {
  user_id: string
  name: string
  status: string
}

export interface WSTaskScriptInfoData {
  script_id: string
  name: string
  status: string
  userList: WSTaskUserInfoData[]
}

export type WSTaskMode = 'AutoProxy' | 'ScriptConfig' | 'Update' | 'CycleRun'

export interface WSTaskScriptIdentityData {
  scriptId: string
  scriptType: string
}

/** 循环运行的一个待运行条目 */
export interface WSTaskCyclePreviewData {
  queueItemId: string
  scriptId: string
  scriptName: string
  nextRunAt: string
  isDue: boolean
  isRunning: boolean
}

/** 任务信息快照 (type=task.info.updated) */
export interface WSTaskInfoUpdatedData {
  task_info: WSTaskScriptInfoData[]
  /** 循环运行的待运行条目，仅循环任务非空 */
  cycleNextList?: WSTaskCyclePreviewData[]
}

/** 当前任务日志 (type=task.log.updated) */
export interface WSTaskLogUpdatedData {
  log: string
}

/** 任务完成消息数据 (type=task.completed) */
export interface WSTaskCompletedData {
  result: string
  outcome: 'success' | 'error' | 'cancelled'
  error?: string | null
  task_info: WSTaskScriptInfoData[]
}

/** 新任务创建通知数据 (id=TaskManager, type=task.created) */
export interface WSTaskCreatedData {
  taskId: string
  mode: WSTaskMode
  scripts: WSTaskScriptIdentityData[]
  queueId?: string | null
  taskName?: string | null
  taskType?: string | null
}

/** 电源倒计时更新数据 (id=Main, type=power.countdown.updated) */
export interface WSPowerCountdownData {
  operation: string
  remaining: number
}

/** 电源标志更新数据 (id=Main, type=power.sign.updated) */
export interface WSPowerSignData {
  signal: string
}

/** MFW 运行环境准备进度 (id=<scriptId>, type=maafw.env-prepare.progress) */
export interface WSMaaFWEnvPrepareProgressData {
  /** resolving / creating_runtime / installing_runtime / runtime_ready / reused / log / ready / failed */
  stage: string
  /** running / success / failed */
  status: string
  message: string
  percent?: number | null
  /** 本次事件附带的新增日志行 */
  log?: string | null
}

/** 更新下载进度数据 (id=Update, type=update.progress) */
export interface WSUpdateProgressData {
  downloaded_size: number
  file_size: number
  speed: number
  source: string
}

export interface WSUpdateCompletedData {
  file: string
}

export interface WSUpdateFailedData {
  message: string
}

/** 游戏签到结果广播数据 (id=GameSign, type=gamesign.result.updated) */
export interface WSGameSignResultData {
  /** JSON 序列化的签到结果数据，与 GET 快照接口返回一致 */
  result: string
}

export type WSEmptyData = Record<string, never>

/** 已知关键消息的 type → data 映射。未知消息回退到 WSJsonObject。 */
export interface WSMessageDataMap {
  [WS_TASK_INFO_UPDATED]: WSTaskInfoUpdatedData
  [WS_TASK_LOG_UPDATED]: WSTaskLogUpdatedData
  [WS_TASK_NOTICE]: WSTaskNoticeData
  [WS_TASK_COMPLETED]: WSTaskCompletedData
  [WS_TASK_CREATED]: WSTaskCreatedData
  [WS_BACKEND_SHUTDOWN_READY]: WSEmptyData
  [WS_FRONTEND_CLOSE_REQUESTED]: WSEmptyData
  [WS_POWER_COUNTDOWN_UPDATED]: WSPowerCountdownData
  [WS_POWER_COUNTDOWN_CANCELLED]: WSEmptyData
  [WS_POWER_SIGN_UPDATED]: WSPowerSignData
  [WS_UPDATE_PROGRESS]: WSUpdateProgressData
  [WS_UPDATE_COMPLETED]: WSUpdateCompletedData
  [WS_UPDATE_FAILED]: WSUpdateFailedData
  [WS_UPDATE_CANCELLED]: WSEmptyData
  [WS_MAAFW_ENV_PREPARE_PROGRESS]: WSMaaFWEnvPrepareProgressData
  [WS_GAMESIGN_RESULT_UPDATED]: WSGameSignResultData
  [WS_EMULATOR_NOTICE]: WSTaskNoticeData
  [WS_TOOLKIT_NOTICE]: WSTaskNoticeData
}

export type WSKnownMessageType = keyof WSMessageDataMap
export type WSDataForType<TType extends string> = TType extends WSKnownMessageType
  ? WSMessageDataMap[TType]
  : WSJsonObject

// ==================== 连接层类型 ====================

/** 连接状态机 */
export type WSConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

/** 订阅键：只允许按 id + type 精确路由。 */
export interface WSSubscriptionKey<TType extends string = string> {
  id: string
  type: TType
}

/** 订阅处理器 */
export type WSMessageHandler<TData = WSJsonObject> = (
  message: WSEnvelope<TData>
) => void | Promise<void>

/** 断开事件（通知生命周期协调器） */
export interface WSDisconnectEvent {
  code: number
  reason: string
}
