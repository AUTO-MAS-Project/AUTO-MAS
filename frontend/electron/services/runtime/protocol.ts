/**
 * AUTO-MAS Runtime NDJSON 协议（protocol v1）类型定义
 *
 * 字段名与取值以 AUTO-MAS-Runtime 的 `internal/protocol/*.go` 为准，
 * 语义参照 `doc/架构设计.md`「NDJSON 公共结构」至「错误码全集」各节。
 *
 * 使用约定：
 * - 一律按 `type`/`code`/`success`/`stage`/`status` 等机器字段判断业务状态，
 *   `message` 只用于展示，禁止解析中文文案做判定；
 * - 未知的 stage、state、capability、remediation 与 code 必须忽略而不是拒绝整条协议，
 *   因此这些字面量类型都是「开放联合」：既保留字面量补全，也接受未来新增的字符串。
 */

/** 本客户端实现并要求的协议版本。 */
export const RUNTIME_PROTOCOL_VERSION = 1

/** 开放字面量联合：保留已知取值的补全，同时接受协议后续追加的新取值。 */
type OpenUnion<T extends string> = T | (string & Record<never, never>)

// ==================== 事件类型 ====================

/** 事件判别字段 `type` 的全集。 */
export type RuntimeEventType =
  | 'hello'
  | 'progress'
  | 'state'
  | 'log'
  | 'warning'
  | 'error'
  | 'result'

// ==================== 阶段与状态字面量 ====================

/** 协议 v1 的稳定 stage 标识（values.go: Stage）。 */
export type RuntimeKnownStage =
  | 'runtime.handshake'
  | 'doctor'
  | 'bootstrap'
  | 'repair'
  | 'cleanup'
  | 'uv.check'
  | 'uv.download'
  | 'uv.verify'
  | 'workspace.check'
  | 'workspace.clone'
  | 'workspace.verify'
  | 'workspace.swap'
  | 'workspace.cleanup'
  | 'python.check'
  | 'python.install'
  | 'dependencies.check'
  | 'dependencies.sync'
  | 'dependencies.rebuild'
  | 'backend.spawn'
  | 'backend.health'
  | 'backend.run'
  | 'backend.restart'
  | 'backend.shutdown'
  | 'backend.cleanup'

export type RuntimeStage = OpenUnion<RuntimeKnownStage>

export const RUNTIME_STAGES: readonly RuntimeKnownStage[] = [
  'runtime.handshake',
  'doctor',
  'bootstrap',
  'repair',
  'cleanup',
  'uv.check',
  'uv.download',
  'uv.verify',
  'workspace.check',
  'workspace.clone',
  'workspace.verify',
  'workspace.swap',
  'workspace.cleanup',
  'python.check',
  'python.install',
  'dependencies.check',
  'dependencies.sync',
  'dependencies.rebuild',
  'backend.spawn',
  'backend.health',
  'backend.run',
  'backend.restart',
  'backend.shutdown',
  'backend.cleanup',
]

/** `progress.status` 的全集（values.go: ProgressStatus）。 */
export type RuntimeKnownProgressStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'skipped'
  | 'failed'
  | 'cancelled'

export type RuntimeProgressStatus = OpenUnion<RuntimeKnownProgressStatus>

export const RUNTIME_PROGRESS_STATUSES: readonly RuntimeKnownProgressStatus[] = [
  'pending',
  'running',
  'succeeded',
  'skipped',
  'failed',
  'cancelled',
]

/** `state.status` 的全集，即 Runtime 生命周期状态（values.go: StateStatus）。 */
export type RuntimeKnownStateStatus =
  | 'uninitialized'
  | 'preparing_uv'
  | 'syncing_repository'
  | 'preparing_python'
  | 'syncing_environment'
  | 'ready_to_start'
  | 'starting_backend'
  | 'running'
  | 'restarting'
  | 'stopping_backend'
  | 'environment_broken'
  | 'backend_failed'
  | 'stopped'

export type RuntimeStateStatus = OpenUnion<RuntimeKnownStateStatus>

export const RUNTIME_STATE_STATUSES: readonly RuntimeKnownStateStatus[] = [
  'uninitialized',
  'preparing_uv',
  'syncing_repository',
  'preparing_python',
  'syncing_environment',
  'ready_to_start',
  'starting_backend',
  'running',
  'restarting',
  'stopping_backend',
  'environment_broken',
  'backend_failed',
  'stopped',
]

/**
 * `result.status` 的取值域。
 *
 * Go 侧该字段是裸 `string`（event.go: ResultEvent.Status），实测一次性命令写入
 * 进度语义的 `succeeded`/`failed`/`cancelled`，`backend supervise` 写入生命周期语义的
 * `backend_failed` 等，因此这里是两个集合的并集，不能只按生命周期状态解读。
 */
export type RuntimeResultStatus = RuntimeProgressStatus | RuntimeStateStatus

/** `hello.capabilities` 的稳定能力标识（values.go: Capability）。 */
export type RuntimeKnownCapability = 'stdin.cancel' | 'state.v1' | 'log.stream'

export type RuntimeCapability = OpenUnion<RuntimeKnownCapability>

export const RUNTIME_CAPABILITIES: readonly RuntimeKnownCapability[] = [
  'stdin.cancel',
  'state.v1',
  'log.stream',
]

/** 稳定的处置动作标识（errors.go: Remediation）。 */
export type RuntimeKnownRemediation =
  | 'retry'
  | 'retry-sync'
  | 'retry-other-mirror'
  | 'rebuild-environment'
  | 'stop-backend'
  | 'restart-backend'
  | 'select-version'
  | 'update-desktop'
  | 'run-doctor'
  | 'cleanup'
  | 'open-log'
  | 'contact-support'

export type RuntimeRemediation = OpenUnion<RuntimeKnownRemediation>

export const RUNTIME_REMEDIATIONS: readonly RuntimeKnownRemediation[] = [
  'retry',
  'retry-sync',
  'retry-other-mirror',
  'rebuild-environment',
  'stop-backend',
  'restart-backend',
  'select-version',
  'update-desktop',
  'run-doctor',
  'cleanup',
  'open-log',
  'contact-support',
]

// ==================== 错误码 ====================

/** Runtime 侧稳定错误码全集（errors.go: Code，不含 `OK`）。 */
export type RuntimeKnownErrorCode =
  | 'INVALID_ARGUMENT'
  | 'INVALID_CONTROL_COMMAND'
  | 'INVALID_VERSION'
  | 'UNSUPPORTED_MODE'
  | 'PROTOCOL_MISMATCH'
  | 'OPERATION_CANCELLED'
  | 'OUTPUT_WRITE_FAILED'
  | 'INTERNAL_ERROR'
  | 'PATH_OUTSIDE_MANAGED_ROOT'
  | 'UNSAFE_REPARSE_POINT'
  | 'DIRECTORY_OCCUPIED'
  | 'MUTATION_IN_PROGRESS'
  | 'BACKEND_ALREADY_RUNNING'
  | 'BACKEND_STILL_RUNNING'
  | 'MUTEX_OPERATION_FAILED'
  | 'STATE_WRITE_FAILED'
  | 'UPDATE_STATE_AMBIGUOUS'
  | 'NETWORK_UNAVAILABLE'
  | 'MIRROR_EXHAUSTED'
  | 'GIT_BRANCH_NOT_FOUND'
  | 'GIT_REMOTE_RESOLVE_FAILED'
  | 'GIT_CLONE_FAILED'
  | 'GIT_REPOSITORY_INVALID'
  | 'GIT_VERSION_MISMATCH'
  | 'GIT_REPO_SWAP_FAILED'
  | 'GIT_REPO_CLEANUP_FAILED'
  | 'UV_DOWNLOAD_FAILED'
  | 'UV_CHECKSUM_MISMATCH'
  | 'UV_VERSION_MISMATCH'
  | 'UV_EXEC_FAILED'
  | 'PYTHON_VERSION_FILE_MISSING'
  | 'PYTHON_VERSION_INVALID'
  | 'PYTHON_VERSION_UNSUPPORTED'
  | 'PYTHON_VERSION_INCOMPATIBLE'
  | 'PYTHON_INSTALL_FAILED'
  | 'PYTHON_VERSION_MISMATCH'
  | 'LOCKFILE_MISSING'
  | 'LOCKFILE_OUTDATED'
  | 'DEPENDENCY_SYNC_FAILED'
  | 'ENVIRONMENT_BROKEN'
  | 'ENVIRONMENT_REBUILD_FAILED'
  | 'BACKEND_ENTRY_NOT_FOUND'
  | 'BACKEND_SPAWN_FAILED'
  | 'BACKEND_EXITED_BEFORE_READY'
  | 'BACKEND_HEALTH_TIMEOUT'
  | 'BACKEND_HEALTH_INVALID'
  | 'BACKEND_IDENTITY_MISMATCH'
  | 'BACKEND_EXITED_UNEXPECTEDLY'
  | 'BACKEND_RESTART_FAILED'
  | 'BACKEND_SHUTDOWN_FAILED'
  | 'BACKEND_FORCE_TERMINATED'

/** 成功结果固定使用的结果码。 */
export const RUNTIME_OK_CODE = 'OK'

export type RuntimeCode = OpenUnion<RuntimeKnownErrorCode | 'OK'>

/**
 * 调用侧错误码。Runtime 自己不会输出这些码，它们只在 Runtime 尚未进入协议、
 * 或协议流本身不可信时由本模块产生。
 */
export type RuntimeClientErrorCode =
  | 'RUNTIME_NOT_FOUND'
  | 'RUNTIME_SPAWN_FAILED'
  | 'RUNTIME_HANDSHAKE_TIMEOUT'
  | 'RUNTIME_PROTOCOL_ERROR'
  | 'RUNTIME_PROTOCOL_MISMATCH'
  | 'RUNTIME_EXITED_UNEXPECTEDLY'

/** 退出码只做粗分类，精确原因必须读 `result.code`。 */
export const RUNTIME_EXIT_CODES = {
  success: 0,
  invalidArgument: 2,
  protocolMismatch: 10,
  preconditionFailed: 20,
  networkFailure: 30,
  gitFailure: 40,
  environmentFailure: 50,
  backendFailure: 60,
  operationConflict: 70,
  operationCancelled: 130,
} as const

/** 一个错误码的稳定行为四元组，外加区分用途的中文摘要。 */
export interface RuntimeErrorDefinition {
  code: RuntimeKnownErrorCode
  exitCode: number
  retryable: boolean
  remediation: readonly RuntimeKnownRemediation[]
  /** 展示与日志用的简短说明；同 remediation 的错误码也必须给出不同文案。 */
  summary: string
}

const ERROR_DEFINITION_LIST: readonly RuntimeErrorDefinition[] = [
  {
    code: 'INVALID_ARGUMENT',
    exitCode: 2,
    retryable: false,
    remediation: ['run-doctor'],
    summary: 'Runtime 参数不合法',
  },
  {
    code: 'INVALID_CONTROL_COMMAND',
    exitCode: 0,
    retryable: false,
    remediation: ['update-desktop'],
    summary: 'Runtime 忽略了一条无效的 stdin 控制命令',
  },
  {
    code: 'INVALID_VERSION',
    exitCode: 2,
    retryable: false,
    remediation: ['select-version'],
    summary: '目标版本号不合法',
  },
  {
    code: 'UNSUPPORTED_MODE',
    exitCode: 2,
    retryable: false,
    remediation: ['update-desktop'],
    summary: 'Runtime 不支持该运行模式',
  },
  {
    code: 'PROTOCOL_MISMATCH',
    exitCode: 10,
    retryable: false,
    remediation: ['update-desktop'],
    summary: 'Runtime 协议版本与本程序不兼容',
  },
  {
    code: 'OPERATION_CANCELLED',
    exitCode: 130,
    retryable: true,
    remediation: ['retry'],
    summary: '操作已被取消',
  },
  {
    code: 'OUTPUT_WRITE_FAILED',
    exitCode: 20,
    retryable: false,
    remediation: ['open-log', 'contact-support'],
    summary: 'Runtime 协议输出通道写入失败',
  },
  {
    code: 'INTERNAL_ERROR',
    exitCode: 20,
    retryable: false,
    remediation: ['open-log', 'contact-support'],
    summary: 'Runtime 内部故障（Runtime 自身缺陷，不是输出通道问题）',
  },
  {
    code: 'PATH_OUTSIDE_MANAGED_ROOT',
    exitCode: 70,
    retryable: false,
    remediation: ['run-doctor'],
    summary: '目标路径不在受管根目录内',
  },
  {
    code: 'UNSAFE_REPARSE_POINT',
    exitCode: 70,
    retryable: false,
    remediation: ['contact-support'],
    summary: '路径上存在不安全的重解析点',
  },
  {
    code: 'DIRECTORY_OCCUPIED',
    exitCode: 70,
    retryable: true,
    remediation: ['retry'],
    summary: '目标目录被占用',
  },
  {
    code: 'MUTATION_IN_PROGRESS',
    exitCode: 70,
    retryable: true,
    remediation: ['retry'],
    summary: '已有变更操作正在进行',
  },
  {
    code: 'BACKEND_ALREADY_RUNNING',
    exitCode: 70,
    retryable: false,
    remediation: [],
    summary: '后端已在运行',
  },
  {
    code: 'BACKEND_STILL_RUNNING',
    exitCode: 70,
    retryable: true,
    remediation: ['stop-backend'],
    summary: '后端仍在运行，需先停止',
  },
  {
    code: 'MUTEX_OPERATION_FAILED',
    exitCode: 70,
    retryable: true,
    remediation: ['retry', 'run-doctor'],
    summary: '并发锁操作失败',
  },
  {
    code: 'STATE_WRITE_FAILED',
    exitCode: 70,
    retryable: true,
    remediation: ['retry', 'run-doctor'],
    summary: 'Runtime 状态文件写入失败',
  },
  {
    code: 'UPDATE_STATE_AMBIGUOUS',
    exitCode: 70,
    retryable: false,
    remediation: ['run-doctor', 'contact-support'],
    summary: '更新事务状态不明确',
  },
  {
    code: 'NETWORK_UNAVAILABLE',
    exitCode: 30,
    retryable: true,
    remediation: ['retry', 'run-doctor'],
    summary: '网络不可用',
  },
  {
    code: 'MIRROR_EXHAUSTED',
    exitCode: 30,
    retryable: true,
    remediation: ['retry-other-mirror'],
    summary: '所有镜像源均已尝试失败',
  },
  {
    code: 'GIT_BRANCH_NOT_FOUND',
    exitCode: 40,
    retryable: false,
    remediation: ['select-version'],
    summary: '目标发布分支不存在',
  },
  {
    code: 'GIT_REMOTE_RESOLVE_FAILED',
    exitCode: 30,
    retryable: true,
    remediation: ['retry-other-mirror'],
    summary: '解析 Git 远端失败',
  },
  {
    code: 'GIT_CLONE_FAILED',
    exitCode: 30,
    retryable: true,
    remediation: ['retry-other-mirror'],
    summary: 'Git 克隆失败',
  },
  {
    code: 'GIT_REPOSITORY_INVALID',
    exitCode: 40,
    retryable: true,
    remediation: ['retry-sync'],
    summary: '受管仓库不完整或不可用',
  },
  {
    code: 'GIT_VERSION_MISMATCH',
    exitCode: 40,
    retryable: false,
    remediation: ['contact-support'],
    summary: '仓库版本与目标版本不一致',
  },
  {
    code: 'GIT_REPO_SWAP_FAILED',
    exitCode: 40,
    retryable: true,
    remediation: ['retry', 'run-doctor'],
    summary: '仓库目录替换失败',
  },
  {
    code: 'GIT_REPO_CLEANUP_FAILED',
    exitCode: 40,
    retryable: true,
    remediation: ['cleanup', 'open-log'],
    summary: '仓库临时目录清理失败',
  },
  {
    code: 'UV_DOWNLOAD_FAILED',
    exitCode: 30,
    retryable: true,
    remediation: ['retry-other-mirror'],
    summary: 'uv 下载失败',
  },
  {
    code: 'UV_CHECKSUM_MISMATCH',
    exitCode: 40,
    retryable: true,
    remediation: ['retry-other-mirror', 'contact-support'],
    summary: 'uv 校验和不匹配',
  },
  {
    code: 'UV_VERSION_MISMATCH',
    exitCode: 20,
    retryable: false,
    remediation: ['update-desktop'],
    summary: 'uv 版本与 Runtime 要求不符',
  },
  {
    code: 'UV_EXEC_FAILED',
    exitCode: 50,
    retryable: true,
    remediation: ['run-doctor', 'open-log'],
    summary: 'uv 执行失败',
  },
  {
    code: 'PYTHON_VERSION_FILE_MISSING',
    exitCode: 20,
    retryable: false,
    remediation: ['contact-support'],
    summary: '仓库缺少 .python-version',
  },
  {
    code: 'PYTHON_VERSION_INVALID',
    exitCode: 20,
    retryable: false,
    remediation: ['contact-support'],
    summary: '.python-version 内容不合法',
  },
  {
    code: 'PYTHON_VERSION_UNSUPPORTED',
    exitCode: 20,
    retryable: false,
    remediation: ['update-desktop'],
    summary: 'Runtime 不支持该 Python 版本',
  },
  {
    code: 'PYTHON_VERSION_INCOMPATIBLE',
    exitCode: 20,
    retryable: false,
    remediation: ['contact-support'],
    summary: 'Python 版本与主项目不兼容',
  },
  {
    code: 'PYTHON_INSTALL_FAILED',
    exitCode: 50,
    retryable: true,
    remediation: ['retry-other-mirror', 'open-log'],
    summary: 'Python 安装失败',
  },
  {
    code: 'PYTHON_VERSION_MISMATCH',
    exitCode: 50,
    retryable: true,
    remediation: ['rebuild-environment'],
    summary: '环境内 Python 版本与目标不一致',
  },
  {
    code: 'LOCKFILE_MISSING',
    exitCode: 20,
    retryable: false,
    remediation: ['contact-support'],
    summary: '缺少 uv.lock',
  },
  {
    code: 'LOCKFILE_OUTDATED',
    exitCode: 20,
    retryable: false,
    remediation: ['contact-support'],
    summary: 'uv.lock 与 pyproject.toml 不同步',
  },
  {
    code: 'DEPENDENCY_SYNC_FAILED',
    exitCode: 50,
    retryable: true,
    remediation: ['retry-sync', 'rebuild-environment', 'open-log'],
    summary: '主项目依赖同步失败',
  },
  {
    code: 'ENVIRONMENT_BROKEN',
    exitCode: 50,
    retryable: true,
    remediation: ['retry-sync', 'rebuild-environment'],
    summary: '主项目环境已损坏',
  },
  {
    code: 'ENVIRONMENT_REBUILD_FAILED',
    exitCode: 50,
    retryable: true,
    remediation: ['run-doctor', 'open-log'],
    summary: '主项目环境重建失败',
  },
  {
    code: 'BACKEND_ENTRY_NOT_FOUND',
    exitCode: 20,
    retryable: false,
    remediation: ['retry-sync', 'contact-support'],
    summary: '后端入口文件不存在',
  },
  {
    code: 'BACKEND_SPAWN_FAILED',
    exitCode: 60,
    retryable: true,
    remediation: ['run-doctor', 'open-log'],
    summary: '后端进程创建失败',
  },
  {
    code: 'BACKEND_EXITED_BEFORE_READY',
    exitCode: 60,
    retryable: true,
    remediation: ['restart-backend', 'open-log'],
    summary: '后端在就绪前退出',
  },
  {
    code: 'BACKEND_HEALTH_TIMEOUT',
    exitCode: 60,
    retryable: true,
    remediation: ['restart-backend', 'open-log'],
    summary: '后端健康检查超时',
  },
  {
    code: 'BACKEND_HEALTH_INVALID',
    exitCode: 60,
    retryable: true,
    remediation: ['restart-backend', 'open-log'],
    summary: '后端健康响应无效',
  },
  {
    code: 'BACKEND_IDENTITY_MISMATCH',
    exitCode: 60,
    retryable: false,
    remediation: ['retry-sync', 'contact-support'],
    summary: '后端身份校验不通过',
  },
  {
    code: 'BACKEND_EXITED_UNEXPECTEDLY',
    exitCode: 60,
    retryable: true,
    remediation: ['restart-backend', 'open-log'],
    summary: '后端意外退出',
  },
  {
    code: 'BACKEND_RESTART_FAILED',
    exitCode: 60,
    retryable: true,
    remediation: ['restart-backend', 'rebuild-environment'],
    summary: '后端自动重启失败',
  },
  {
    code: 'BACKEND_SHUTDOWN_FAILED',
    exitCode: 60,
    retryable: true,
    remediation: ['retry', 'open-log'],
    summary: '后端关闭或进程树清理失败',
  },
  {
    code: 'BACKEND_FORCE_TERMINATED',
    exitCode: 0,
    retryable: false,
    remediation: ['open-log'],
    summary: '后端优雅关闭超时后被强制结束',
  },
]

const ERROR_DEFINITION_INDEX = new Map<string, RuntimeErrorDefinition>(
  ERROR_DEFINITION_LIST.map(definition => [definition.code, definition])
)

export const RUNTIME_ERROR_CODES: readonly RuntimeKnownErrorCode[] = ERROR_DEFINITION_LIST.map(
  definition => definition.code
)

/** 查表得到某个 Runtime 错误码的稳定行为；未知码返回 undefined。 */
export function lookupRuntimeErrorDefinition(code: string): RuntimeErrorDefinition | undefined {
  return ERROR_DEFINITION_INDEX.get(code)
}

/** 调用侧错误码的行为定义，语义由本模块自行约定（Runtime 不产生这些码）。 */
export interface RuntimeClientErrorDefinition {
  code: RuntimeClientErrorCode
  retryable: boolean
  remediation: readonly RuntimeKnownRemediation[]
  summary: string
}

export const RUNTIME_CLIENT_ERROR_DEFINITIONS: Readonly<
  Record<RuntimeClientErrorCode, RuntimeClientErrorDefinition>
> = {
  RUNTIME_NOT_FOUND: {
    code: 'RUNTIME_NOT_FOUND',
    retryable: false,
    remediation: ['update-desktop', 'contact-support'],
    summary: '找不到 Runtime 可执行文件',
  },
  RUNTIME_SPAWN_FAILED: {
    code: 'RUNTIME_SPAWN_FAILED',
    retryable: true,
    remediation: ['retry', 'open-log'],
    summary: 'Runtime 进程创建失败',
  },
  RUNTIME_HANDSHAKE_TIMEOUT: {
    code: 'RUNTIME_HANDSHAKE_TIMEOUT',
    retryable: true,
    remediation: ['retry', 'open-log'],
    summary: '等待 Runtime hello 事件超时',
  },
  RUNTIME_PROTOCOL_ERROR: {
    code: 'RUNTIME_PROTOCOL_ERROR',
    retryable: false,
    remediation: ['update-desktop', 'contact-support'],
    summary: 'Runtime 输出不符合 NDJSON 协议',
  },
  RUNTIME_PROTOCOL_MISMATCH: {
    code: 'RUNTIME_PROTOCOL_MISMATCH',
    retryable: false,
    remediation: ['update-desktop'],
    summary: 'Runtime 协议版本与本程序不一致',
  },
  RUNTIME_EXITED_UNEXPECTEDLY: {
    code: 'RUNTIME_EXITED_UNEXPECTEDLY',
    retryable: true,
    remediation: ['retry', 'open-log'],
    summary: 'Runtime 未输出最终结果就退出',
  },
}

// ==================== 事件结构 ====================

/** 所有事件共享的公共字段（event.go: Common）。 */
export interface RuntimeEventCommon {
  protocol: number
  type: RuntimeEventType
  operationId: string
  sequence: number
  timestamp: string
}

/** 首个事件，公告 Runtime 版本与本次操作支持的能力。 */
export interface RuntimeHelloEvent extends RuntimeEventCommon {
  type: 'hello'
  runtimeVersion: string
  command: string
  capabilities: RuntimeCapability[]
}

/** 可量化的阶段进度。`current`/`total`/`percent` 只在总量可知时出现。 */
export interface RuntimeProgressEvent extends RuntimeEventCommon {
  type: 'progress'
  stage: RuntimeStage
  status: RuntimeProgressStatus
  message: string
  current?: number
  total?: number
  percent?: number
}

/** 生命周期状态迁移或只读状态快照。 */
export interface RuntimeStateEvent extends RuntimeEventCommon {
  type: 'state'
  stage: RuntimeStage
  status: RuntimeStateStatus
  message: string
  details: Record<string, unknown>
}

/**
 * 受管进程转发出来的一行日志。
 *
 * `source`（如 `runtime`、`backend`）与 `stream`（`stdout`/`stderr`）在 Go 侧都是裸
 * `string`，架构设计文档的事件表未列出这两个字段。
 */
export interface RuntimeLogEvent extends RuntimeEventCommon {
  type: 'log'
  source: string
  stream: string
  message: string
}

/** 不终止顶层操作的警告，字段与 error 相同。 */
export interface RuntimeWarningEvent extends RuntimeEventCommon {
  type: 'warning'
  code: RuntimeCode
  stage: RuntimeStage
  message: string
  retryable: boolean
  remediation: RuntimeRemediation[]
  details: Record<string, unknown>
}

/** 操作的主错误。 */
export interface RuntimeErrorEvent extends RuntimeEventCommon {
  type: 'error'
  code: RuntimeCode
  stage: RuntimeStage
  message: string
  retryable: boolean
  remediation: RuntimeRemediation[]
  details: Record<string, unknown>
}

/** 顶层操作的最终结果，成功时 `code` 固定为 `OK`。 */
export interface RuntimeResultEvent extends RuntimeEventCommon {
  type: 'result'
  success: boolean
  code: RuntimeCode
  stage: RuntimeStage
  status: RuntimeResultStatus
  message: string
  retryable: boolean
  remediation: RuntimeRemediation[]
  details: Record<string, unknown>
}

/** 按 `type` 判别的事件联合。 */
export type RuntimeEvent =
  | RuntimeHelloEvent
  | RuntimeProgressEvent
  | RuntimeStateEvent
  | RuntimeLogEvent
  | RuntimeWarningEvent
  | RuntimeErrorEvent
  | RuntimeResultEvent

/** `result.details.warnings` 中的 warning 快照（event.go: WarningSummary）。 */
export interface RuntimeWarningSummary {
  code: RuntimeCode
  stage: RuntimeStage
  message: string
  retryable: boolean
  remediation: RuntimeRemediation[]
  details: Record<string, unknown>
}

// ==================== 标准输入控制命令 ====================

/** stdin 控制命令类型。`shutdown` 与 `status` 只对 `backend supervise` 有意义。 */
export type RuntimeControlKind = 'cancel' | 'shutdown' | 'status'

/**
 * 一条 stdin 控制命令。
 *
 * Runtime 的解码器拒绝未知字段，因此这三个字段既是全部必填项也是全部允许项
 * （control.go: decodeControlFields）。`commandId` 必须是规范 ULID。
 */
export interface RuntimeControlCommand {
  protocol: number
  command: RuntimeControlKind
  commandId: string
}

// ==================== 类型守卫 ====================

export function isKnownRuntimeStage(value: string): value is RuntimeKnownStage {
  return (RUNTIME_STAGES as readonly string[]).includes(value)
}

export function isKnownRuntimeProgressStatus(value: string): value is RuntimeKnownProgressStatus {
  return (RUNTIME_PROGRESS_STATUSES as readonly string[]).includes(value)
}

export function isKnownRuntimeStateStatus(value: string): value is RuntimeKnownStateStatus {
  return (RUNTIME_STATE_STATUSES as readonly string[]).includes(value)
}

export function isKnownRuntimeCapability(value: string): value is RuntimeKnownCapability {
  return (RUNTIME_CAPABILITIES as readonly string[]).includes(value)
}

export function isKnownRuntimeRemediation(value: string): value is RuntimeKnownRemediation {
  return (RUNTIME_REMEDIATIONS as readonly string[]).includes(value)
}

export function isKnownRuntimeCode(value: string): boolean {
  return value === RUNTIME_OK_CODE || ERROR_DEFINITION_INDEX.has(value)
}

/**
 * 判断一个 Runtime 错误码是否可重试。
 *
 * 未知错误码按不可重试处理：宁可少给一个重试按钮，也不要让用户在真正不可恢复的
 * 故障上反复重试。`INTERNAL_ERROR` 在表中即为不可重试。
 */
export function isRetryableRuntimeCode(code: string): boolean {
  return ERROR_DEFINITION_INDEX.get(code)?.retryable ?? false
}

/** 事件是否为终态 `result`。 */
export function isRuntimeResultEvent(event: RuntimeEvent): event is RuntimeResultEvent {
  return event.type === 'result'
}

// ==================== 调用侧错误 ====================

export interface RuntimeClientErrorDetails {
  /** Runtime 进程退出码，未退出时为 undefined。 */
  exitCode?: number | null
  /** 结束进程的信号。 */
  signal?: NodeJS.Signals | null
  /** Runtime 自身的 stderr 诊断输出（不是被监督进程的日志）。 */
  stderr?: string
  /** 触发 RUNTIME_PROTOCOL_ERROR 的原始行。 */
  line?: string
  /** 握手拿到的协议版本，用于 RUNTIME_PROTOCOL_MISMATCH。 */
  actualProtocol?: number
  expectedProtocol?: number
  /** Runtime 可执行文件路径。 */
  runtimePath?: string
  /** 本次调用的命令与参数。 */
  argv?: string[]
}

/**
 * 调用侧统一错误。
 *
 * 只承载六个调用侧错误码；Runtime 自己输出的错误（含 `INTERNAL_ERROR`）走
 * `result`/`error` 事件，由调用方按 `code` + `retryable` + `remediation` 处理，
 * 不会被包装成本类型。
 */
export class RuntimeClientError extends Error {
  readonly code: RuntimeClientErrorCode
  readonly retryable: boolean
  readonly remediation: readonly RuntimeKnownRemediation[]
  readonly details: RuntimeClientErrorDetails

  constructor(
    code: RuntimeClientErrorCode,
    message?: string,
    details: RuntimeClientErrorDetails = {},
    options?: { cause?: unknown }
  ) {
    const definition = RUNTIME_CLIENT_ERROR_DEFINITIONS[code]
    super(message || definition.summary)
    this.name = 'RuntimeClientError'
    this.code = code
    this.retryable = definition.retryable
    this.remediation = definition.remediation
    this.details = details
    if (options && 'cause' in options) {
      // Electron 的 Node 支持 Error.cause，但 tsconfig 目标是 ES2020，这里手动挂载。
      ;(this as { cause?: unknown }).cause = options.cause
    }
  }
}

export function isRuntimeClientError(value: unknown): value is RuntimeClientError {
  return value instanceof RuntimeClientError
}
