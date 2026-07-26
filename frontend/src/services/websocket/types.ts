// WebSocket 统一消息协议类型
// 与后端 app/core/ws/protocol.py、app/models/schema.py 保持一致

// ==================== 信封 ====================

/** 主 WebSocket 统一消息信封，前后端均按 id + type 路由 */
export interface WSEnvelope<T = Record<string, unknown>> {
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
export const WS_ID_PLUGIN_SYSTEM = 'PluginSystem'
export const WS_ID_PLUGIN_MARKET = 'PluginMarket'
export const WS_ID_EMULATOR_MANAGER = 'EmulatorManager'
export const WS_ID_ARKNIGHTS_TOOLKIT = 'ArknightsPCToolkit'

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

// 应用内弹窗（id=Main）
export const WS_DIALOG_REQUEST = 'dialog.request'
export const WS_DIALOG_RESPONSE = 'dialog.response'

// 更新下载（id=Update）
export const WS_UPDATE_PROGRESS = 'update.progress'
export const WS_UPDATE_COMPLETED = 'update.completed'
export const WS_UPDATE_VERIFYING = 'update.verifying'
export const WS_UPDATE_INSTALLING = 'update.installing'
export const WS_UPDATE_FAILED = 'update.failed'
export const WS_UPDATE_CANCELLED = 'update.cancelled'

// 插件系统实时消息（id=PluginSystem）
export const WS_PLUGIN_RUNTIME_UPDATED = 'plugin.runtime.updated'
export const WS_PLUGIN_SNAPSHOT_UPDATED = 'plugin.snapshot.updated'
export const WS_PLUGIN_HMR = 'plugin.hmr'

// 状态快照（id=Main）；后端在每次主连接建立后主动推送 snapshot.response，
// 也支持前端主动发送 snapshot.request 拉取（app/core/ws/dispatcher.py）
export const WS_SNAPSHOT_REQUEST = 'snapshot.request'
export const WS_SNAPSHOT_RESPONSE = 'snapshot.response'

// 模拟器异步操作结果（id=EmulatorManager）
export const WS_EMULATOR_NOTICE = 'emulator.notice'

// MaaFW 工具箱异步通知（id=ArknightsPCToolkit）；payload 复用 WSTaskNoticeData，
// 如 ArknightsPC 工具连接明日方舟窗口失败（app/MaaFW/ArknightWin32.py）
export const WS_TOOLKIT_NOTICE = 'toolkit.notice'

// 插件市场（id=PluginMarket）
export const WS_MARKET_SNAPSHOT_REQUEST = 'market.snapshot.request'
export const WS_MARKET_SNAPSHOT_RESPONSE = 'market.snapshot.response'
export const WS_MARKET_ERROR = 'market.error'
export const WS_PLUGIN_INSTALL_REQUEST = 'plugin.install.request'
export const WS_PLUGIN_INSTALL_PROGRESS = 'plugin.install.progress'
export const WS_PLUGIN_INSTALL_RESULT = 'plugin.install.result'
export const WS_PLUGIN_UNINSTALL_REQUEST = 'plugin.uninstall.request'
export const WS_PLUGIN_UNINSTALL_RESULT = 'plugin.uninstall.result'
export const WS_PLUGIN_INSTALLED_REQUEST = 'plugin.installed.request'
export const WS_PLUGIN_INSTALLED_SYNC = 'plugin.installed.sync'

// ==================== 关键消息数据类型 ====================

/** 任务提示消息数据 (type=task.notice) */
export interface WSTaskNoticeData {
  level: 'info' | 'warning' | 'error'
  message: string
  /** 异步业务操作追踪 ID（当前由 emulator.notice 使用） */
  operationId?: string | null
}

export interface WSCyclePreviewItem {
  queueItemId: string
  scriptId: string
  scriptName: string
  nextRunAt: string
  isDue: boolean
  isRunning: boolean
}

/** 任务状态更新数据 (type=task.info.updated) */
export interface WSTaskInfoUpdatedData {
  task_info: Record<string, unknown>[]
  cycleQueueId?: string | null
  cycleNextRunAt?: string | null
  cycleWaitingReason?: string | null
  cycleCurrentItemId?: string | null
  cycleNext?: WSCyclePreviewItem | null
  cycleNextList?: WSCyclePreviewItem[]
}

/** 任务完成消息数据 (type=task.completed) */
export interface WSTaskCompletedData {
  result: string
  task_info: Record<string, unknown>[]
}

/** 新任务创建通知数据 (id=TaskManager, type=task.created) */
export interface WSTaskCreatedData {
  taskId: string
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

/** 应用内弹窗请求数据 (id=Main, type=dialog.request) */
export interface WSDialogRequestData {
  requestId: string
  taskId?: string | null
  title: string
  message: string
  options: string[]
}

/** 应用内弹窗响应数据 (id=Main, type=dialog.response) */
export interface WSDialogResponseData {
  requestId: string
  choice: boolean
}

/**
 * 状态快照数据 (id=Main, type=snapshot.response)。
 * states 为 type -> id -> data 的可合并状态集合（对应后端
 * app/core/ws/publisher.py 的 MergeableStateCache.snapshot()）。
 */
export interface WSSnapshotResponseData {
  revision: number
  states: Record<string, Record<string, Record<string, unknown>>>
}

/** 更新下载进度数据 (id=Update, type=update.progress) */
export interface WSUpdateProgressData {
  downloaded_size: number
  file_size: number
  speed: number
  source: string
}

// ==================== 连接层类型 ====================

/**
 * 连接状态机。
 *
 * - `suspended`：协议级终止性关闭（1009 消息超限 / 4001 连接被替换）后的可恢复挂起态。
 *   停止**自动**重连以避免连接风暴，但用户显式发起的恢复（手动重连 / 重启后端 /
 *   启动重试）仍可通过 `connect({ force: true })` 重新建连。
 * - `closed`：应用退出 `shutdown()` 的不可恢复终态，任何 connect 请求都被拒绝。
 */
export type WSConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'suspended'
  | 'closed'

/** 订阅键：优先按 id + type 精确路由；单字段和空键仅供迁移期兼容。 */
export interface WSSubscriptionKey {
  id?: string
  type?: string
}

/** 订阅处理器 */
export type WSMessageHandler = (message: WSEnvelope) => void

/** 断开事件（通知生命周期协调器） */
export interface WSDisconnectEvent {
  code: number
  reason: string
}
