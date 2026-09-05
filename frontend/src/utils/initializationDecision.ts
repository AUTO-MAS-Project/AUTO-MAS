import type { RuntimeInitMode } from '@/types/electron'

export type InitializationDecisionMode = 'skip-home' | 'full-init' | 'force-backend-update'

export interface InitializationDecision {
  mode: InitializationDecisionMode
  currentVersion: string
  savedVersion: string | null
  autoUpdateEnabled: boolean
  forceBackendUpdate: boolean
}

export async function getInitializationDecision(): Promise<InitializationDecision> {
  const api = window.electronAPI
  const logger = api.getLogger('初始化决策')
  const currentVersion = import.meta.env.VITE_APP_VERSION
  const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
  const disableSkip = sessionStorage.getItem('disableInitializationSkip') === 'true'

  if (forceBackendUpdate) {
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

  if (import.meta.env.DEV) {
    return {
      mode: 'skip-home',
      currentVersion,
      savedVersion: currentVersion,
      autoUpdateEnabled: false,
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
  | 'retry'
  | 'retry-other-mirror'
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

export interface FailureActionPlan {
  /** 有序动作列表，界面按这个顺序渲染，第一个作主按钮。 */
  actions: FailureAction[]
  /** 是否展开镜像源选择面板。 */
  showMirrorSelection: boolean
  /** 额外提示文案的种类，不需要时为 null。 */
  notice: FailureNoticeKind | null
  /** 本次失败没带任何 Runtime 结构化字段，按旧链路原样展示。 */
  legacy: boolean
}

/** 决策输入，全部来自失败结果里的机器字段，不含任何展示文案。 */
export interface FailureContext {
  /** Runtime 结果码。 */
  code?: string
  retryable?: boolean
  remediation?: string[]
  /** 界面段 key，如 `python` / `repository` / `dependency`。 */
  stage?: string
  runtimeMode?: RuntimeInitMode
}

/**
 * Runtime 链路下仍有镜像可换的段。
 *
 * Runtime 的镜像目录里 `python`（python-build-standalone）、`git` 与 `package-index` 三类
 * 对得上界面：依赖段的锁文件虽然冻结在 PyPI，但 Runtime 同步时会把锁副本里的下载地址改写到
 * 所选镜像（显式指定的排在尝试顺序最前，失败再逐个换源），所以依赖段也能换镜像。
 * `pip` / `git` 两段在 Runtime 下根本不执行，给「换镜像」按钮只会弹出空面板。
 */
const RUNTIME_MIRROR_STAGES = new Set(['python', 'repository', 'dependency'])

/** remediation 到界面动作的显式对应；这里没有的一律忽略。 */
const REMEDIATION_ACTIONS: Readonly<Record<string, FailureActionKind>> = {
  retry: 'retry',
  'retry-sync': 'retry',
  'restart-backend': 'retry',
  'retry-other-mirror': 'retry-other-mirror',
  'rebuild-environment': 'rebuild-environment',
  'open-log': 'open-log',
  'run-doctor': 'run-doctor',
}

/** 会真的再跑一次安装的动作，`retryable === false` 时全部屏蔽。 */
const RETRY_KINDS = new Set<FailureActionKind>([
  'retry',
  'retry-other-mirror',
  'rebuild-environment',
])

const ACTION_LABEL_KEYS: Readonly<Record<FailureActionKind, string>> = {
  retry: 'init.step.retry',
  'retry-other-mirror': 'init.failure.retryOtherMirror',
  'rebuild-environment': 'init.failure.rebuildEnvironment',
  'open-log': 'init.failure.openLog',
  'run-doctor': 'init.failure.runDoctor',
}

/** Runtime 自身的缺陷，重试多少次都是同一个结果。 */
const INTERNAL_ERROR_CODE = 'INTERNAL_ERROR'

function toAction(kind: FailureActionKind): FailureAction {
  return { kind, labelKey: ACTION_LABEL_KEYS[kind] }
}

function pushUnique(kinds: FailureActionKind[], kind: FailureActionKind): void {
  if (!kinds.includes(kind)) kinds.push(kind)
}

/** 旧链路的老样子：一个「用选中的镜像源重试」加一整块镜像面板。 */
function legacyPlan(): FailureActionPlan {
  return {
    actions: [{ kind: 'retry-other-mirror', labelKey: 'init.step.retryWithMirror' }],
    showMirrorSelection: true,
    notice: null,
    legacy: true,
  }
}

/**
 * 按失败结果里的机器字段决定失败态给哪些按钮。
 *
 * 纯函数，不碰 DOM 也不读全局状态，界面只负责渲染返回的动作列表并把点击接回对应通道。
 * 三条硬规则：
 * - `retryable === false` 不出任何重试类按钮，哪怕 remediation 里写了；
 * - `INTERNAL_ERROR` 一律按不可重试处理，只给日志和一句「请携带日志反馈」；
 * - 认不出来的 remediation 按协议要求忽略，一条都认不出来时退回旧链路的现有行为。
 */
export function decideFailureActions(context: FailureContext): FailureActionPlan {
  const remediation = context.remediation ?? []

  // 旧链路：既没有结果码也没有处置动作，什么都不改。
  if (!context.code && remediation.length === 0) {
    return legacyPlan()
  }

  const isInternalError = context.code === INTERNAL_ERROR_CODE
  const retryAllowed = context.retryable !== false && !isInternalError
  // 主进程没给模式（旧版本主进程）时按旧链路处理，镜像面板照常可用。
  const canSwitchMirror =
    context.runtimeMode === undefined ||
    context.runtimeMode === 'off' ||
    (context.stage !== undefined && RUNTIME_MIRROR_STAGES.has(context.stage))

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
    // 该段没有可换的镜像时降级成普通重试，免得弹出一个空的镜像面板。
    pushUnique(kinds, mapped === 'retry-other-mirror' && !canSwitchMirror ? 'retry' : mapped)
  }

  if (isInternalError) {
    notice = 'internal-error'
    pushUnique(kinds, 'open-log')
  }

  // 一条都没认出来（只给了未知 code、或 remediation 全是界面管不了的动作）。
  if (recognized === 0) {
    if (retryAllowed) return legacyPlan()
    return {
      actions: [toAction('open-log')],
      showMirrorSelection: false,
      notice: notice ?? 'contact-support',
      legacy: false,
    }
  }

  const allowed = retryAllowed ? kinds : kinds.filter(kind => !RETRY_KINDS.has(kind))
  // 重试全被屏蔽后可能一个按钮都不剩，日志任何时候都能打开，也是反馈时唯一有用的东西。
  if (allowed.length === 0) allowed.push('open-log')

  return {
    actions: allowed.map(toAction),
    showMirrorSelection: allowed.includes('retry-other-mirror'),
    notice,
    legacy: false,
  }
}

/**
 * 过滤「换镜像重试」的候选列表。
 *
 * Runtime 只收得下自己镜像目录里有对应源的那几个键，键名由主进程从 W9b 的映射表原样导出
 * （`mirrorKeys`），界面不自己抄一份。旧链路原样返回。
 */
export function filterRuntimeMirrors<T extends { key: string }>(
  mirrors: readonly T[],
  stage: string,
  runtimeMode: RuntimeInitMode | undefined,
  mirrorKeys: Readonly<Record<string, string[]>> | undefined
): T[] {
  if (runtimeMode === undefined || runtimeMode === 'off') return [...mirrors]

  const allowed = new Set(mirrorKeys?.[stage] ?? [])
  return mirrors.filter(mirror => allowed.has(mirror.key))
}
