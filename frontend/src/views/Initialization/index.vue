<template>
  <div class="initialization-page">
    <div class="header">
      <a-typography-title :level="3">
        {{ t('init.page.subtitle') }}
      </a-typography-title>
    </div>

    <a-steps :current="currentStepIndex" :status="stepStatus" class="init-steps">
      <a-step v-for="step in steps" :key="step.key" :title="t(stepTitleKey(step.key))" />
    </a-steps>

    <div class="step-content">
      <!-- 当前步骤内容 -->
      <component
        :is="currentStepComponent"
        v-bind="currentStepProps"
        @update:selected-mirror="handleMirrorSelect"
        @action="handleFailureAction"
        @skip="handleSkip"
        @complete="handleBackendComplete"
        @error="handleBackendError"
      />
    </div>

    <!-- 步骤操作按钮区域 - 后端启动完成后会自动进入应用，不需要手动按钮 -->
    <div class="step-actions"></div>
  </div>

  <!-- 跳过初始化弹窗 -->
  <a-modal
    v-model:open="forceEnterVisible"
    :title="t('init.page.skipModalTitle')"
    :ok-text="t('init.page.skipModalOk')"
    :cancel-text="t('init.page.skipModalCancel')"
    @ok="handleForceEnterConfirm"
  >
    <a-alert
      :message="t('init.page.skipModalAlert')"
      :description="t('init.page.skipModalDesc')"
      type="warning"
      show-icon
    />
  </a-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { enterApp, forceEnterApp } from '@/utils/appEntry.ts'
import { getBackendVersion } from '@/composables/useVersionService'
import StepPanel from './components/StepPanel.vue'
import BackendStartStep from './components/BackendStartStep.vue'
import { decideFailureActions, filterRuntimeMirrors } from '@/utils/initializationDecision'
import type {
  FailureAction,
  FailureActionKind,
  FailureNoticeKind,
} from '@/utils/initializationDecision'
import type { MirrorConfig } from '@/types/mirror'
import type {
  InstallStageResult,
  RuntimeDoctorCheck,
  RuntimeFailureFields,
  RuntimeInitMode,
} from '@/types/electron'

defineOptions({ name: 'InitializationPage' })

const { t } = useI18n()

const logger = window.electronAPI.getLogger('初始化流程')

// ==================== 步骤定义 ====================
// title 仅用于日志标签；界面显示走 init.steps.<key> 词表
const steps = [
  { key: 'python', title: 'Python 安装', canSkip: false },
  { key: 'pip', title: 'Pip 安装', canSkip: false },
  { key: 'git', title: 'Git 安装', canSkip: false },
  { key: 'repository', title: '源码拉取', canSkip: true },
  { key: 'dependency', title: '依赖安装', canSkip: true },
  { key: 'backend', title: '后端启动', canSkip: true },
]

// ==================== 状态管理 ====================
const currentStepIndex = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const initCompleted = ref(false)
const forceEnterVisible = ref(false)
const isDev = import.meta.env.DEV
const version = import.meta.env.VITE_APP_VERSION
const targetBranch = ref(isDev ? 'dev' : `release/${version}`)

logger.info(`当前环境: ${isDev ? '开发环境' : '生产环境'}, 目标分支: ${targetBranch.value}`)

// 各步骤状态
interface StepState {
  status: 'waiting' | 'processing' | 'success' | 'failed'
  message: string
  progress: number
  showMirrorSelection: boolean
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
  checkInfo?: {
    exeExists?: boolean
    canRun?: boolean
    version?: string
    exists?: boolean
    isGitRepo?: boolean
    isHealthy?: boolean
    requirementsExists?: boolean
    needsInstall?: boolean
  }
  mirrorProgress?: {
    current: number
    total: number
  }
  /** 以下几项由失败结果里的机器字段算出，旧链路下退化成原来的「重试 + 镜像面板」。 */
  failureActions: FailureAction[]
  failureNotice: FailureNoticeKind | null
  failureLogs: string
  failureLogPath: string
  doctorChecks: RuntimeDoctorCheck[] | null
  doctorRunning: boolean
}

/** 六个步骤的初始状态一模一样，逐个抄一遍只会在加字段时漏掉其中一份。 */
function createStepState(): StepState {
  return {
    status: 'waiting',
    message: '',
    progress: 0,
    showMirrorSelection: false,
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
    failureActions: [],
    failureNotice: null,
    failureLogs: '',
    failureLogPath: '',
    doctorChecks: null,
    doctorRunning: false,
  }
}

const stepStates = ref<Record<string, StepState>>({
  python: createStepState(),
  pip: createStepState(),
  git: createStepState(),
  repository: createStepState(),
  dependency: createStepState(),
  backend: createStepState(),
})

// 倒计时定时器
let countdownTimer: ReturnType<typeof setInterval> | null = null

// ==================== Runtime 链路 ====================

const runtimeMode = ref<RuntimeInitMode>('off')
const runtimeMirrorKeys = ref<Record<string, string[]>>({})
const runtimeFallbackLogPath = ref('')

/**
 * Runtime 接管后不再执行的段。
 *
 * uv 与 Python 合并进 python 段，pip 由 uv 管、Git 由 Runtime 内置，都不再单独安装。
 * `mirror` 段不在界面的步骤条上，列在这里只是让判定覆盖主进程发得出的全部段名。
 */
const RUNTIME_TAKEOVER_STEPS = new Set(['mirror', 'pip', 'git'])

/** 会真的再跑一次安装的动作，自动重试只挑这几种。 */
const RETRY_ACTION_KINDS = new Set<FailureActionKind>([
  'retry',
  'retry-other-mirror',
  'rebuild-environment',
])

function isRuntimeTakenOver(stepKey: string): boolean {
  return runtimeMode.value !== 'off' && RUNTIME_TAKEOVER_STEPS.has(stepKey)
}

/** 步骤条上的标题：Runtime 接管后 uv 与 Python 合成一段，另外两段直接说明由谁负责。 */
function stepTitleKey(stepKey: string): string {
  if (runtimeMode.value === 'off') return `init.steps.${stepKey}`
  if (stepKey === 'python') return 'init.runtime.preparingEnv'
  if (RUNTIME_TAKEOVER_STEPS.has(stepKey)) return 'init.runtime.takenOver'
  return `init.steps.${stepKey}`
}

// ==================== 计算属性 ====================
const currentStep = computed(() => steps[currentStepIndex.value])

const currentStepComponent = computed(() => {
  // 后端启动步骤使用专门的组件
  if (currentStep.value.key === 'backend') {
    return BackendStartStep
  }
  return StepPanel
})

const currentStepProps = computed(() => {
  const state = stepStates.value[currentStep.value.key]
  const step = currentStep.value

  return {
    title: t(stepTitleKey(step.key)),
    status: state.status,
    message: state.message,
    progress: state.progress,
    showProgress: true,
    progressStatus: (state.status === 'failed' ? 'exception' : 'normal') as
      | 'normal'
      | 'exception'
      | 'success',
    successTitle: `${step.title}完成`,
    showMirrorSelection: state.showMirrorSelection, // 由 decideFailureActions 决定，旧链路下仍是失败即显示
    showSkipButton: step.canSkip && state.status === 'failed', // 只有可跳过的步骤且失败时才显示跳过按钮
    // Runtime 收不下的镜像源不摆出来：选了也只会被忽略，键名以主进程给的映射表为准
    mirrors: filterRuntimeMirrors(
      state.mirrors,
      step.key,
      runtimeMode.value,
      runtimeMirrorKeys.value
    ),
    selectedMirror: state.selectedMirror,
    countdown: state.countdown,
    currentMirror: state.currentMirror,
    downloadSpeed: state.downloadSpeed,
    downloadSize: state.downloadSize,
    installMessage: state.installMessage,
    installProgress: state.installProgress,
    deployMessage: state.deployMessage,
    deployProgress: state.deployProgress,
    operationDesc: state.operationDesc,
    checkInfo: state.checkInfo,
    mirrorProgress: state.mirrorProgress,
    failureActions: state.failureActions,
    failureNotice: state.failureNotice,
    failureLogs: state.failureLogs,
    doctorChecks: state.doctorChecks,
    doctorRunning: state.doctorRunning,
  }
})

// ==================== 方法 ====================

// 格式化速度
function formatSpeed(bytesPerSecond: number): string {
  if (bytesPerSecond < 1024) {
    return `${Math.round(bytesPerSecond)} B/s`
  } else if (bytesPerSecond < 1024 * 1024) {
    const kb = bytesPerSecond / 1024
    return `${kb < 10 ? kb.toFixed(2) : kb.toFixed(1)} KB/s`
  } else {
    const mb = bytesPerSecond / 1024 / 1024
    return `${mb < 10 ? mb.toFixed(2) : mb.toFixed(1)} MB/s`
  }
}

// 格式化大小
function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${Math.round(bytes)} B`
  } else if (bytes < 1024 * 1024) {
    const kb = bytes / 1024
    return `${kb < 10 ? kb.toFixed(2) : kb.toFixed(1)} KB`
  } else if (bytes < 1024 * 1024 * 1024) {
    const mb = bytes / 1024 / 1024
    return `${mb < 10 ? mb.toFixed(2) : mb.toFixed(1)} MB`
  } else {
    const gb = bytes / 1024 / 1024 / 1024
    return `${gb < 10 ? gb.toFixed(2) : gb.toFixed(1)} GB`
  }
}

// 处理进度更新
function handleProgress(stepKey: string, progressData: any) {
  const state = stepStates.value[stepKey]
  if (!state) return

  const { stage, progress, message: msg, details } = progressData

  // 更新状态
  if (progress >= 100) {
    // 进度达到 100%，标记为成功
    state.status = 'success'
    state.message = msg || t('init.msg.done')
    state.progress = 100
    state.currentMirror = ''
    state.downloadSpeed = ''
    state.downloadSize = ''
    state.installMessage = ''
    state.installProgress = 0
    state.deployMessage = ''
    state.deployProgress = 0
    state.operationDesc = ''
    logger.info(`[${stepKey}] 完成 - 100%`)
  } else if (progress > 0) {
    // 进度更新中
    state.status = 'processing'
    state.message = msg
    // 控制进度条显示为整数
    state.progress = Math.round(progress)

    // 处理详细信息
    if (details) {
      if (details.checkInfo) {
        state.checkInfo = details.checkInfo
      }
      if (details.currentMirror) {
        state.currentMirror = details.currentMirror
      }
      if (details.mirrorProgress) {
        state.mirrorProgress = details.mirrorProgress
      }
      if (details.downloadSpeed) {
        state.downloadSpeed = formatSpeed(details.downloadSpeed)
      }
      if (details.downloadSize) {
        state.downloadSize = formatSize(details.downloadSize)
      }
      if (details.operationDesc) {
        state.operationDesc = details.operationDesc
      }
    }

    // 根据阶段更新安装信息
    if (stage === 'install') {
      state.installMessage = msg
      state.installProgress = Math.round(progress)
      state.deployMessage = ''
      state.deployProgress = 0
    } else if (stage === 'deploy') {
      // 部署阶段
      state.deployMessage = msg
      state.deployProgress = Math.round(progress)
      state.installMessage = ''
      state.installProgress = 0
    } else {
      // 其他阶段清空安装和部署信息
      state.installMessage = ''
      state.installProgress = 0
      state.deployMessage = ''
      state.deployProgress = 0
    }

    logger.info(`[${stepKey}] ${msg} - ${Math.round(progress)}%`)
  } else if (progress === 0) {
    // 进度为 0，只在还没有进度时才重置
    // 避免在安装过程中因为某些中间步骤发送 progress: 0 导致进度条跳回0
    if (state.progress === 0 || state.status === 'waiting') {
      state.status = 'processing'
      state.message = msg || t('init.msg.preparing')
      state.progress = 0
      logger.info(`[${stepKey}] 开始 - ${msg}`)
    } else {
      // 如果已经有进度了，忽略 progress: 0 的更新，保持当前进度
      logger.debug(`[${stepKey}] 忽略 progress: 0 更新（当前进度: ${state.progress}%）`)
    }
  }
}

/** 把失败结果里的机器字段落进步骤状态，并算出该给哪些按钮。 */
function applyFailure(state: StepState, stepKey: string, failure: RuntimeFailureFields) {
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

/** Runtime 接管的段没有对应的安装动作，直接置完成，不必往主进程跑一趟。 */
function markStepTakenOver(state: StepState) {
  state.status = 'success'
  state.progress = 100
  state.message = t('init.runtime.takenOver')
  state.showMirrorSelection = false
  state.countdown = 0
  state.failureActions = []
  state.failureNotice = null
}

/** 完整 Runtime 初始化的进度按真实段落切换界面；没有独立页面的接管段保持已完成。 */
function handleRuntimeInitializationProgress(progressData: {
  stage: string
  progress: number
  message: string
}) {
  if (RUNTIME_TAKEOVER_STEPS.has(progressData.stage)) return

  const stepIndex = steps.findIndex(step => step.key === progressData.stage)
  if (stepIndex < 0 || progressData.stage === 'backend') return

  currentStepIndex.value = stepIndex
  handleProgress(progressData.stage, progressData)
}

function markStepFailed(stepKey: string, errorMsg: string, failure: RuntimeFailureFields) {
  const state = stepStates.value[stepKey]

  logger.error(`步骤 ${stepKey} 失败: ${errorMsg}`)
  state.status = 'failed'
  state.message = errorMsg

  const plan = applyFailure(state, stepKey, failure)

  // 只有真会重跑安装的动作才值得自动重试；不可重试的失败干等 60 秒没有意义
  const autoAction = plan.actions.find(action => RETRY_ACTION_KINDS.has(action.kind))
  if (autoAction) {
    startCountdown(stepKey, autoAction.kind === 'rebuild-environment')
  }
}

/** Runtime 的完整首次准备必须走 bootstrap；分步 IPC 继续承担更新与失败重试。 */
async function executeRuntimeInitialization(): Promise<boolean> {
  try {
    const result = await window.electronAPI.initialize(targetBranch.value, false)

    if (!result.success) {
      const failedStep = steps.find(
        step => step.key === result.failedStage && !RUNTIME_TAKEOVER_STEPS.has(step.key)
      )
      const failedStepKey = failedStep?.key ?? 'python'
      currentStepIndex.value = steps.findIndex(step => step.key === failedStepKey)
      markStepFailed(
        failedStepKey,
        result.error || t('init.msg.execFailed'),
        result
      )
      return false
    }

    // 进度事件是界面展示，最终结果才是准备完成的权威状态。
    for (const step of steps.slice(0, -1)) {
      const state = stepStates.value[step.key]
      state.status = 'success'
      state.progress = 100
      state.message ||= t('init.msg.stageDone')
    }

    currentStepIndex.value = steps.length - 1
    logger.info('Runtime bootstrap 完成，准备启动后端')
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    currentStepIndex.value = 0
    markStepFailed('python', errorMsg, {})
    return false
  }
}

// 执行单个步骤
async function executeStep(stepKey: string, rebuild: boolean = false): Promise<boolean> {
  const state = stepStates.value[stepKey]

  if (isRuntimeTakenOver(stepKey)) {
    logger.info(`步骤 ${stepKey} 由 Runtime 接管，直接置为完成`)
    markStepTakenOver(state)
    return true
  }

  state.status = 'processing'
  state.progress = 0
  state.message = t('init.msg.running')

  // 失败结果上的机器字段：抛异常前先接住，catch 里统一算按钮
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
        // 后端启动由BackendStartStep组件处理
        // 该组件会触发 complete 事件，由 handleBackendComplete 处理
        // 这里直接返回 true，让循环结束
        // 但不触发自动进入应用，由 handleBackendComplete 控制
        return true
      default:
        throw new Error(t('init.unknownStepP0', { p0: stepKey }))
    }

    if (result.success) {
      // 确保进度更新到 100%
      state.status = 'success'
      state.progress = 100
      state.message = t('init.msg.stageDone')
      state.currentMirror = ''
      state.downloadSpeed = ''
      state.downloadSize = ''
      state.installMessage = ''
      state.installProgress = 0
      state.operationDesc = ''

      logger.info(`步骤 ${stepKey} 完成`)

      // 显示成功状态，让用户看到阶段完成
      await new Promise(resolve => setTimeout(resolve, 300))

      return true
    } else {
      failure = result
      throw new Error(result.error || t('init.msg.execFailed'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    markStepFailed(stepKey, errorMsg, failure)
    return false
  }
}

// 开始初始化流程
async function startInitialization(startIndex: number = 0) {
  logger.info('开始初始化流程...')

  try {
    if (runtimeMode.value !== 'off' && startIndex === 0) {
      logger.info('Runtime 接管首次初始化，执行完整 bootstrap')
      const success = await executeRuntimeInitialization()
      if (!success) {
        stepStatus.value = 'error'
      }
      return
    }

    // 依次执行每个步骤
    for (let i = startIndex; i < steps.length; i++) {
      const step = steps[i]
      currentStepIndex.value = i

      logger.info(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)

      const success = await executeStep(step.key)

      if (!success) {
        // 步骤失败，等待用户重试
        stepStatus.value = 'error'
        logger.warn(`步骤 ${step.title} 失败，等待用户重试`)
        return
      }

      logger.info(`步骤 ${step.title} 完成`)
    }

    // 所有步骤完成
    // 注意：不在这里进入应用，由 handleBackendComplete 处理
    logger.info('初始化流程执行完成，等待后端启动完成...')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`初始化失败: ${errorMsg}`)
    stepStatus.value = 'error'
    message.error(t('init.msg.initFailed'))
  }
}

function handleMirrorSelect(mirrorKey: string) {
  const state = stepStates.value[currentStep.value.key]
  if (state) {
    state.selectedMirror = mirrorKey
  }
}

async function handleSkip() {
  const stepKey = currentStep.value.key
  const state = stepStates.value[stepKey]

  logger.info(`跳过步骤: ${stepKey}`)

  if (state) {
    // 清除倒计时
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }

    // 标记为已跳过
    state.status = 'success'
    state.progress = 100
    state.message = t('init.msg.skipped')
    state.showMirrorSelection = false
    state.countdown = 0
    state.failureActions = []
    state.failureNotice = null

    message.warning(t('init.msg.skippedStep', { step: t(`init.steps.${currentStep.value.key}`) }))

    // 等待一下让用户看到跳过状态
    await new Promise(resolve => setTimeout(resolve, 500))

    // 继续执行后续步骤
    for (let i = currentStepIndex.value + 1; i < steps.length; i++) {
      const step = steps[i]
      currentStepIndex.value = i

      logger.info(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)

      const stepSuccess = await executeStep(step.key)

      if (!stepSuccess) {
        stepStatus.value = 'error'
        return
      }
    }

    // 如果跳过的步骤是后端步骤，或者我们已经完成了所有步骤
    if (stepKey === 'backend' || currentStepIndex.value === steps.length - 1) {
      logger.info('后端步骤已跳过或所有步骤已完成，准备进入应用')
      handleLocalEnterApp()
    } else {
      // 所有步骤完成
      logger.info('初始化流程执行完成，等待后端启动完成...')
    }
  }
}

async function handleRetry(rebuild: boolean = false) {
  const stepKey = currentStep.value.key
  const state = stepStates.value[stepKey]

  if (state) {
    // 清除倒计时
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }

    // 重置状态
    state.showMirrorSelection = false
    state.countdown = 0
    state.failureActions = []
    state.failureNotice = null
    state.failureLogs = ''
    state.doctorChecks = null

    logger.info(
      `重试 ${stepKey}，使用镜像源: ${state.selectedMirror}${rebuild ? '（重建环境）' : ''}`
    )

    // 重新执行当前步骤
    const success = await executeStep(stepKey, rebuild)

    if (success) {
      // 继续执行后续步骤
      for (let i = currentStepIndex.value + 1; i < steps.length; i++) {
        const step = steps[i]
        currentStepIndex.value = i

        logger.info(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)

        const stepSuccess = await executeStep(step.key)

        if (!stepSuccess) {
          stepStatus.value = 'error'
          return
        }
      }

      // 所有步骤完成
      logger.info('初始化流程执行完成，等待后端启动完成...')
    }
  }
}

// 处理后端启动完成
async function handleBackendComplete() {
  logger.info('后端启动完成，准备进入应用')
  const state = stepStates.value.backend
  state.status = 'success'
  state.progress = 100
  state.message = t('init.msg.backendStarted')

  // 标记初始化完成
  initCompleted.value = true
  stepStatus.value = 'finish'
  message.success(t('init.msg.initDone'))

  // 保存初始化版本号，用于下次启动时比对
  const api = window.electronAPI
  await api.setInitializedVersion?.(version)
  logger.info(`初始化版本号已保存: ${version}`)

  // 初始化完成后刷新后端版本状态，消除标题栏更新提示
  await getBackendVersion()
  logger.info('后端版本状态已刷新')

  // 后端就绪、WebSocket 连接与版本检查任务均已在后端步骤内等待完成，直接进入应用
  logger.info('准备进入主应用界面')
  handleLocalEnterApp()
}

// 处理后端启动错误
function handleBackendError(error: string) {
  logger.error(`后端启动失败: ${error}`)
  const state = stepStates.value.backend
  state.status = 'failed'
  state.message = error
  stepStatus.value = 'error'
}

function startCountdown(stepKey: string, rebuild: boolean = false) {
  const state = stepStates.value[stepKey]
  if (!state) return

  state.countdown = 60

  countdownTimer = setInterval(() => {
    state.countdown--
    if (state.countdown <= 0) {
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      // 自动重试：用决策给出的第一个重试类动作，不硬当作普通重试
      handleRetry(rebuild)
    }
  }, 1000)
}

// ==================== 失败态动作 ====================

/**
 * 分发失败态按钮。
 *
 * 按钮是什么、有几个由 decideFailureActions 决定，这里只把 kind 接回对应的通道，
 * 不再按文案或中文 message 判断任何东西。
 */
async function handleFailureAction(kind: FailureActionKind) {
  const state = stepStates.value[currentStep.value.key]
  if (!state) return

  switch (kind) {
    case 'open-log':
      await openFailureLog(state)
      return
    case 'run-doctor':
      await runRuntimeDoctor(state)
      return
    // 三种重试共用一条通道，只有要不要重建环境这一个区别
    case 'retry':
    case 'retry-other-mirror':
      await handleRetry(false)
      return
    case 'rebuild-environment':
      await handleRetry(true)
      return
  }
}

/** 打开日志：优先 Runtime 本次操作的日志文件，没有就退回本程序自己的日志。 */
async function openFailureLog(state: StepState) {
  const target = state.failureLogPath || runtimeFallbackLogPath.value

  if (!target) {
    logger.error('没有可打开的日志文件路径')
    message.error(t('init.failure.openLogFailed', { error: t('init.msg.execFailed') }))
    return
  }

  try {
    logger.info(`打开日志文件: ${target}`)
    await window.electronAPI.openFile(target)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`打开日志失败: ${errorMsg}`)
    message.error(t('init.failure.openLogFailed', { error: errorMsg }))
  }
}

/** 运行诊断：check-critical-files 在 Runtime 链路下问的就是 Runtime doctor。 */
async function runRuntimeDoctor(state: StepState) {
  state.doctorRunning = true

  try {
    const result = await window.electronAPI.checkCriticalFiles()
    state.doctorChecks = result.runtimeChecks ?? []
    logger.info(`运行诊断完成，检查项: ${state.doctorChecks.length}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`运行诊断失败: ${errorMsg}`)
    message.error(t('init.failure.doctorFailed', { error: errorMsg }))
    state.doctorChecks = []
  } finally {
    state.doctorRunning = false
  }
}

async function handleForceEnterConfirm() {
  forceEnterVisible.value = false
  logger.info('用户确认跳过初始化')
  await forceEnterApp('初始化-强行进入确认')
}

async function handleLocalEnterApp() {
  try {
    // 尝试正常进入应用（会建立WebSocket连接，同时标记初始化完成）
    logger.info('准备正常进入应用...')
    const success = await enterApp('初始化完成后进入', true)

    if (!success) {
      logger.warn('正常进入失败，尝试强制进入')
      await forceEnterApp('初始化完成后强制进入')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`进入应用失败: ${errorMsg}`)
    // 发生异常时强制进入
    await forceEnterApp('初始化失败后强制进入')
  }
}

// ==================== 生命周期 ====================
// 从后端加载镜像源配置
async function loadMirrorConfigs() {
  const api = window.electronAPI

  try {
    logger.info('正在从后端加载镜像源配置...')

    // 先初始化镜像服务
    await api.initMirrors()

    // 并行获取所有镜像源配置
    const [pythonMirrors, getPipMirrors, gitMirrors, repoMirrors, pipMirrors] = await Promise.all([
      api.getMirrors('python'), // Python 安装包
      api.getMirrors('get_pip'), // get-pip.py 脚本
      api.getMirrors('git'), // Git 安装包
      api.getMirrors('repo'), // Git 仓库
      api.getMirrors('pip_mirror'), // PyPI 镜像源
    ])

    // 转换后端镜像源格式为前端格式
    const convertMirror = (mirror: any) => ({
      key: mirror.name,
      name: mirror.name,
      url: mirror.url,
      type: mirror.type,
      description: mirror.description,
      recommended: mirror.type === 'mirror',
    })

    // 设置各步骤的镜像源配置
    stepStates.value.python.mirrors = pythonMirrors.map(convertMirror)
    stepStates.value.pip.mirrors = getPipMirrors.map(convertMirror)
    stepStates.value.git.mirrors = gitMirrors.map(convertMirror)
    stepStates.value.repository.mirrors = repoMirrors.map(convertMirror)
    stepStates.value.dependency.mirrors = pipMirrors.map(convertMirror)

    logger.info('镜像源配置加载完成')
    logger.info(`Python 镜像源: ${stepStates.value.python.mirrors.map(m => m.name)}`)
    logger.info(`Pip 镜像源: ${stepStates.value.pip.mirrors.map(m => m.name)}`)
    logger.info(`Git 镜像源: ${stepStates.value.git.mirrors.map(m => m.name)}`)
    logger.info(`Repository 镜像源: ${stepStates.value.repository.mirrors.map(m => m.name)}`)
    logger.info(`Dependency 镜像源: ${stepStates.value.dependency.mirrors.map(m => m.name)}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载镜像源配置失败: ${errorMsg}`)
    // 镜像源配置由 Electron MirrorService 管理，如果失败则使用其默认配置
    logger.warn('镜像源配置加载失败，将使用 Electron MirrorService 的默认配置')
  }
}

onMounted(async () => {
  logger.info('初始化界面已加载')

  const api = window.electronAPI
  let startFromIndex = 0

  // 开发环境：完全跳过初始化流程
  if (isDev) {
    logger.info('开发环境，跳过初始化流程，直接进入应用')
    await handleLocalEnterApp()
    return
  }

  // Runtime 上下文决定步骤标签、哪些段不再执行、失败时日志开哪个文件、能换哪些镜像；
  // 拿不到就按旧链路走，界面与原来完全一致。
  try {
    const context = await api.getRuntimeInitContext?.()
    if (context) {
      runtimeMode.value = context.mode
      runtimeMirrorKeys.value = context.mirrorKeys ?? {}
      runtimeFallbackLogPath.value = context.fallbackLogPath ?? ''
      logger.info(`Runtime 初始化模式: ${context.mode}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取 Runtime 上下文失败，按旧链路处理: ${errorMsg}`)
  }

  // Runtime 接管的段没有对应的安装动作，进界面就置成完成，不让它们空转一遍
  if (runtimeMode.value !== 'off') {
    for (const step of steps) {
      if (RUNTIME_TAKEOVER_STEPS.has(step.key)) {
        markStepTakenOver(stepStates.value[step.key])
      }
    }
  }

  // 检查是否为强制后端更新模式（从标题栏触发）
  const forceBackendUpdate = sessionStorage.getItem('forceBackendUpdate') === 'true'
  if (forceBackendUpdate) {
    logger.info('检测到强制后端更新标志，将从第4步（源码拉取）开始执行')
    sessionStorage.removeItem('forceBackendUpdate')
  }

  // 检查自动更新开关（从 electron 配置中读取）
  let IfAutoUpdate = false
  try {
    const config = await api.loadConfig?.()
    if (config?.Update?.IfAutoUpdate !== undefined) {
      IfAutoUpdate = config.Update.IfAutoUpdate === true
      logger.info(`从配置读取到 IfAutoUpdate: ${IfAutoUpdate}`)
    } else {
      logger.warn('配置中未找到 IfAutoUpdate，默认为 false')
    }
  } catch {
    logger.warn('读取配置失败，默认执行完整初始化')
  }

  if (forceBackendUpdate) {
    // 强制后端更新模式：从第4步开始（repository, dependency, backend）
    logger.info('强制后端更新模式：跳过前3步，从源码拉取开始')
    startFromIndex = 3 // 从第4步（索引3）开始

    // 跳过前 3 步（python, pip, git），标记为成功
    for (let i = 0; i < 3; i++) {
      const stepKey = steps[i].key
      const state = stepStates.value[stepKey]
      state.status = 'success'
      state.progress = 100
      state.message = t('init.msg.skipped')
      state.showMirrorSelection = false
      state.countdown = 0
    }
  } else if (!IfAutoUpdate) {
    // 自动更新关闭：检查版本号
    const savedVersion = await api.getInitializedVersion?.()
    if (savedVersion === version) {
      // 版本号相同：跳过前5步，从后端步骤开始
      logger.info(`自动更新已关闭，初始化版本号一致（${version}），跳过安装步骤，启动后端`)
      startFromIndex = steps.length - 1

      // 跳过前 5 步（python, pip, git, repository, dependency），只启动后端
      for (let i = 0; i < steps.length - 1; i++) {
        const stepKey = steps[i].key
        const state = stepStates.value[stepKey]
        state.status = 'success'
        state.progress = 100
        state.message = t('init.msg.skipped')
        state.showMirrorSelection = false
        state.countdown = 0
      }
    } else {
      // 版本号不同或无记录：执行完整初始化流程
      logger.info(
        `自动更新已关闭，初始化版本号不一致（当前${version} vs 保存${savedVersion}），执行完整初始化流程`
      )
    }
  } else if (!forceBackendUpdate) {
    // 自动更新开启且非强制更新：无条件执行完整初始化流程
    logger.info('自动更新已开启，执行完整初始化流程')
  }

  // 加载镜像源配置
  await loadMirrorConfigs()

  // 监听各步骤进度
  api.onPythonProgress?.((progress: any) => handleProgress('python', progress))
  api.onPipProgress?.((progress: any) => handleProgress('pip', progress))
  api.onGitProgress?.((progress: any) => handleProgress('git', progress))
  api.onRepositoryProgress?.((progress: any) => handleProgress('repository', progress))
  api.onDependencyProgress?.((progress: any) => handleProgress('dependency', progress))
  api.onInitializationProgress?.(handleRuntimeInitializationProgress)

  api.onBackendStatus?.((status: any) => {
    logger.info(`后端状态更新: ${status.isRunning ? '运行中' : '已停止'}`)
    if (status.isRunning) {
      const state = stepStates.value.backend
      state.status = 'success'
      state.progress = 100
      state.message = t('init.msg.backendRunning', { pid: status.pid })
    }
  })

  // 延迟启动初始化
  setTimeout(() => {
    startInitialization(startFromIndex)
  }, 500)
})

onUnmounted(() => {
  logger.info('初始化界面卸载')

  // 清除倒计时
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }

  const api = window.electronAPI

  // 移除监听器
  api.removePythonProgressListener?.()
  api.removePipProgressListener?.()
  api.removeGitProgressListener?.()
  api.removeRepositoryProgressListener?.()
  api.removeDependencyProgressListener?.()
  api.removeInitializationProgressListener?.()
  api.removeBackendStatusListener?.()
})
</script>

<style scoped>
.initialization-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  width: 100%;
  height: 100%;
  padding: 20px;
  box-sizing: border-box;
  background-color: var(--ant-color-bg-layout);
  color: var(--ant-color-text);
}

.header {
  text-align: center;
  margin-bottom: 20px;
  width: 100%;
  max-width: 1000px;
}

.header h3 {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.init-steps {
  margin-bottom: 20px;
  width: 100%;
  max-width: 1000px;
}

.step-content {
  background-color: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 24px;
  /* min-height: 400px; Remove fixed min-height to allow shrinking on small screens */
  flex: 1;
  /* Take available vertical space */
  min-height: 0;
  /* Allow shrinking below content size */
  width: 100%;
  max-width: 1000px;
  box-sizing: border-box;
  display: flex;
  /* Enable flex for children (StepPanel) */
  flex-direction: column;
  overflow: auto;
  /* Allow scrolling when content overflows */
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
  width: 100%;
  max-width: 1000px;
}

/* 响应式优化 */
@media (max-width: 768px) {
  .initialization-page {
    gap: 15px;
    padding: 10px;
  }

  .header h3 {
    font-size: 20px;
  }

  .init-steps {
    :deep(.ant-steps-item-title) {
      white-space: normal;
    }
  }

  .step-content {
    padding: 16px;
    min-height: 300px;
  }
}

@media (max-width: 480px) {
  .step-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
