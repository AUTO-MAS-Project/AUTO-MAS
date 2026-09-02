/**
 * Runtime 链路的后端更新
 *
 * 灰度开关打开后，后端更新不再由 Python 侧自己下载 `UpdatePack_<版本>.zip` 再拉起
 * Inno Setup 安装器整包替换，而是由 Electron 做停机与更新编排者，严格按三步走：
 *
 * 1. 向当前 `backend supervise` 的 stdin 发 `shutdown`，等最终 `result` 与进程退出
 *    （backendService 的 `stopBackend()` 已封装）——`workspace sync` 发现后端仍在跑会
 *    直接返回 `BACKEND_STILL_RUNNING`，所以这一步必须真的等到退出；
 * 2. `bootstrap --version v<新版本>`：临时目录浅克隆 `release/<新版本>`、校验通过后整体
 *    替换 `repo/`，再同步 Python 与依赖；
 * 3. 重新 `backend supervise`（backendService 的 `startBackend()`）。
 *
 * 三步各自的失败后果完全不同，所以失败结果里带 `phase`，界面据此给出不同的处置入口，
 * 见 `RuntimeUpdatePhase`。进度桥接、阶段映射与单步重试全部复用初始化链路
 * （runtimeInitializationService），这里只做编排，不重写一套。
 */

import type { BackendStartResult, BackendStopResult } from './backendService'
import { getLogger } from './logger'
import type { RuntimeLaunchConfig, RuntimeRemediation } from './runtime'
import {
  InitializationRunStage,
  InitializationStageStatus,
  RuntimeInitializationOptions,
  RuntimeInitializationService,
  RuntimeRetryMode,
  RuntimeStageOutcome,
  toRuntimeVersion,
} from './runtimeInitializationService'

const logger = getLogger('Runtime更新')

// ==================== 阶段与结局 ====================

/**
 * 更新失败的三类结局。
 *
 * - `shutdown`：旧后端还在（没停掉，或者根本没开始动作，例如版本号非法）。源码与环境
 *   一动没动，用户可以直接取消更新继续用旧版本；
 * - `bootstrap`：源码可能已经被整体替换、环境可能是 `environment_broken`。Runtime 只在
 *   克隆或校验失败时才保证保留旧 `repo/`；一旦 `uv sync` 失败，源码已经是新版本而环境
 *   坏了，回不去，只能重试同步或重建环境；
 * - `restart`：源码与环境都已就位，但新后端没起来。展示 `formatStartupLogs` 的整块日志。
 */
export type RuntimeUpdatePhase = 'shutdown' | 'bootstrap' | 'restart'

/** 更新流程的进度段：首尾两段是更新独有的，中间七段与初始化界面完全一致。 */
export type RuntimeUpdateStage = 'shutdown' | InitializationRunStage | 'restart'

export interface RuntimeUpdateProgress {
  stage: RuntimeUpdateStage
  status: InitializationStageStatus
  progress: number
  message: string
}

/**
 * 失败后可用的重试入口。
 *
 * 全部由初始化链路的单步重试执行，不另写命令：
 * - `workspace-sync` → `workspace sync --version v<目标版本>`
 * - `dependencies-sync` → `dependencies sync`
 * - `dependencies-rebuild` → `dependencies rebuild`
 * - `repair` → `repair`
 */
export type RuntimeUpdateRetryAction =
  | 'workspace-sync'
  | 'dependencies-sync'
  | 'dependencies-rebuild'
  | 'repair'

/** 重试入口到初始化链路单步重试参数的映射。 */
const RETRY_ACTION_MAP: Readonly<
  Record<RuntimeUpdateRetryAction, { stage: InitializationRunStage; mode: RuntimeRetryMode }>
> = {
  'workspace-sync': { stage: 'repository', mode: 'auto' },
  'dependencies-sync': { stage: 'dependency', mode: 'sync' },
  'dependencies-rebuild': { stage: 'dependency', mode: 'rebuild' },
  repair: { stage: 'python', mode: 'rebuild' },
}

export interface RuntimeUpdateOutcome {
  success: boolean
  /** 失败时必有；成功时不写。 */
  phase?: RuntimeUpdatePhase
  error?: string
  /** Runtime 的结构化结果码，原样透传，不做翻译。 */
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
  /** `[stdout]…\n\n[stderr]…` 整块文本。 */
  logs?: string
  /** Runtime 自己的轮转日志路径。 */
  logPath?: string
  /** 本次失败可用的重试入口，按推荐顺序排列；不可重试时为空。 */
  retryActions?: RuntimeUpdateRetryAction[]
  /**
   * 重试已无意义，只能携带日志反馈。
   *
   * `retryable=false`、`INTERNAL_ERROR` 或 remediation 含 `contact-support` 时为真；
   * 此时 `retryActions` 必为空，界面改为提示用户带上日志反馈。
   */
  supportRequired?: boolean
  /** 用户主动取消。 */
  cancelled?: boolean
  /** 当前模式根本不支持自动更新（development 或灰度开关关闭）。 */
  unsupported?: boolean
}

/** 更新流程只用到 backendService 的这两个方法，测试直接给桩。 */
export interface BackendUpdateController {
  stopBackend(): Promise<BackendStopResult>
  startBackend(): Promise<BackendStartResult>
}

export interface RuntimeUpdateDependencies {
  backend: BackendUpdateController
  /** 本次生命周期的启动模式与 Runtime 路径，由调用方解析后传入。 */
  launchConfig: RuntimeLaunchConfig
  /** 省略时用真实的初始化编排器。 */
  createRuntimeService?: (options: RuntimeInitializationOptions) => RuntimeInitializationService
}

// ==================== 版本号 ====================

/**
 * 目标版本的合法形态：`v` 加点分数字，可跟一段预发布/构建后缀。
 *
 * Runtime 把它拼进 `release/<版本>` 分支名，非法字符必须在这里挡掉，不能交给 Runtime
 * 报错——一个带 `/` 的版本号会变成另一个分支名，而不是一个报错。
 */
const RUNTIME_VERSION_PATTERN = /^v\d+(\.\d+)*([-+][0-9A-Za-z.-]+)?$/

/**
 * 把 `/api/update/check` 给的版本号规范成 Runtime 要的 `v<x.y.z…>`。
 *
 * MirrorChyan 返回的 `version_name` 可能带 `v` 也可能不带（本仓库的发布标签是带的），
 * 统一补齐；含路径分隔符、空白或 `..` 的一律判非法，返回 null。
 */
export function normalizeRuntimeUpdateVersion(raw: unknown): string | null {
  if (typeof raw !== 'string') return null

  const trimmed = raw.trim()
  if (!trimmed) return null
  // 路径穿越与分隔符先于格式校验挡掉，避免任何形态被拼进分支名。
  if (/[\s/\\]/.test(trimmed) || trimmed.includes('..')) return null

  const normalized = toRuntimeVersion(trimmed)
  return RUNTIME_VERSION_PATTERN.test(normalized) ? normalized : null
}

// ==================== 会话 ====================

/**
 * 一次更新会话。
 *
 * 单步重试要和它前面那次 bootstrap 用同一个编排器实例（后者记着上一次失败给出的
 * remediation，也记着本次的目标版本），所以会话在模块级保留到下一次更新开始。
 */
interface UpdateSession {
  version: string
  runtimeService: RuntimeInitializationService
  backend: BackendUpdateController
  cancelRequested: boolean
  /** 应用正在退出：取消后不再把旧后端拉回来，交给退出清场统一处理。 */
  abortedForShutdown: boolean
  /** 在途的 bootstrap 或单步重试，退出清场要等它落地。 */
  inFlight: Promise<unknown> | null
}

let session: UpdateSession | null = null

/** 仅供测试清场；应用退出走 `abortRuntimeUpdateForShutdown`。 */
export function resetRuntimeUpdateSession(): void {
  session = null
}

export interface RuntimeUpdateAbortResult {
  /** 清场时是否有更新会话。 */
  hadSession: boolean
  /** 是否有在途 Runtime 命令并已向它下发 cancel。 */
  forwarded: boolean
  /** 在途命令是否在时限内落地；没有在途命令时为真。 */
  settled: boolean
}

/** 退出清场默认等在途命令落地的上限。 */
export const RUNTIME_UPDATE_ABORT_TIMEOUT_MS = 5000

/**
 * 应用退出时中止更新。
 *
 * 只置空会话不够：bootstrap 子进程会跑成孤儿，下次启动撞 `MUTATION_IN_PROGRESS`。
 * 这里先对在途命令下发 cancel，等它在时限内落地（Runtime 收到 cancel 会以
 * `OPERATION_CANCELLED` 收尾），再置空；超时也置空，不拖住退出。
 */
export async function abortRuntimeUpdateForShutdown(
  timeoutMs = RUNTIME_UPDATE_ABORT_TIMEOUT_MS
): Promise<RuntimeUpdateAbortResult> {
  const current = session
  if (!current) return { hadSession: false, forwarded: false, settled: true }

  current.cancelRequested = true
  current.abortedForShutdown = true
  const forwarded = current.runtimeService.cancel()

  let settled = true
  const inFlight = current.inFlight
  if (inFlight) {
    logger.info(`应用退出，等待在途更新命令落地（上限 ${timeoutMs}ms）`)
    settled = await waitForSettle(inFlight, timeoutMs)
    if (!settled) logger.warn('在途更新命令未在时限内落地，放弃等待')
  }

  if (session === current) session = null
  logger.info(`更新会话已因应用退出清场${forwarded ? '，并已下发 stdin cancel' : ''}`)
  return { hadSession: true, forwarded, settled }
}

/** 等一个 promise 落地（无论成败），超时返回 false。 */
function waitForSettle(target: Promise<unknown>, timeoutMs: number): Promise<boolean> {
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve(false), timeoutMs)
    const done = (): void => {
      clearTimeout(timer)
      resolve(true)
    }
    target.then(done, done)
  })
}

const defaultRuntimeServiceFactory = (
  options: RuntimeInitializationOptions
): RuntimeInitializationService => new RuntimeInitializationService(options)

// ==================== 编排 ====================

const STOP_MESSAGE = '正在停止当前后端'
const STOP_DONE_MESSAGE = '后端已停止'
const RESTART_MESSAGE = '正在重新启动后端'
const RESTART_DONE_MESSAGE = '后端已重新启动'
export const RUNTIME_UPDATE_UNSUPPORTED_CODE = 'RUNTIME_UPDATE_UNSUPPORTED'
export const RUNTIME_UPDATE_INVALID_VERSION_CODE = 'INVALID_VERSION'

/**
 * 走 Runtime 链路更新后端：停机 → bootstrap → 重新监督。
 *
 * @param targetVersion `/api/update/check` 给的目标版本，带不带 `v` 都行。
 * @param onProgress 首段 `shutdown`、中间七段沿用初始化界面的段模型、末段 `restart`。
 */
export async function updateBackendViaRuntime(
  targetVersion: string,
  onProgress: (update: RuntimeUpdateProgress) => void,
  deps: RuntimeUpdateDependencies
): Promise<RuntimeUpdateOutcome> {
  const { launchConfig } = deps

  if (launchConfig.mode === 'off') {
    logger.info('灰度开关关闭，Runtime 更新链路不可用')
    return unsupported('灰度开关关闭时后端更新仍走原有的下载安装包流程')
  }

  if (launchConfig.mode === 'development') {
    // 开发检出是开发者自己的源码，Runtime 只监督它，绝不替换。
    logger.info('development 模式不支持自动更新后端源码')
    return unsupported('开发模式下 Runtime 不管理源码，请自行更新本地检出')
  }

  const version = normalizeRuntimeUpdateVersion(targetVersion)
  if (!version) {
    const message = `目标版本号非法：${String(targetVersion)}`
    logger.error(message)
    return {
      success: false,
      phase: 'shutdown',
      error: message,
      code: RUNTIME_UPDATE_INVALID_VERSION_CODE,
      retryable: false,
      remediation: ['select-version'],
    }
  }

  const runtimeService = (deps.createRuntimeService ?? defaultRuntimeServiceFactory)({
    launchConfig,
    targetVersion: version,
  })
  const current: UpdateSession = {
    version,
    runtimeService,
    backend: deps.backend,
    cancelRequested: false,
    abortedForShutdown: false,
    inFlight: null,
  }
  session = current

  logger.info(`开始经 Runtime 更新后端到 ${version}`)

  // ---------- 1. 停机 ----------
  onProgress({ stage: 'shutdown', status: 'started', progress: 0, message: STOP_MESSAGE })
  const stopResult = await deps.backend.stopBackend()
  if (!stopResult.success) {
    const message = stopResult.error ?? '停止当前后端失败'
    logger.error(`更新中止：${message}`)
    onProgress({ stage: 'shutdown', status: 'failed', progress: 0, message })
    return {
      success: false,
      phase: 'shutdown',
      error: message,
      retryable: true,
      remediation: ['stop-backend'],
    }
  }
  onProgress({ stage: 'shutdown', status: 'completed', progress: 100, message: STOP_DONE_MESSAGE })

  // 停机期间按了取消：源码一动没动，直接把旧后端拉回来。
  if (current.cancelRequested) {
    logger.info('更新在 bootstrap 开始前被取消，重新启动旧后端')
    return finishCancelled(current, onProgress)
  }

  // ---------- 2. bootstrap ----------
  const bootstrapOutcome = await trackInFlight(
    current,
    runtimeService.bootstrap(update => onProgress(update))
  )
  if (!bootstrapOutcome.success) {
    // Runtime 只在提交点（整体替换 `repo/`）之前受理取消，所以 OPERATION_CANCELLED 就
    // 意味着源码一动没动，结局与 bootstrap 开始前取消完全一样：把旧后端拉回来。
    if (isCancelledOutcome(bootstrapOutcome)) {
      logger.info('bootstrap 在替换源码前被取消，重新启动旧后端')
      return finishCancelled(current, onProgress, bootstrapOutcome)
    }
    return buildBootstrapFailure(bootstrapOutcome, current.cancelRequested)
  }

  // ---------- 3. 重新监督 ----------
  return restartBackend(current, onProgress)
}

/**
 * 单步重试：只重跑失败的那一段，成功后继续把后端拉起来。
 *
 * 必须在同一次更新会话内调用——重试用的目标版本与「上次失败要不要重建环境」都存在
 * 那个会话的编排器实例里。
 */
export async function retryBackendUpdate(
  action: RuntimeUpdateRetryAction,
  onProgress: (update: RuntimeUpdateProgress) => void
): Promise<RuntimeUpdateOutcome> {
  const current = session
  if (!current) {
    const message = '没有进行中的更新会话，请重新发起更新'
    logger.warn(message)
    return { success: false, phase: 'bootstrap', error: message, retryable: false }
  }

  const mapped = RETRY_ACTION_MAP[action]
  current.cancelRequested = false
  logger.info(`重试更新入口 ${action}（段 ${mapped.stage}，模式 ${mapped.mode}）`)

  const outcome = await trackInFlight(
    current,
    current.runtimeService.retryStage(
      mapped.stage,
      update => onProgress(update),
      undefined,
      mapped.mode
    )
  )
  if (!outcome.success) {
    // 单步重试时源码可能已是新版本，取消后不能再拉旧后端；保留重试入口让用户接着修。
    return buildBootstrapFailure(outcome, current.cancelRequested)
  }

  return restartBackend(current, onProgress)
}

/** 本次会话实际会执行的命令，供界面与测试确认重试入口没接错。 */
export function describeRetryAction(action: RuntimeUpdateRetryAction): string[] | null {
  const current = session
  if (!current) return null
  const mapped = RETRY_ACTION_MAP[action]
  return current.runtimeService.resolveRetryCommand(mapped.stage, mapped.mode)
}

/**
 * 请求取消。
 *
 * 只在停机之前或 bootstrap 尚未替换 `repo/` 时有意义：Runtime 保证克隆未完成时保留旧
 * 仓库，提交点之后的迟到取消不会把已激活的现场伪装成取消，结局仍以它的 `result` 为准。
 */
export function cancelBackendUpdate(): { accepted: boolean; forwarded: boolean } {
  const current = session
  if (!current) return { accepted: false, forwarded: false }

  current.cancelRequested = true
  const forwarded = current.runtimeService.cancel()
  logger.info(`已受理更新取消请求${forwarded ? '，并已下发 stdin cancel' : ''}`)
  return { accepted: true, forwarded }
}

// ==================== 内部 ====================

function unsupported(message: string): RuntimeUpdateOutcome {
  return {
    success: false,
    phase: 'shutdown',
    unsupported: true,
    error: message,
    code: RUNTIME_UPDATE_UNSUPPORTED_CODE,
    retryable: false,
  }
}

/** 记下在途的 Runtime 命令，供退出清场等待；落地后清掉。 */
async function trackInFlight<T>(current: UpdateSession, task: Promise<T>): Promise<T> {
  current.inFlight = task
  try {
    return await task
  } finally {
    if (current.inFlight === task) current.inFlight = null
  }
}

/** Runtime 受理了取消：源码没动。 */
function isCancelledOutcome(outcome: RuntimeStageOutcome): boolean {
  return outcome.code === 'OPERATION_CANCELLED'
}

/**
 * 取消时源码一动没动（停机后、bootstrap 前，或 bootstrap 在提交点前被 Runtime 受理）：
 * 后端已经停了，得把它按原样拉回来。拉不起来时结局是 `restart`，界面给「重新启动后端」。
 * 应用正在退出时不再拉起，交给退出清场。
 */
async function finishCancelled(
  current: UpdateSession,
  onProgress: (update: RuntimeUpdateProgress) => void,
  outcome?: RuntimeStageOutcome
): Promise<RuntimeUpdateOutcome> {
  const detail = outcome ? { code: outcome.code, logPath: outcome.logPath } : {}
  if (current.abortedForShutdown) {
    logger.info('应用正在退出，取消后不再重新启动旧后端')
    return { success: false, phase: 'shutdown', cancelled: true, error: '更新已取消', ...detail }
  }

  const restarted = await restartBackend(current, onProgress)
  if (!restarted.success) return { ...restarted, cancelled: true }
  return { success: false, phase: 'shutdown', cancelled: true, error: '更新已取消', ...detail }
}

/**
 * 重试已无意义、只能携带日志反馈的失败。
 *
 * `INTERNAL_ERROR` 一律视为不可重试，不看 `retryable`；remediation 里明确给了
 * `contact-support` 的同样如此。
 */
export function requiresSupport(outcome: {
  code?: string
  retryable?: boolean
  remediation?: RuntimeRemediation[]
}): boolean {
  if (outcome.retryable === false) return true
  if (outcome.code === 'INTERNAL_ERROR') return true
  return outcome.remediation?.includes('contact-support') ?? false
}

async function restartBackend(
  current: UpdateSession,
  onProgress: (update: RuntimeUpdateProgress) => void
): Promise<RuntimeUpdateOutcome> {
  onProgress({ stage: 'restart', status: 'started', progress: 0, message: RESTART_MESSAGE })

  const startResult = await current.backend.startBackend()
  if (!startResult.success) {
    const message = startResult.error ?? '后端启动失败'
    logger.error(`更新后重新启动后端失败: ${message}`)
    onProgress({ stage: 'restart', status: 'failed', progress: 0, message })
    return {
      success: false,
      phase: 'restart',
      error: message,
      code: startResult.code,
      retryable: startResult.retryable,
      remediation: startResult.remediation,
      logs: startResult.logs,
      supportRequired: requiresSupport(startResult),
    }
  }

  onProgress({
    stage: 'restart',
    status: 'completed',
    progress: 100,
    message: RESTART_DONE_MESSAGE,
  })
  logger.info(`后端已更新到 ${current.version} 并重新启动`)
  return { success: true }
}

/**
 * bootstrap 或单步重试失败：结局一律是 `bootstrap`，附上该段对应的重试入口；
 * 不可重试（`retryable=false`、`INTERNAL_ERROR`、`contact-support`）时重试入口为空，
 * 改为提示携带日志反馈。
 */
function buildBootstrapFailure(
  outcome: RuntimeStageOutcome,
  cancelled: boolean
): RuntimeUpdateOutcome {
  const supportRequired = requiresSupport(outcome)
  return {
    success: false,
    phase: 'bootstrap',
    error: outcome.error,
    code: outcome.code,
    retryable: outcome.retryable,
    remediation: outcome.remediation,
    logs: outcome.logs,
    logPath: outcome.logPath,
    retryActions: supportRequired ? [] : resolveRetryActions(outcome.failedStage),
    supportRequired,
    ...(cancelled ? { cancelled: true } : {}),
  }
}

/**
 * 失败段到重试入口。
 *
 * 仓库段失败时旧 `repo/` 仍在，只要重跑 `workspace sync`；依赖段失败时源码已经是新版本
 * 而环境标记为 `environment_broken`，退不回去，只能重试同步、重建依赖或整体修复。
 */
export function resolveRetryActions(
  failedStage: InitializationRunStage | undefined
): RuntimeUpdateRetryAction[] {
  switch (failedStage) {
    case 'repository':
      return ['workspace-sync']
    case 'dependency':
      return ['dependencies-sync', 'dependencies-rebuild', 'repair']
    default:
      return ['repair']
  }
}
