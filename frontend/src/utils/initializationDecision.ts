import { managesBackendProcess } from '@/utils/environment'
import type { RuntimeInitMode } from '@/types/electron'
import { beginAnalyticsOperation } from '@/utils/analytics'

type InitializationDecisionMode = 'skip-home' | 'full-init' | 'force-backend-update'

interface InitializationDecision {
  mode: InitializationDecisionMode
  currentVersion: string
  savedVersion: string | null
  autoUpdateEnabled: boolean
  forceBackendUpdate: boolean
}

let decisionObserved = false

export async function getInitializationDecision(): Promise<InitializationDecision> {
  if (decisionObserved) return resolveInitializationDecision()
  decisionObserved = true
  const operation = beginAnalyticsOperation('initialization_decided')
  const runtime = Promise.resolve()
    .then(() => (managesBackendProcess() ? window.electronAPI.getRuntimeInitContext?.() : null))
    .catch(() => null)
  const decision = await resolveInitializationDecision()
  // 额外的模式查询仅用于统计，不延长路由守卫的等待。
  void runtime.then(context =>
    operation.finish({
      decision: decision.mode,
      runtime_mode: context?.mode ?? 'unknown',
    })
  )
  return decision
}

async function resolveInitializationDecision(): Promise<InitializationDecision> {
  const api = window.electronAPI
  const logger = api.getLogger('初始化决策')
  const currentVersion = import.meta.env.VITE_APP_VERSION
  const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
  const disableSkip = sessionStorage.getItem('disableInitializationSkip') === 'true'

  if (forceBackendUpdate && managesBackendProcess()) {
    await api.cancelDesktopStartup?.()
    return {
      mode: 'force-backend-update',
      currentVersion,
      savedVersion: null,
      autoUpdateEnabled: false,
      forceBackendUpdate,
    }
  }

  if (disableSkip) {
    return {
      mode: 'full-init',
      currentVersion,
      savedVersion: null,
      autoUpdateEnabled: false,
      forceBackendUpdate,
    }
  }

  if (!managesBackendProcess()) {
    return {
      mode: 'skip-home',
      currentVersion,
      savedVersion: currentVersion,
      autoUpdateEnabled: false,
      forceBackendUpdate,
    }
  }

  const startup = await api.desktopStartupStatus?.()
  if (startup) {
    return {
      mode: startup.fullInitialization || startup.state === 'failed' ? 'full-init' : 'skip-home',
      currentVersion,
      savedVersion: startup.flowKind === 'first-run' ? null : currentVersion,
      autoUpdateEnabled: startup.fullInitialization,
      forceBackendUpdate,
    }
  }

  let autoUpdateEnabled = false
  try {
    const config = await api.loadConfig?.()
    autoUpdateEnabled = config?.Update?.IfAutoUpdate ?? false
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取自动更新配置失败，回退为完整初始化: ${errorMsg}`)
  }

  let savedVersion: string | null = null
  try {
    savedVersion = await api.getInitializedVersion?.()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取初始化版本失败，回退为完整初始化: ${errorMsg}`)
  }

  if (!autoUpdateEnabled && savedVersion === currentVersion) {
    return {
      mode: 'skip-home',
      currentVersion,
      savedVersion,
      autoUpdateEnabled,
      forceBackendUpdate,
    }
  }

  return {
    mode: 'full-init',
    currentVersion,
    savedVersion,
    autoUpdateEnabled,
    forceBackendUpdate,
  }
}

// ==================== 失败态动作决策 ====================

/**
 * 失败时界面上真正能点的动作。
 *
 * 与 Runtime 的 remediation 不是一一对应：`retry` / `retry-sync` / `restart-backend`
 * 在界面上都是同一个「重试」按钮（都调该步骤现有的重试通道），
 * `contact-support` 本身不是按钮，它带出的是一段提示加一个「打开日志」。
 */
export type FailureActionKind =
  | 'restore-workspace'
  | 'retry'
  | 'rebuild-environment'
  | 'open-log'
  | 'run-doctor'

export interface FailureAction {
  kind: FailureActionKind
  /** 按钮文案的词表 key。 */
  labelKey: string
}

/** 需要在按钮之外多说一句话的两种情形。 */
export type FailureNoticeKind = 'internal-error' | 'contact-support'

interface FailureActionPlan {
  /** 有序动作列表，界面按这个顺序渲染，第一个作主按钮。 */
  actions: FailureAction[]
  /** 额外提示文案的种类，不需要时为 null。 */
  notice: FailureNoticeKind | null
}

/** 决策输入，全部来自失败结果里的机器字段，不含任何展示文案。 */
interface FailureContext {
  /** Runtime 结果码。 */
  code?: string
  retryable?: boolean
  remediation?: string[]
  /** 界面段 key，如 `python` / `repository` / `dependency`。 */
  stage?: string
  runtimeMode?: RuntimeInitMode
}

/** remediation 到界面动作的显式对应；这里没有的一律忽略。 */
const REMEDIATION_ACTIONS: Readonly<Record<string, FailureActionKind>> = {
  retry: 'retry',
  'retry-sync': 'retry',
  'restart-backend': 'retry',
  'retry-other-mirror': 'retry',
  'rebuild-environment': 'rebuild-environment',
  'open-log': 'open-log',
  'run-doctor': 'run-doctor',
}

/** 会真的再跑一次安装的动作，`retryable === false` 时全部屏蔽。 */
const RETRY_KINDS = new Set<FailureActionKind>(['retry', 'rebuild-environment'])

const ACTION_LABEL_KEYS: Readonly<Record<FailureActionKind, string>> = {
  'restore-workspace': 'bootstrap.init.failure.restoreWorkspace',
  retry: 'bootstrap.init.step.retry',
  'rebuild-environment': 'bootstrap.init.failure.rebuildEnvironment',
  'open-log': 'bootstrap.launch.viewLog',
  'run-doctor': 'bootstrap.init.failure.runDoctor',
}

/** Runtime 自身的缺陷，重试多少次都是同一个结果。 */
const INTERNAL_ERROR_CODE = 'INTERNAL_ERROR'

function toAction(kind: FailureActionKind): FailureAction {
  return { kind, labelKey: ACTION_LABEL_KEYS[kind] }
}

function pushUnique(kinds: FailureActionKind[], kind: FailureActionKind): void {
  if (!kinds.includes(kind)) kinds.push(kind)
}

/** 缺少可识别处置动作时仍保留普通重试和本地日志。 */
function fallbackPlan(): FailureActionPlan {
  return { actions: [toAction('retry'), toAction('open-log')], notice: null }
}

/**
 * 按失败结果里的机器字段决定失败态给哪些按钮。
 *
 * 纯函数，不碰 DOM 也不读全局状态，界面只负责渲染返回的动作列表并把点击接回对应通道。
 * 三条硬规则：
 * - `retryable === false` 不出普通重试按钮；受管源码恢复与 Runtime 补装独立处理；
 * - `INTERNAL_ERROR` 一律按不可重试处理，只给日志和一句「请携带日志反馈」；
 * - 认不出来的 remediation 按协议要求忽略，一条都认不出来时保留普通重试与日志。
 * 日志是界面兜底：等待态始终有「查看日志」，失败态不能因为这个错误码没声明
 * `open-log` 就把入口收走。
 */
export function decideFailureActions(context: FailureContext): FailureActionPlan {
  // 找不到现有 exe 时不能重启它；managed 模式的重试已转到完整初始化，先补装再启动。
  if (context.runtimeMode === 'managed' && context.code === 'RUNTIME_NOT_FOUND') {
    return fallbackPlan()
  }
  // 源码恢复会先重新校验 Runtime 并执行完整 bootstrap，不是重跑失败的依赖命令。
  if (context.runtimeMode === 'managed' && canRestoreWorkspace(context.code)) {
    return {
      actions: [toAction('restore-workspace'), toAction('open-log')],
      notice: null,
    }
  }
  const remediation = context.remediation ?? []

  const isInternalError = context.code === INTERNAL_ERROR_CODE
  const retryAllowed = context.retryable !== false && !isInternalError
  const kinds: FailureActionKind[] = []
  let notice: FailureNoticeKind | null = null
  let recognized = 0

  for (const item of remediation) {
    if (item === 'contact-support') {
      recognized += 1
      notice = notice ?? 'contact-support'
      pushUnique(kinds, 'open-log')
      continue
    }

    const mapped = REMEDIATION_ACTIONS[item]
    if (!mapped) continue
    recognized += 1
    pushUnique(kinds, mapped)
  }

  if (isInternalError) {
    notice = 'internal-error'
    pushUnique(kinds, 'open-log')
  }

  // 一条都没认出来（只给了未知 code、或 remediation 全是界面管不了的动作）。
  if (recognized === 0) {
    if (retryAllowed) return fallbackPlan()
    return {
      actions: [toAction('open-log')],
      notice: notice ?? 'contact-support',
    }
  }

  const allowed = retryAllowed ? kinds : kinds.filter(kind => !RETRY_KINDS.has(kind))
  pushUnique(allowed, 'open-log')

  return {
    actions: allowed.map(toAction),
    notice,
  }
}

const WORKSPACE_RECOVERY_CODES = new Set([
  'LOCKFILE_MISSING',
  'LOCKFILE_OUTDATED',
  'LOCKFILE_INVALID',
  'LOCKFILE_CHECK_FAILED',
  'WORKSPACE_RESTORE_FAILED',
  'GIT_REPOSITORY_INVALID',
  'BACKEND_ENTRY_NOT_FOUND',
  'PYTHON_VERSION_FILE_MISSING',
  'PYTHON_VERSION_INVALID',
])

/** canRestoreWorkspace 标记能通过完整 bootstrap 恢复受管源码的错误。 */
export function canRestoreWorkspace(code: string | undefined): boolean {
  return code !== undefined && WORKSPACE_RECOVERY_CODES.has(code)
}
