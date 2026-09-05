import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { enterApp, forceEnterApp } from '@/utils/appEntry.ts'
import { getBackendVersion } from '@/composables/useVersionService'
import { decideFailureActions, filterRuntimeMirrors } from '@/utils/initializationDecision'
import {
  formatElapsedSeconds,
  getInitializationStageKey,
  getInitializationStageStatus,
  initializationStages,
} from './initializationPresentation'
import type {
  ElectronMirrorSource,
  InstallStageResult,
  RuntimeDoctorCheck,
  RuntimeFailureFields,
  RuntimeInitMode,
} from '@/types/electron'
import type { MirrorConfig } from '@/types/mirror'
import type {
  FailureAction,
  FailureActionKind,
  FailureNoticeKind,
} from '@/utils/initializationDecision'
import type { InitializationStepKey, InitializationStepStatus } from './initializationPresentation'

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
    countdown: number
    failureActions: FailureAction[]
    failureNotice: FailureNoticeKind | null
    failureLogs: string
    failureLogPath: string
    doctorChecks: RuntimeDoctorCheck[] | null
    doctorRunning: boolean
  }

  interface ProgressPayload {
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
      countdown: 0,
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
  const runtimeMirrorKeys = ref<Record<string, string[]>>({})
  const runtimeFallbackLogPath = ref('')
  const elapsedSeconds = ref(0)
  const flowKind = ref<'first-run' | 'update' | 'startup'>('first-run')

  const isDev = import.meta.env.DEV
  const version = import.meta.env.VITE_APP_VERSION
  const targetBranch = ref(isDev ? 'dev' : `release/${version}`)

  const RUNTIME_TAKEOVER_STEPS = new Set<InitializationStepKey>(['pip', 'git'])
  const RETRY_ACTION_KINDS = new Set<FailureActionKind>([
    'retry',
    'retry-other-mirror',
    'rebuild-environment',
  ])

  let countdownTimer: ReturnType<typeof setInterval> | null = null
  let elapsedTimer: ReturnType<typeof setInterval> | null = null
  let initializationTimer: ReturnType<typeof setTimeout> | null = null

  const currentStep = computed(() => steps[currentStepIndex.value])
  const activeStageKey = computed(() => getInitializationStageKey(currentStep.value.key))
  const elapsedText = computed(() => formatElapsedSeconds(elapsedSeconds.value))

  const presentationStages = computed(() => {
    const statuses = Object.fromEntries(
      steps.map(step => [step.key, stepStates.value[step.key].status])
    ) as Record<InitializationStepKey, InitializationStepStatus>

    return initializationStages.map(stage => ({
      key: stage.key,
      status: getInitializationStageStatus(stage.key, statuses),
    }))
  })

  const pageTitle = computed(() => {
    if (activeStageKey.value === 'backend') return t('init.page.startingTitle')
    if (flowKind.value === 'update') return t('init.page.updatingTitle')
    return t('init.page.preparingTitle')
  })

  const currentStepProps = computed(() => {
    const step = currentStep.value
    const state = stepStates.value[step.key]

    return {
      title: t(`init.steps.${getInitializationStageKey(step.key)}`),
      status: state.status,
      message: state.message,
      progress: state.progress,
      progressIndeterminate: state.progressIndeterminate,
      elapsedText: elapsedText.value,
      showMirrorSelection: state.showMirrorSelection,
      showSkipButton: step.canSkip && state.status === 'failed',
      mirrors: filterRuntimeMirrors(
        state.mirrors,
        step.key,
        runtimeMode.value,
        runtimeMirrorKeys.value
      ),
      selectedMirror: state.selectedMirror,
      countdown: state.countdown,
      failureActions: state.failureActions,
      failureNotice: state.failureNotice,
      failureLogs: state.failureLogs,
      doctorChecks: state.doctorChecks,
      doctorRunning: state.doctorRunning,
    }
  })

  logger.info(`当前环境: ${isDev ? '开发环境' : '生产环境'}, 目标分支: ${targetBranch.value}`)

  function stageStatusKey(status: InitializationStepStatus): string {
    return `init.state.${status}`
  }

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
    }
  }

  function handleProgress(stepKey: InitializationStepKey, value: unknown) {
    const state = stepStates.value[stepKey]
    const progress = readProgressPayload(value)
    const previousStatus = state.status
    const previousMessage = state.message

    if (progress.status === 'completed' || (progress.progress ?? 0) >= 100) {
      state.status = 'success'
      state.message = progress.message || t('init.msg.stageDone')
      state.progress = 100
      state.progressIndeterminate = false
    } else if (progress.status === 'failed') {
      state.status = 'failed'
      state.message = progress.message || t('init.msg.execFailed')
      state.progressIndeterminate = false
    } else {
      state.status = 'processing'
      state.message = progress.message || t('init.msg.running')
      if (progress.progress !== undefined) {
        state.progress = Math.min(100, Math.max(0, Math.round(progress.progress)))
      }
      state.progressIndeterminate = progress.indeterminate ?? progress.progress === undefined
    }

    if (previousStatus !== state.status || previousMessage !== state.message) {
      logger.info(`[${stepKey}] ${state.message}`)
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
    state.message = t('init.runtime.takenOver')
    state.progress = 100
    state.progressIndeterminate = false
    state.showMirrorSelection = false
    state.countdown = 0
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

    const plan = applyFailure(state, stepKey, failure)
    const autoAction = plan.actions.find(action => RETRY_ACTION_KINDS.has(action.kind))
    if (autoAction) startCountdown(stepKey, autoAction.kind === 'rebuild-environment')
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
        state.message ||= t('init.msg.stageDone')
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
    state.message = t('init.msg.running')
    state.progress = 0
    state.progressIndeterminate = true
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
      state.message = t('init.msg.stageDone')
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
    stepStates.value[currentStep.value.key].selectedMirror = mirrorKey
  }

  function resetFailureState(state: StepState) {
    state.showMirrorSelection = false
    state.countdown = 0
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
    clearCountdown()

    state.status = 'success'
    state.message = t('init.msg.skipped')
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
    clearCountdown()
    resetFailureState(state)

    logger.info(`重试 ${step.key}${rebuild ? '（重建环境）' : ''}`)
    if (await executeStep(step.key)) await continueAfterCurrentStep()
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
    state.message = t('init.msg.backendStarted')
    clearElapsedClock()

    message.success(t('init.msg.initDone'))
    await window.electronAPI.setInitializedVersion?.(version)
    await getBackendVersion()
    await handleLocalEnterApp()
  }

  function handleBackendError(errorMessage: string) {
    const state = stepStates.value.backend
    state.status = 'failed'
    state.message = errorMessage
  }

  function clearCountdown() {
    if (!countdownTimer) return
    clearInterval(countdownTimer)
    countdownTimer = null
  }

  function startCountdown(stepKey: InitializationStepKey, rebuild = false) {
    clearCountdown()
    const state = stepStates.value[stepKey]
    state.countdown = 60

    countdownTimer = setInterval(() => {
      state.countdown -= 1
      if (state.countdown > 0) return
      clearCountdown()
      void handleRetry(rebuild)
    }, 1000)
  }

  async function handleFailureAction(kind: FailureActionKind) {
    const state = stepStates.value[currentStep.value.key]

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
      await window.electronAPI.openFile(target)
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

  function startElapsedClock() {
    const startedAt = Date.now()
    elapsedTimer = setInterval(() => {
      elapsedSeconds.value = Math.floor((Date.now() - startedAt) / 1000)
    }, 1000)
  }

  function clearElapsedClock() {
    if (!elapsedTimer) return
    clearInterval(elapsedTimer)
    elapsedTimer = null
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
    logger.info('新版初始化界面已加载')

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

    startElapsedClock()
    if (startIndex < steps.length - 1) {
      initializationTimer = setTimeout(() => {
        void startInitialization(startIndex)
      }, 400)
    }
  })

  onUnmounted(() => {
    clearCountdown()
    clearElapsedClock()
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
    activeStageKey,
    currentStep,
    currentStepProps,
    elapsedText,
    handleBackendComplete,
    handleBackendError,
    handleBackendStatusChange,
    handleFailureAction,
    handleMirrorSelect,
    handleSkip,
    pageTitle,
    presentationStages,
    stageStatusKey,
  }
}
