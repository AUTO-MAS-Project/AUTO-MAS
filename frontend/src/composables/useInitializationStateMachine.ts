import { computed, ref, type Ref } from 'vue'
import type { MirrorConfig } from '@/types/mirror'

/**
 * 初始化页步骤状态机。
 *
 * 状态：waiting -> running -> success | failure -> retry -> running ...
 *                                  -> skipped
 *
 * Lane 8 要求：每步显示 running/success/failure/skipped/retry，失败不得只给"请选择镜像源"。
 * 因此失败状态携带结构化 failureDetails，包含后端返回的具体错误、阶段、镜像源和可执行建议。
 */

export type InitStepStatus =
  | 'waiting'
  | 'processing'
  | 'running'
  | 'success'
  | 'failed'
  | 'failure'
  | 'skipped'
  | 'retry'

export interface InitStepFailureDetails {
  /** 后端返回的具体错误，原样保留 */
  reason: string
  /** 失败阶段：download / install / deploy / check / network / unknown */
  stage: string
  /** 最后尝试的镜像源名称 */
  mirrorTried?: string
  /** 镜像源尝试进度 */
  mirrorProgress?: { current: number; total: number }
  /** 可执行建议（基于 stepKey + reason 推断） */
  suggestion: string
  /** 已经重试的次数（不含当前这次） */
  retryCount: number
  /** 最后一次失败时间（ISO 字符串） */
  lastAttemptAt: string
}

/**
 * Lane 8：插件版本锁冲突结构化展示。
 *
 * installPluginBootstrap 返回 warnings 数组，其中 kind=version-mismatch 携带
 * packageName（含 requested specifier）与 message（含 installed version）。
 * 前端需要将其解析成 distribution / locked / requested / installed 四元组，
 * 并给出可执行建议，不得吞掉后端错误。
 */
export interface PluginVersionConflict {
  /** 分发包名，例如 auto-mas-core */
  distribution: string
  /**
   * 锁定版本（来自 plugins/wheels/runtime-lock.json）。
   * 当前 Electron API 未直接暴露 runtime-lock，故为 null 时表示未提供，
   * 并提示用户参考本地 runtime-lock.json。
   */
  locked: string | null
  /** 请求的版本范围（来自 declared package specifier，例如 >=6.0.0a1） */
  requested: string
  /** 实际安装版本（从 warning message 解析；解析失败时为 null） */
  installed: string | null
  /** 警告类型 */
  kind: 'install-failed' | 'missing-entry-point' | 'version-mismatch'
  /** 原始后端消息，原样保留供诊断 */
  rawMessage: string
  /** 可执行建议 */
  suggestion: string
}

/** 与 Electron 服务 PluginBootstrapWarning 接口对齐 */
export interface PluginBootstrapWarningLike {
  packageName: string
  message: string
  kind: 'install-failed' | 'missing-entry-point' | 'version-mismatch' | string
}

export interface InitStepCheckInfo {
  exeExists?: boolean
  canRun?: boolean
  version?: string
  exists?: boolean
  isGitRepo?: boolean
  isHealthy?: boolean
  currentBranch?: string
  requirementsExists?: boolean
  needsInstall?: boolean
}

export interface InitStepState {
  status: InitStepStatus
  message: string
  progress: number
  mirrors: MirrorConfig[]
  selectedMirror: string
  countdown: number
  currentMirror: string
  downloadSpeed: string
  downloadSize: string
  installMessage: string
  installProgress: number
  deployMessage: string
  deployProgress: number
  operationDesc: string
  checkInfo?: InitStepCheckInfo
  mirrorProgress?: { current: number; total: number }
  failureDetails?: InitStepFailureDetails
  /** Lane 8：插件安装步骤的原始 warnings（来自 installPluginBootstrap） */
  pluginWarnings?: PluginBootstrapWarningLike[]
  /** Lane 8：解析后的版本锁冲突结构化列表 */
  pluginVersionConflicts?: PluginVersionConflict[]
}

const STEP_LABELS: Record<string, string> = {
  python: 'Python 安装',
  pip: 'Pip 安装',
  git: 'Git 安装',
  repository: '源码拉取',
  dependency: '依赖安装',
  'plugin-bootstrap': '插件安装',
  backend: '后端启动',
}

/**
 * 根据失败原因生成可执行建议。不得返回空字符串或"请选择镜像源"。
 */
export function buildSuggestion(
  stepKey: string,
  reason: string,
  mirrorProgress?: { current: number; total: number }
): string {
  const lower = reason.toLowerCase()
  const stepLabel = STEP_LABELS[stepKey] || '当前步骤'

  // 网络类
  if (
    lower.includes('network') ||
    lower.includes('timeout') ||
    lower.includes('超时') ||
    lower.includes('etimedout') ||
    lower.includes('econnreset') ||
    lower.includes('econnrefused') ||
    lower.includes('enotfound')
  ) {
    return `网络连接异常导致${stepLabel}失败。请检查代理/防火墙设置，或在失败面板切换镜像源后重试。`
  }

  // 镜像源耗尽
  if (
    mirrorProgress &&
    typeof mirrorProgress.total === 'number' &&
    mirrorProgress.total > 0 &&
    mirrorProgress.current >= mirrorProgress.total
  ) {
    return `已尝试全部 ${mirrorProgress.total} 个镜像源均失败。请检查网络后重试，或联系维护者并提供下方完整错误日志。`
  }

  // 权限类
  if (
    lower.includes('permission') ||
    lower.includes('eacces') ||
    lower.includes('eparm') ||
    lower.includes('拒绝访问') ||
    lower.includes('权限')
  ) {
    return `${stepLabel}因权限不足失败。请以管理员身份运行 AUTO-MAS，或检查目标目录写入权限。`
  }

  // 磁盘空间
  if (lower.includes('enospc') || lower.includes('no space') || lower.includes('磁盘')) {
    return `${stepLabel}因磁盘空间不足失败。请清理目标盘符后重试。`
  }

  // 已存在的进程/文件占用
  if (lower.includes('ebusy') || lower.includes('被占用') || lower.includes('locked')) {
    return `${stepLabel}因文件被占用失败。请关闭相关进程（如已运行的 Python/Git）后重试。`
  }

  // 后端启动失败
  if (stepKey === 'backend') {
    return `后端启动失败。请截图下方完整日志并参考文档，或点击"查看文档"获取排查指引。`
  }

  // 仓库相关
  if (stepKey === 'repository') {
    if (
      lower.includes('not a git repo') ||
      lower.includes('authentication') ||
      lower.includes('auth')
    ) {
      return `源码拉取失败：仓库鉴权或本地 Git 状态异常。请检查 Git 凭据，或删除本地仓库目录后重试。`
    }
    return `源码拉取失败。请在失败面板切换镜像源后重试；若仍失败请检查目标目录的 Git 状态。`
  }

  // 依赖安装
  if (stepKey === 'dependency' || stepKey === 'pip') {
    if (lower.includes('nomatching') || lower.includes('no matching distribution')) {
      return `依赖安装失败：找不到匹配的 wheel 包。请确认 Python 版本符合要求，或切换镜像源后重试。`
    }
    return `依赖安装失败。请在失败面板切换镜像源后重试；若仍失败请检查 Python 版本与网络。`
  }

  // Python/Git 安装包下载
  if (stepKey === 'python' || stepKey === 'git') {
    return `${stepLabel}失败。请在失败面板切换镜像源后重试；若仍失败请检查网络连接。`
  }

  // 插件安装
  if (stepKey === 'plugin-bootstrap') {
    return `插件安装失败。请在失败面板切换镜像源后重试；若仍失败请检查 PyPI 镜像源可用性。`
  }

  return `${stepLabel}失败：${reason || '未知错误'}。请在失败面板切换镜像源后重试，或联系维护者。`
}

/**
 * 从原始错误消息中推断失败阶段。
 */
export function inferFailureStage(reason: string): string {
  const lower = reason.toLowerCase()
  if (lower.includes('download') || lower.includes('下载')) return 'download'
  if (lower.includes('install') || lower.includes('安装')) return 'install'
  if (lower.includes('deploy') || lower.includes('部署')) return 'deploy'
  if (lower.includes('check') || lower.includes('检查')) return 'check'
  if (
    lower.includes('network') ||
    lower.includes('timeout') ||
    lower.includes('超时') ||
    lower.includes('econnreset') ||
    lower.includes('etimedout')
  ) {
    return 'network'
  }
  return 'unknown'
}

/**
 * Lane 8：从 declared package displayLabel 中解析 distribution 与 requested specifier。
 *
 * displayLabel 形如：
 *   "auto-mas-core>=6.0.0a1"
 *   "automas-plugin-browser>=0.1.0"
 *   "some-pkg==1.2.3"
 *   "some-pkg"  (无 specifier)
 *
 * 注意：包名可能包含连字符； specifier 起始字符为 < > = ! ~ 之一。
 */
export function parseDistributionAndRequested(displayLabel: string): {
  distribution: string
  requested: string
} {
  if (!displayLabel || typeof displayLabel !== 'string') {
    return { distribution: '', requested: '' }
  }
  const match = displayLabel.match(/^([A-Za-z0-9][A-Za-z0-9._-]*?)\s*([<>=!~].*)?$/)
  if (!match) {
    return { distribution: displayLabel.trim(), requested: '' }
  }
  return {
    distribution: match[1] || displayLabel.trim(),
    requested: (match[2] || '').trim(),
  }
}

/**
 * Lane 8：从 version-mismatch warning message 中提取实际安装版本。
 *
 * Electron 服务生成的消息形如：
 *   "Installed version 6.0.0a1 does not satisfy auto-mas-core>=6.0.0a1"
 *   "Installed version unknown does not satisfy auto-mas-core>=6.0.0a1"
 *
 * 当 installed 为 "unknown" 或无法解析时返回 null。
 */
export function parseInstalledVersionFromMessage(message: string): string | null {
  if (!message || typeof message !== 'string') return null
  const match = message.match(/Installed version\s+(\S+)\s+does not satisfy/i)
  if (!match) return null
  const raw = match[1]
  if (!raw || raw.toLowerCase() === 'unknown') return null
  return raw
}

/**
 * 解析 Electron 锁定 wheel 契约与插件声明直接冲突的错误。
 *
 * 示例：
 * Locked plugin automas_plugin_maaend_adapter==0.0.4 violates
 * automas_plugin_maaend_adapter==0.0.3
 */
export function parseLockedPluginConflict(message: string): PluginVersionConflict | null {
  if (!message || typeof message !== 'string') return null
  const match = message.match(
    /Locked plugin\s+([A-Za-z0-9_.-]+)==([^\s]+)\s+violates\s+([A-Za-z0-9_.-]+)([^\s]*)/i
  )
  if (!match) return null

  const distribution = match[1]
  const locked = match[2]
  const requestedDistribution = match[3]
  const requested = match[4] || ''
  const normalizeDistribution = (value: string) => value.toLowerCase().replace(/[-_.]+/g, '-')
  if (normalizeDistribution(requestedDistribution) !== normalizeDistribution(distribution)) {
    return null
  }

  const conflict: Omit<PluginVersionConflict, 'suggestion'> = {
    distribution,
    locked,
    requested,
    installed: null,
    kind: 'version-mismatch',
    rawMessage: message,
  }
  return {
    ...conflict,
    suggestion: buildVersionConflictSuggestion(conflict),
  }
}

/**
 * Lane 8：为版本锁冲突生成可执行建议。不得返回空字符串。
 */
export function buildVersionConflictSuggestion(
  conflict: Omit<PluginVersionConflict, 'suggestion'>
): string {
  const { distribution, locked, requested, installed, kind, rawMessage } = conflict

  if (kind === 'install-failed') {
    return `${distribution} 安装失败：${rawMessage}。请检查网络/镜像源可用性，或在失败面板切换镜像源后重试；若仍失败请提供完整日志并联系维护者。`
  }

  if (kind === 'missing-entry-point') {
    return `${distribution} 已安装但缺少 auto_mas.plugins / automas.plugins 入口点。请确认 wheel 包完整；若使用自定义构建，请检查 setup.py / pyproject.toml 中的 entry_points 声明。`
  }

  // version-mismatch
  const parts: string[] = []
  if (installed && requested) {
    parts.push(`当前已安装 ${installed}，但声明要求 ${requested}`)
  } else if (requested) {
    parts.push(`声明要求 ${requested}`)
  }
  if (locked) {
    parts.push(`运行时锁指定 ${locked}`)
  }
  const summary = parts.length > 0 ? `（${parts.join('；')}）` : ''

  if (locked && requested.startsWith('==') && requested !== `==${locked}`) {
    return `${distribution} 的运行时锁 ${locked} 与插件声明 ${requested} 相互冲突${summary}。切换镜像源或重复安装无法解决；请由维护者统一 plugins/wheels/runtime-lock.json、wheelhouse 与插件声明后重新打包。`
  }

  if (locked) {
    return `${distribution} 版本不匹配${summary}。建议删除 plugins/pypi/site-packages 下对应目录后重新启动初始化，让 Electron 服务按 runtime-lock.json 重新安装锁定版本。`
  }
  return `${distribution} 版本不匹配${summary}。建议删除 plugins/pypi/site-packages 下对应目录后重新启动初始化；若问题持续，请检查 plugins/wheels/runtime-lock.json 与 pyproject.toml 中的 [tool.auto_mas.bootstrap] 声明是否一致。`
}

/**
 * Lane 8：将 Electron installPluginBootstrap 返回的 warnings 数组解析为
 * 结构化 PluginVersionConflict 列表。
 *
 * 当前 Electron API 未直接暴露 runtime-lock.json 内容到前端，
 * 因此 locked 字段为 null，并在建议中提示用户参考本地 runtime-lock.json。
 * 若未来 Lane 01 暴露了 runtime-lock 读取接口，可在此处补充。
 */
export function parsePluginWarnings(
  warnings: PluginBootstrapWarningLike[] | undefined | null
): PluginVersionConflict[] {
  if (!warnings || !Array.isArray(warnings) || warnings.length === 0) {
    return []
  }

  return warnings.map(w => {
    const { distribution, requested } = parseDistributionAndRequested(w.packageName)
    const installed = parseInstalledVersionFromMessage(w.message)
    const conflict: Omit<PluginVersionConflict, 'suggestion'> = {
      distribution: distribution || w.packageName,
      // 当前未暴露 runtime-lock 到前端；保持 null 以避免编造数据
      locked: null,
      requested,
      installed,
      kind: (['install-failed', 'missing-entry-point', 'version-mismatch'].includes(w.kind)
        ? w.kind
        : 'version-mismatch') as PluginVersionConflict['kind'],
      rawMessage: w.message,
    }
    return {
      ...conflict,
      suggestion: buildVersionConflictSuggestion(conflict),
    }
  })
}

export function createInitialStepState(): InitStepState {
  return {
    status: 'waiting',
    message: '',
    progress: 0,
    mirrors: [],
    selectedMirror: '',
    countdown: 0,
    currentMirror: '',
    downloadSpeed: '',
    downloadSize: '',
    installMessage: '',
    installProgress: 0,
    deployMessage: '',
    deployProgress: 0,
    operationDesc: '',
  }
}

export function transitionToRunning(state: InitStepState, message = '正在执行...'): InitStepState {
  return {
    ...state,
    status: 'running',
    message,
    progress: state.progress > 0 ? state.progress : 0,
    countdown: 0,
  }
}

export function transitionToSuccess(state: InitStepState, message = '阶段完成'): InitStepState {
  return {
    ...state,
    status: 'success',
    message,
    progress: 100,
    countdown: 0,
    currentMirror: '',
    downloadSpeed: '',
    downloadSize: '',
    installMessage: '',
    installProgress: 0,
    deployMessage: '',
    deployProgress: 0,
    operationDesc: '',
    failureDetails: undefined,
    // Lane 8：成功时保留 pluginWarnings/pluginVersionConflicts 以便用户查看
    // 后端可能 success=true 但仍带 warnings（非致命警告）。
  }
}

export function transitionToFailure(
  state: InitStepState,
  reason: string,
  opts: {
    stepKey: string
    mirrorTried?: string
    mirrorProgress?: { current: number; total: number }
    /**
     * Lane 8：插件安装步骤可传入 warnings 数组，解析为结构化版本冲突。
     * 仅在 stepKey === 'plugin-bootstrap' 时生效；其他步骤忽略。
     */
    pluginWarnings?: PluginBootstrapWarningLike[]
  }
): InitStepState {
  const stage = inferFailureStage(reason)
  const suggestion = buildSuggestion(opts.stepKey, reason, opts.mirrorProgress)
  const prevRetryCount = state.failureDetails?.retryCount ?? 0

  // Lane 8：解析插件版本锁冲突
  let pluginVersionConflicts = state.pluginVersionConflicts
  if (opts.stepKey === 'plugin-bootstrap') {
    const warningConflicts = parsePluginWarnings(opts.pluginWarnings)
    const lockedConflict = parseLockedPluginConflict(reason)
    pluginVersionConflicts = lockedConflict
      ? [
          ...warningConflicts.filter(
            conflict =>
              conflict.distribution.toLowerCase().replace(/[-_.]+/g, '-') !==
              lockedConflict.distribution.toLowerCase().replace(/[-_.]+/g, '-')
          ),
          lockedConflict,
        ]
      : warningConflicts.length > 0
        ? warningConflicts
        : state.pluginVersionConflicts
  }

  return {
    ...state,
    status: 'failure',
    message: reason,
    progress: state.progress,
    countdown: 0,
    failureDetails: {
      reason,
      stage,
      mirrorTried: opts.mirrorTried,
      mirrorProgress: opts.mirrorProgress,
      suggestion,
      retryCount: prevRetryCount,
      lastAttemptAt: new Date().toISOString(),
    },
    pluginWarnings: opts.pluginWarnings ?? state.pluginWarnings,
    pluginVersionConflicts,
  }
}

export function transitionToSkipped(state: InitStepState): InitStepState {
  return {
    ...state,
    status: 'skipped',
    message: '已跳过',
    progress: 100,
    countdown: 0,
    currentMirror: '',
    downloadSpeed: '',
    downloadSize: '',
    installMessage: '',
    installProgress: 0,
    deployMessage: '',
    deployProgress: 0,
    operationDesc: '',
  }
}

export function transitionToRetry(state: InitStepState): InitStepState {
  const retryCount = state.failureDetails?.retryCount ?? 0
  return {
    ...state,
    status: 'retry',
    message: `正在重试（第 ${retryCount + 1} 次）...`,
    countdown: 0,
    failureDetails: state.failureDetails
      ? {
          ...state.failureDetails,
          retryCount: retryCount + 1,
        }
      : undefined,
  }
}

/**
 * 计数：当前所有步骤中处于 failure 的数量。
 */
export function countFailedSteps(states: Record<string, InitStepState>): number {
  return Object.values(states).filter(s => s.status === 'failure').length
}

/**
 * 计数：当前所有步骤中处于 skipped 的数量。
 */
export function countSkippedSteps(states: Record<string, InitStepState>): number {
  return Object.values(states).filter(s => s.status === 'skipped').length
}

/**
 * 提供响应式的初始化步骤状态机容器，便于 Vue 组件绑定。
 * 内部仍以纯函数 transition* 完成状态转移，方便单元测试。
 */
export function useInitializationStateMachine(stepKeys: string[]) {
  const steps = ref<Record<string, InitStepState>>(
    Object.fromEntries(stepKeys.map(key => [key, createInitialStepState()]))
  ) as Ref<Record<string, InitStepState>>

  const failedCount = computed(() => countFailedSteps(steps.value))
  const skippedCount = computed(() => countSkippedSteps(steps.value))

  const setStep = (key: string, next: InitStepState) => {
    steps.value = { ...steps.value, [key]: next }
  }

  const reset = () => {
    steps.value = Object.fromEntries(stepKeys.map(key => [key, createInitialStepState()]))
  }

  return {
    steps,
    failedCount,
    skippedCount,
    setStep,
    reset,
    // 暴露纯函数方便组件直接调用
    transitionToRunning,
    transitionToSuccess,
    transitionToFailure,
    transitionToSkipped,
    transitionToRetry,
  }
}
