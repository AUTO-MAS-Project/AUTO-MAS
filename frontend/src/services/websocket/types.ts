// WebSocket 统一消息协议类型
// 与后端 app/core/ws/protocol.py、app/models/schema.py 保持一致

import type { PluginsGetOut } from '@/api/models/PluginsGetOut'

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
export const WS_ID_PLUGIN_SYSTEM = 'PluginSystem'
export const WS_ID_PLUGIN_MARKET = 'PluginMarket'
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

// 应用内弹窗（id=Main）
export const WS_DIALOG_REQUEST = 'dialog.request'
export const WS_DIALOG_RESPONSE = 'dialog.response'

// 更新下载（id=Update）
export const WS_UPDATE_PROGRESS = 'update.progress'
export const WS_UPDATE_COMPLETED = 'update.completed'
export const WS_UPDATE_FAILED = 'update.failed'
export const WS_UPDATE_CANCELLED = 'update.cancelled'

// MaaFW 项目资源更新（id 为脚本 UUID）
export const WS_MAAFW_PROJECT_UPDATE_PROGRESS = 'maafw.project-update.progress'
export const WS_MAAFW_ENV_PREPARE_PROGRESS = 'maafw.env-prepare.progress'

// 插件系统实时消息（id=PluginSystem）
export const WS_PLUGIN_RUNTIME_UPDATED = 'plugin.runtime.updated'
export const WS_PLUGIN_SNAPSHOT_UPDATED = 'plugin.snapshot.updated'
export const WS_PLUGIN_HMR = 'plugin.hmr'

// 插件市场（id=PluginMarket，初始快照使用 HTTP）
export const WS_MARKET_ERROR = 'market.error'
export const WS_PLUGIN_INSTALL_REQUEST = 'plugin.install.request'
export const WS_PLUGIN_INSTALL_PROGRESS = 'plugin.install.progress'
export const WS_PLUGIN_INSTALL_RESULT = 'plugin.install.result'
export const WS_PLUGIN_UNINSTALL_REQUEST = 'plugin.uninstall.request'
export const WS_PLUGIN_UNINSTALL_RESULT = 'plugin.uninstall.result'
export const WS_PLUGIN_INSTALLED_REQUEST = 'plugin.installed.request'
export const WS_PLUGIN_INSTALLED_SYNC = 'plugin.installed.sync'

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

export type WSTaskMode = 'AutoProxy' | 'ManualReview' | 'ScriptConfig'

export interface WSTaskScriptIdentityData {
  scriptId: string
  scriptType: string
}

/** 任务信息快照 (type=task.info.updated) */
export interface WSTaskInfoUpdatedData {
  task_info: WSTaskScriptInfoData[]
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

export type WSMaaFWProjectUpdateStage =
  | 'checking'
  | 'downloading'
  | 'validating'
  | 'extracting'
  | 'switching'
  | 'preparing_environment'
  | 'completed'
  | 'failed'
  | string

/** MaaFW 项目资源更新进度（id 为脚本 UUID）。 */
export interface WSMaaFWProjectUpdateProgressData {
  scriptId?: string
  phase?: string | null
  final?: boolean
  stage: WSMaaFWProjectUpdateStage
  status?: string
  message?: string
  provider_error_code?: number | null
  version?: string | null
  metadata_source?: string | null
  package_source?: string | null
  downloaded_bytes?: number | null
  total_bytes?: number | null
  percent?: number | null
}

/** MaaFW 运行环境准备进度（id 为脚本 UUID）。 */
export interface WSMaaFWEnvPrepareProgressData {
  scriptId?: string
  project_path?: string | null
  stage: string
  status?: string
  message?: string
  percent?: number | null
  downloaded_bytes?: number | null
  total_bytes?: number | null
  logs?: string[]
}

export interface WSPluginRuntimeStateData {
  instance_id: string
  plugin: string
  status: string
  generation: number
  lifecycle_phase: string
  lifecycle_updated_at?: string | null
  reload_count: number
  last_reload_reason?: string | null
  last_reload_at?: string | null
  created_at?: string | null
  discovered_at?: string | null
  loaded_at?: string | null
  activated_at?: string | null
  disposed_at?: string | null
  unloaded_at?: string | null
  last_error?: string | null
  last_error_at?: string | null
}

export interface WSPluginRuntimeUpdatedData {
  event: string
  record: WSPluginRuntimeStateData
}

export type WSPluginSnapshotUpdatedData = PluginsGetOut & {
  reason?: string
}

export interface WSPluginHmrData {
  event: string
  plugin?: string | null
  changed_files: string[]
  action: string
  status: string
  message: string
}

export interface WSPluginPackageRequestData {
  requestId?: string | null
  package: string
}

export interface WSPluginInstallProgressData {
  requestId?: string | null
  status: 'success' | 'error'
  message: string
  package: string
  progress: number
  stage: 'queued' | 'installing' | 'completed'
}

export interface WSPluginOperationResultData {
  requestId?: string | null
  status: 'success' | 'error'
  message: string
  package: string
  success: boolean
}

export interface WSPluginInstalledSyncData {
  requestId?: string | null
  status: 'success' | 'error'
  message: string
  package: string
  installed: boolean
}

export interface WSMarketErrorData {
  requestId?: string | null
  status: 'error'
  message: string
}

export type WSEmptyData = Record<string, never>

/** 已知关键消息的 type → data 映射。动态插件消息回退到 WSJsonObject。 */
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
  [WS_DIALOG_REQUEST]: WSDialogRequestData
  [WS_DIALOG_RESPONSE]: WSDialogResponseData
  [WS_UPDATE_PROGRESS]: WSUpdateProgressData
  [WS_UPDATE_COMPLETED]: WSUpdateCompletedData
  [WS_UPDATE_FAILED]: WSUpdateFailedData
  [WS_UPDATE_CANCELLED]: WSEmptyData
  [WS_MAAFW_PROJECT_UPDATE_PROGRESS]: WSMaaFWProjectUpdateProgressData
  [WS_MAAFW_ENV_PREPARE_PROGRESS]: WSMaaFWEnvPrepareProgressData
  [WS_PLUGIN_RUNTIME_UPDATED]: WSPluginRuntimeUpdatedData
  [WS_PLUGIN_SNAPSHOT_UPDATED]: WSPluginSnapshotUpdatedData
  [WS_PLUGIN_HMR]: WSPluginHmrData
  [WS_PLUGIN_INSTALL_REQUEST]: WSPluginPackageRequestData
  [WS_PLUGIN_INSTALL_PROGRESS]: WSPluginInstallProgressData
  [WS_PLUGIN_INSTALL_RESULT]: WSPluginOperationResultData
  [WS_PLUGIN_UNINSTALL_REQUEST]: WSPluginPackageRequestData
  [WS_PLUGIN_UNINSTALL_RESULT]: WSPluginOperationResultData
  [WS_PLUGIN_INSTALLED_REQUEST]: WSPluginPackageRequestData
  [WS_PLUGIN_INSTALLED_SYNC]: WSPluginInstalledSyncData
  [WS_MARKET_ERROR]: WSMarketErrorData
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
