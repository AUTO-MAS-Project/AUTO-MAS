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
  | 'network.probe'
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
  'network.probe',
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

/**
 * `result.status` 的取值域。
 *
 * Go 侧该字段是裸 `string`（event.go: ResultEvent.Status），实测一次性命令写入
 * 进度语义的 `succeeded`/`failed`/`cancelled`，`backend supervise` 写入生命周期语义的
 * `backend_failed` 等，因此这里是两个集合的并集，不能只按生命周期状态解读。
 */
export type RuntimeResultStatus = RuntimeProgressStatus | RuntimeStateStatus

/**
 * `hello.capabilities` 的稳定能力标识（values.go: Capability）。
 *
 * `stdin.shutdown` 与 `stdin.status` 是 `backend supervise` 一直接受、后来才补公告的两条
 * stdin 控制命令；调用方按契约只信 hello 宣告的能力，没宣告就不发对应命令。
 */
export type RuntimeKnownCapability =
  | 'stdin.cancel'
  | 'state.v1'
  | 'log.stream'
  | 'stdin.shutdown'
  | 'stdin.status'

export type RuntimeCapability = OpenUnion<RuntimeKnownCapability>

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
  | 'LOCKFILE_INVALID'
  | 'LOCKFILE_CHECK_FAILED'
  | 'WORKSPACE_RESTORE_FAILED'
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

/**
 * 可量化的阶段进度。`current`/`total`/`percent` 只在总量可知时出现。
 *
 * M14 起下载类 stage（`uv.download` / `python.install` / `dependencies.sync`）的
 * `current` / `total` 是真实字节数，并追加三个可选字段说明「在拉什么、从哪拉、多快」；
 * `network.probe`（下载前的镜像源测速）每探测完一个源发一条 `running`，`item` 与 `source`
 * 都是源 key，`current` / `total` 是已完成源数 / 源总数，全部完成后发一条 `succeeded`。
 * 测速的 `bytesPerSecond` 三种取值三种含义：正数是实测吞吐；`0` 是探测失败；缺失是探测
 * 成功但只测了首字节、没有吞吐可报（git 类源）。旧版 Runtime 不带这三个字段，缺失即无信息。
 */
export interface RuntimeProgressEvent extends RuntimeEventCommon {
  type: 'progress'
  stage: RuntimeStage
  status: RuntimeProgressStatus
  message: string
  current?: number
  total?: number
  percent?: number
  /** 当前条目：正在下载的文件名，或测速时的源 key。 */
  item?: string
  /** 当前字节来自哪个源的 key（`aliyun` / `tsinghua` / `pypi` / `github` / `cnb` …）。 */
  source?: string
  /** 最近 1 秒窗口的整数吞吐（字节/秒）；测速时 `0` 表示探测失败、缺失表示只测了首字节。 */
  bytesPerSecond?: number
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

// ==================== 调用侧错误 ====================

export interface RuntimeClientErrorDetails {
  /** Runtime 进程退出码，未退出时为 undefined。 */
  exitCode?: number | null
  /** 结束进程的信号。 */
  signal?: NodeJS.Signals | null
  /** Runtime 自身的 stderr 诊断输出（不是被监督进程的日志）。 */
  stderr?: string
  /** 触发 RUNTIME_PROTOCOL_ERROR 的原始行；超长行被丢弃时只保留开头片段。 */
  line?: string
  /** 单行超过该长度时被丢弃，仅超长行的 RUNTIME_PROTOCOL_ERROR 携带。 */
  maxLineLength?: number
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
