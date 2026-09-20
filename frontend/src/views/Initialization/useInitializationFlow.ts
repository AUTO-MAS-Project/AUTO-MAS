import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { enterApp, forceEnterApp } from '@/utils/appEntry.ts'
import { getBackendVersion } from '@/composables/useVersionService'
import { decideFailureActions, filterRuntimeMirrors } from '@/utils/initializationDecision'
import {
  getInitializationStageKey,
  getInitializationStageStatus,
  initializationStages,
} from './initializationPresentation'
import {
  EMPTY_NETWORK_ACTIVITY,
  formatNetworkDetails,
  reduceNetworkActivity,
} from './networkActivity'
import type {
  ElectronMirrorSource,
  InstallStageResult,
  RuntimeDoctorCheck,
  RuntimeFailureFields,
  RuntimeInitMode,
} from '@/types/electron'
import type { LaunchStep } from '@/types/launch'
import type { MirrorConfig } from '@/types/mirror'
import type {
  FailureAction,
  FailureActionKind,
  FailureNoticeKind,
} from '@/utils/initializationDecision'
import type { InitializationStepKey, InitializationStepStatus } from './initializationPresentation'
import type {
  NetworkActivity,
  NetworkActivityPayload,
  NetworkDetailLabels,
} from './networkActivity'

export function useInitializationFlow() {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('初始化流程')

  interface StepDefinition {
    key: InitializationStepKey
    canSkip: boolean
  }

  interface StepState {
    status: InitializationStepStatus
    message: string
    progress: number
    progressIndeterminate: boolean
    showMirrorSelection: boolean
    mirrors: MirrorConfig[]
    selectedMirror: string
    failureActions: FailureAction[]
    failureNotice: FailureNoticeKind | null
    failureLogs: string
    failureLogPath: string
    doctorChecks: RuntimeDoctorCheck[] | null
    doctorRunning: boolean
  }

  interface ProgressPayload extends NetworkActivityPayload {
    stage?: string
    progress?: number
    message?: string
    status?: 'started' | 'running' | 'completed' | 'failed'
    indeterminate?: boolean
  }

  const steps: readonly StepDefinition[] = [
    { key: 'python', canSkip: false },
    { key: 'pip', canSkip: false },
    { key: 'git', canSkip: false },
    { key: 'repository', canSkip: true },
    { key: 'dependency', canSkip: true },
    { key: 'backend', canSkip: true },
  ]

  function createStepState(): StepState {
    return {
      status: 'waiting',
      message: '',
      progress: 0,
      progressIndeterminate: true,
      showMirrorSelection: false,
      mirrors: [],
      selectedMirror: '',
      failureActions: [],
      failureNotice: null,
      failureLogs: '',
      failureLogPath: '',
      doctorChecks: null,
      doctorRunning: false,
    }
  }

  const stepStates = ref<Record<InitializationStepKey, StepState>>({
    python: createStepState(),
    pip: createStepState(),
    git: createStepState(),
    repository: createStepState(),
    dependency: createStepState(),
    backend: createStepState(),
  })

  const currentStepIndex = ref(0)
  const runtimeMode = ref<RuntimeInitMode>('off')
  /** Runtime 报上来的测速结果与当前下载文件，只在 Runtime 链路有内容；页面级，不分段。 */
  const networkActivity = ref<NetworkActivity>(EMPTY_NETWORK_ACTIVITY)
  const runtimeMirrorKeys = ref<Record<string, string[]>>({})
  const runtimeFallbackLogPath = ref('')
  const flowKind = ref<'first-run' | 'update' | 'startup'>('first-run')

  const isDev = import.meta.env.DEV
  const version = import.meta.env.VITE_APP_VERSION
  const targetBranch = ref(isDev ? 'dev' : `release/${version}`)

  const RUNTIME_TAKEOVER_STEPS = new Set<InitializationStepKey>(['pip', 'git'])

  let initializationTimer: ReturnType<typeof setTimeout> | null = null

  const currentStep = computed(() => steps[currentStepIndex.value])
  const currentState = computed(() => stepStates.value[currentStep.value.key])
  const activeStageKey = computed(() => getInitializationStageKey(currentStep.value.key))
  const isBackendStep = computed(() => currentStep.value.key === 'backend')
  const hasFailed = computed(() => currentState.value.status === 'failed')

  const presentationStages = computed(() => {
    const statuses = Object.fromEntries(
      steps.map(step => [step.key, stepStates.value[step.key].status])
    ) as Record<InitializationStepKey, InitializationStepStatus>

    return initializationStages.map(stage => ({
      key: stage.key,
      status: getInitializationStageStatus(stage.key, statuses),
    }))
  })

  /**
   * 步骤条只在真的会跑安装的路径上出现。
   *
   * `startup` 是静默启动失败后回落到本页的路径，前五步在挂载时就被标成完成，
   * 这一趟一件都没做，画出来只是演一个没发生的过程。
   */
  const launchSteps = computed<LaunchStep[]>(() => {
    if (flowKind.value === 'startup') return []

    return presentationStages.value.map(stage => ({
      key: stage.key,
      label: t(`init.steps.${stage.key}`),
      state:
        stage.status === 'success'
          ? 'done'
          : stage.key === activeStageKey.value
            ? 'current'
            : 'todo',
    }))
  })

  const statusTitle = computed(() => {
    // 安装器和 Runtime 报上来的进度描述本身就是给人看的，有就直接用。
    if (currentState.value.status === 'processing' && currentState.value.message) {
      return currentState.value.message
    }
    if (flowKind.value === 'update') return t('launch.updating')
    return t('launch.preparing')
  })

  const statusHint = computed(() =>
    flowKind.value === 'startup' ? '' : t('launch.firstRunEstimate')
  )

  const statusProgress = computed(() =>
    currentState.value.progressIndeterminate ? undefined : currentState.value.progress
  )

  const networkDetailLabels: NetworkDetailLabels = {
    transferSource: source => t('launch.transferSource', { source }),
    probeUnavailable: source => t('launch.probeUnavailable', { source }),
  }

  /**
   * 进度条下面的网络细节，最多两行：测速时是「各源实测」+「最终顺序」，下载时是
   * 「文件名」+「已下载 / 总量 · 速度 · 来源」。
   *
   * 本次运行一次都没出现过细节（旧链路、旧版 Runtime、还没到有字段的阶段）时为 undefined，
   * LaunchStatus 不占位，界面与以前一致；出现过之后就一直交给它一个数组（哪怕为空），
   * 让两行的位置留着，细节出现和消失时步骤条不会上下跳。
   */
  const statusDetails = computed<string[] | undefined>(() => {
    if (runtimeMode.value === 'off') return undefined
    const lines = formatNetworkDetails(networkActivity.value, networkDetailLabels)
    if (lines === undefined) return undefined
    return currentState.value.status === 'processing' ? lines : []
  })

  const failureProps = computed(() => {
    const step = currentStep.value
    const state = currentState.value

    return {
      title: t(`init.steps.${activeStageKey.value}`),
      message: state.message,
      failureActions: state.failureActions,
      failureNotice: state.failureNotice,
      failureLogs: state.failureLogs,
      showMirrorSelection: state.showMirrorSelection,
      mirrors: filterRuntimeMirrors(
        state.mirrors,
        step.key,
        runtimeMode.value,
        runtimeMirrorKeys.value
      ),
      selectedMirror: state.selectedMirror,
      doctorChecks: state.doctorChecks,
      doctorRunning: state.doctorRunning,
      showSkipButton: step.canSkip,
    }
  })

  logger.info(`当前环境: ${isDev ? '开发环境' : '生产环境'}, 目标分支: ${targetBranch.value}`)

  function readProgressPayload(value: unknown): ProgressPayload {
    if (!value || typeof value !== 'object') return {}
    const raw = value as Record<string, unknown>
    return {
      stage: typeof raw.stage === 'string' ? raw.stage : undefined,
      progress: typeof raw.progress === 'number' ? raw.progress : undefined,
      message: typeof raw.message === 'string' ? raw.message : undefined,
      indeterminate: typeof raw.indeterminate === 'boolean' ? raw.indeterminate : undefined,
      status:
        raw.status === 'started' ||
        raw.status === 'running' ||
        raw.status === 'completed' ||
        raw.status === 'failed'
          ? raw.status
          : undefined,
      runtimeStage: typeof raw.runtimeStage === 'string' ? raw.runtimeStage : undefined,
      runtimeStatus: typeof raw.runtimeStatus === 'string' ? raw.runtimeStatus : undefined,
      item: typeof raw.item === 'string' ? raw.item : undefined,
      source: typeof raw.source === 'string' ? raw.source : undefined,
      bytesPerSecond: typeof raw.bytesPerSecond === 'number' ? raw.bytesPerSecond : undefined,
      current: typeof raw.current === 'number' ? raw.current : undefined,
      total: typeof raw.total === 'number' ? raw.total : undefined,
    }
  }

  function handleProgress(stepKey: InitializationStepKey, value: unknown) {
    const state = stepStates.value[stepKey]
    const progress = readProgressPayload(value)
    const previousStatus = state.status
    const previousMessage = state.message
    networkActivity.value = reduceNetworkActivity(networkActivity.value, progress)

    if (progress.status === 'completed' || (progress.progress ?? 0) >= 100) {
      state.status = 'success'
      state.message = progress.message || ''
      state.progress = 100
      state.progressIndeterminate = false
    } else if (progress.status === 'failed') {
      state.status = 'failed'
      state.message = progress.message || t('init.msg.execFailed')
      state.progressIndeterminate = false
    } else {
      state.status = 'processing'
      state.message = progress.message || ''
      // 旧安装器切换阶段时会发送 0，保留已经展示的进度。
      if (progress.progress !== undefined && (progress.progress > 0 || state.progress === 0)) {
        state.progress = Math.min(100, Math.max(0, Math.round(progress.progress)))
      }
      state.progressIndeterminate = progress.indeterminate ?? progress.progress === undefined
    }

    if (previousStatus !== state.status || previousMessage !== state.message) {
      logger.info(`[${stepKey}] ${state.message || state.status}`)
    }
  }

  function applyFailure(
    state: StepState,
    stepKey: InitializationStepKey,
    failure: RuntimeFailureFields
  ) {
    const plan = decideFailureActions({
      code: failure.code,
      retryable: failure.retryable,
      remediation: failure.remediation,
      stage: stepKey,
      runtimeMode: runtimeMode.value,
    })

    state.failureActions = plan.actions
    state.failureNotice = plan.notice
    state.showMirrorSelection = plan.showMirrorSelection
    state.failureLogs = failure.logs ?? ''
    state.failureLogPath = failure.logPath ?? ''
    state.doctorChecks = null
    state.doctorRunning = false

    logger.info(
      `[${stepKey}] 失败处置 - code: ${failure.code ?? '无'}, retryable: ${failure.retryable ?? '无'}, ` +
        `动作: ${plan.actions.map(action => action.kind).join(', ') || '无'}`
    )
    return plan
  }

  function markStepTakenOver(state: StepState) {
    state.status = 'success'
    state.message = ''
    state.progress = 100
    state.progressIndeterminate = false
    state.showMirrorSelection = false
    state.failureActions = []
    state.failureNotice = null
  }

  function handleRuntimeInitializationProgress(progress: {
    stage: string
    progress: number
    message: string
    status?: 'started' | 'running' | 'completed' | 'failed'
  }) {
    if (progress.stage === 'mirror' || progress.stage === 'complete') return
    if (!steps.some(step => step.key === progress.stage)) return

    const stepKey = progress.stage as InitializationStepKey
    if (stepKey === 'backend' || RUNTIME_TAKEOVER_STEPS.has(stepKey)) return

    currentStepIndex.value = steps.findIndex(step => step.key === stepKey)
    handleProgress(stepKey, progress)
  }

  function markStepFailed(
    stepKey: InitializationStepKey,
    errorMessage: string,
    failure: RuntimeFailureFields
  ) {
    const state = stepStates.value[stepKey]
    state.status = 'failed'
    state.message = errorMessage
    logger.error(`步骤 ${stepKey} 失败: ${errorMessage}`)

    applyFailure(state, stepKey, failure)
  }

  async function executeRuntimeInitialization(): Promise<boolean> {
    try {
      const result = await window.electronAPI.initialize(targetBranch.value, false)

      if (!result.success) {
        const failedStep = steps.find(
          step => step.key === result.failedStage && !RUNTIME_TAKEOVER_STEPS.has(step.key)
        )
        const failedStepKey = failedStep?.key ?? 'python'
        currentStepIndex.value = steps.findIndex(step => step.key === failedStepKey)
        markStepFailed(failedStepKey, result.error || t('init.msg.execFailed'), result)
        return false
      }

      for (const step of steps.slice(0, -1)) {
        const state = stepStates.value[step.key]
        state.status = 'success'
        state.progress = 100
        state.progressIndeterminate = false
      }

      currentStepIndex.value = steps.length - 1
      logger.info('Runtime bootstrap 完成，准备启动后端')
      return true
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      currentStepIndex.value = 0
      markStepFailed('python', errorMessage, {})
      return false
    }
  }

  function isRuntimeTakenOver(stepKey: InitializationStepKey): boolean {
    return runtimeMode.value !== 'off' && RUNTIME_TAKEOVER_STEPS.has(stepKey)
  }

  async function executeStep(stepKey: InitializationStepKey, rebuild = false): Promise<boolean> {
    const state = stepStates.value[stepKey]

    if (isRuntimeTakenOver(stepKey)) {
      markStepTakenOver(state)
      return true
    }

    state.status = 'processing'
    state.message = ''
    state.progress = 0
    state.progressIndeterminate = true
    networkActivity.value = EMPTY_NETWORK_ACTIVITY
    let failure: RuntimeFailureFields = {}

    try {
      const api = window.electronAPI
      let result: InstallStageResult

      switch (stepKey) {
        case 'python':
          result = await api.installPython(state.selectedMirror, rebuild)
          break
        case 'pip':
          result = await api.installPip(state.selectedMirror, rebuild)
          break
        case 'git':
          result = await api.installGit(state.selectedMirror, rebuild)
          break
        case 'repository':
          result = await api.pullRepository(targetBranch.value, state.selectedMirror, rebuild)
          break
        case 'dependency':
          result = await api.installDependencies(state.selectedMirror, rebuild)
          break
        case 'backend':
          return true
      }

      if (!result.success) {
        failure = result
        throw new Error(result.error || t('init.msg.execFailed'))
      }

      state.status = 'success'
      state.message = ''
      logger.info(`步骤 ${stepKey} 完成`)
      return true
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      markStepFailed(stepKey, errorMessage, failure)
      return false
    }
  }

  async function startInitialization(startIndex = 0) {
    logger.info('开始初始化流程')

    try {
      if (runtimeMode.value !== 'off' && startIndex === 0) {
        const success = await executeRuntimeInitialization()
        if (!success) logger.warn('Runtime 初始化失败，等待用户处理')
        return
      }

      for (let index = startIndex; index < steps.length; index += 1) {
        const step = steps[index]
        currentStepIndex.value = index
        if (!(await executeStep(step.key))) return
      }

      logger.info('初始化准备完成，等待后端启动')
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.error(`初始化失败: ${errorMessage}`)
      message.error(t('init.msg.initFailed'))
    }
  }

  function handleMirrorSelect(mirrorKey: string) {
    currentState.value.selectedMirror = mirrorKey
  }

  function resetFailureState(state: StepState) {
    state.showMirrorSelection = false
    state.failureActions = []
    state.failureNotice = null
    state.failureLogs = ''
    state.doctorChecks = null
  }

  async function continueAfterCurrentStep() {
    for (let index = currentStepIndex.value + 1; index < steps.length; index += 1) {
      currentStepIndex.value = index
      if (!(await executeStep(steps[index].key))) return false
    }
    return true
  }

  async function handleSkip() {
    const step = currentStep.value
    const state = stepStates.value[step.key]

    state.status = 'success'
    state.message = ''
    resetFailureState(state)
    message.warning(t('init.msg.skippedStep', { step: t(`init.steps.${activeStageKey.value}`) }))

    if (step.key === 'backend') {
      await handleLocalEnterApp()
      return
    }

    if (await continueAfterCurrentStep()) logger.info('跳过当前阶段后，初始化流程继续完成')
  }

  async function handleRetry(rebuild = false) {
    const step = currentStep.value
    const state = stepStates.value[step.key]
    resetFailureState(state)

    logger.info(`重试 ${step.key}${rebuild ? '（重建环境）' : ''}`)
    if (await executeStep(step.key, rebuild)) await continueAfterCurrentStep()
  }

  function handleBackendStatusChange(
    status: 'waiting' | 'starting' | 'running' | 'success' | 'failed'
  ) {
    stepStates.value.backend.status =
      status === 'starting' || status === 'running' ? 'processing' : status
  }

  async function handleBackendComplete() {
    const state = stepStates.value.backend
    state.status = 'success'
    state.message = ''

    message.success(t('init.msg.initDone'))
    await window.electronAPI.setInitializedVersion?.(version)
    await getBackendVersion()
    await handleLocalEnterApp()
  }

  async function handleBackendError(errorMessage: string, failure: RuntimeFailureFields = {}) {
    const state = stepStates.value.backend
    state.status = 'failed'
    state.message = errorMessage

    if (
      runtimeMode.value !== 'off' &&
      (failure.code === 'DEPENDENCY_SYNC_FAILED' || failure.code === 'ENVIRONMENT_BROKEN')
    ) {
      // 启动时应用后台更新也可能需要修复依赖，复用安装阶段的失败处置。
      state.status = 'waiting'
      currentStepIndex.value = steps.findIndex(step => step.key === 'dependency')
      markStepFailed('dependency', errorMessage, failure)
      await loadMirrorConfigs()
    }
  }

  async function handleFailureAction(kind: FailureActionKind) {
    const state = currentState.value

    switch (kind) {
      case 'open-log':
        await openFailureLog(state)
        return
      case 'run-doctor':
        await runRuntimeDoctor(state)
        return
      case 'retry':
      case 'retry-other-mirror':
        await handleRetry(false)
        return
      case 'rebuild-environment':
        await handleRetry(true)
        return
    }
  }

  async function openFailureLog(state: StepState) {
    const target = state.failureLogPath || runtimeFallbackLogPath.value
    if (!target) {
      message.error(t('init.failure.openLogFailed', { error: t('init.msg.execFailed') }))
      return
    }

    try {
      const result = await window.electronAPI.openFile(target)
      if (!result.success) {
        message.error(
          t('init.failure.openLogFailed', { error: result.error ?? t('init.msg.execFailed') })
        )
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      message.error(t('init.failure.openLogFailed', { error: errorMessage }))
    }
  }

  async function runRuntimeDoctor(state: StepState) {
    state.doctorRunning = true
    try {
      const result = await window.electronAPI.checkCriticalFiles()
      state.doctorChecks = result.runtimeChecks ?? []
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      message.error(t('init.failure.doctorFailed', { error: errorMessage }))
      state.doctorChecks = []
    } finally {
      state.doctorRunning = false
    }
  }

  async function handleLocalEnterApp() {
    try {
      const success = await enterApp('初始化完成后进入', true)
      if (!success) await forceEnterApp('初始化完成后强制进入')
    } catch {
      await forceEnterApp('初始化失败后强制进入')
    }
  }

  function convertMirror(mirror: ElectronMirrorSource): MirrorConfig {
    return {
      key: mirror.name,
      name: mirror.name,
      url: mirror.url,
      type: mirror.type,
      description: mirror.description,
      recommended: mirror.type === 'mirror',
    }
  }

  async function loadMirrorConfigs() {
    const api = window.electronAPI
    try {
      await api.initMirrors()
      const [pythonMirrors, getPipMirrors, gitMirrors, repoMirrors, pipMirrors] = await Promise.all(
        [
          api.getMirrors('python'),
          api.getMirrors('get_pip'),
          api.getMirrors('git'),
          api.getMirrors('repo'),
          api.getMirrors('pip_mirror'),
        ]
      )

      stepStates.value.python.mirrors = pythonMirrors.map(convertMirror)
      stepStates.value.pip.mirrors = getPipMirrors.map(convertMirror)
      stepStates.value.git.mirrors = gitMirrors.map(convertMirror)
      stepStates.value.repository.mirrors = repoMirrors.map(convertMirror)
      stepStates.value.dependency.mirrors = pipMirrors.map(convertMirror)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.warn(`加载镜像源配置失败，将使用默认配置: ${errorMessage}`)
    }
  }

  function markStepsBefore(startIndex: number) {
    for (let index = 0; index < startIndex; index += 1) {
      markStepTakenOver(stepStates.value[steps[index].key])
    }
  }

  async function resolveStartIndex(): Promise<number> {
    const api = window.electronAPI
    const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
    if (forceBackendUpdate) {
      sessionStorage.removeItem('forceBackendUpdate')
      flowKind.value = 'update'
      markStepsBefore(3)
      return 3
    }

    let autoUpdate = false
    try {
      const config = await api.loadConfig?.()
      autoUpdate = config?.Update?.IfAutoUpdate === true
    } catch {
      logger.warn('读取自动更新配置失败，执行完整初始化')
    }

    if (autoUpdate) {
      flowKind.value = 'update'
      return 0
    }

    const savedVersion = await api.getInitializedVersion?.()
    if (savedVersion === version) {
      flowKind.value = 'startup'
      markStepsBefore(steps.length - 1)
      return steps.length - 1
    }

    flowKind.value = savedVersion ? 'update' : 'first-run'
    return 0
  }

  onMounted(async () => {
    logger.info('初始化界面已加载')

    if (isDev) {
      await handleLocalEnterApp()
      return
    }

    const api = window.electronAPI
    try {
      const context = await api.getRuntimeInitContext?.()
      if (context) {
        runtimeMode.value = context.mode
        runtimeMirrorKeys.value = context.mirrorKeys ?? {}
        runtimeFallbackLogPath.value = context.fallbackLogPath ?? ''
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.warn(`读取 Runtime 上下文失败，回退兼容链路: ${errorMessage}`)
    }

    if (runtimeMode.value !== 'off') {
      for (const stepKey of RUNTIME_TAKEOVER_STEPS) markStepTakenOver(stepStates.value[stepKey])
    }

    const startIndex = await resolveStartIndex()
    currentStepIndex.value = startIndex

    // 已完成过同版本初始化时只启动后端，不再为不会执行的安装步骤加载镜像配置。
    if (startIndex < steps.length - 1) await loadMirrorConfigs()

    api.onPythonProgress?.(progress => handleProgress('python', progress))
    api.onPipProgress?.(progress => handleProgress('pip', progress))
    api.onGitProgress?.(progress => handleProgress('git', progress))
    api.onRepositoryProgress?.(progress => handleProgress('repository', progress))
    api.onDependencyProgress?.(progress => handleProgress('dependency', progress))
    api.onInitializationProgress?.(handleRuntimeInitializationProgress)
    api.onBackendStatus?.(backendStatus => {
      if (backendStatus.isRunning) stepStates.value.backend.status = 'processing'
    })

    if (startIndex < steps.length - 1) {
      initializationTimer = setTimeout(() => {
        void startInitialization(startIndex)
      }, 400)
    }
  })

  onUnmounted(() => {
    if (initializationTimer) clearTimeout(initializationTimer)

    const api = window.electronAPI
    api.removePythonProgressListener?.()
    api.removePipProgressListener?.()
    api.removeGitProgressListener?.()
    api.removeRepositoryProgressListener?.()
    api.removeDependencyProgressListener?.()
    api.removeInitializationProgressListener?.()
    api.removeBackendStatusListener?.()
  })

  return {
    currentStep,
    failureProps,
    flowKind,
    handleBackendComplete,
    handleBackendError,
    handleBackendStatusChange,
    handleFailureAction,
    handleMirrorSelect,
    handleSkip,
    hasFailed,
    isBackendStep,
    launchSteps,
    statusDetails,
    statusHint,
    statusProgress,
    statusTitle,
  }
}
