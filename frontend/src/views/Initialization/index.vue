<template>
  <div class="initialization-page">
    <MacPageHeader
      title="欢迎使用 AUTO-MAS"
      subtitle="自动化脚本管理平台，让游戏日常更轻松"
      transparent
      class="initialization-hero"
    >
      <template #title>
        <div class="initialization-brand">
          <div class="robot-mark" aria-hidden="true">
            <span class="robot-eye" />
            <span class="robot-eye" />
          </div>
          <h1>欢迎使用 AUTO-MAS</h1>
        </div>
      </template>
      <template #subtitle>
        <p class="initialization-subtitle">自动化脚本管理平台，让游戏日常更轻松</p>
      </template>
      <div class="hero-progress">
        <span class="hero-progress__label">{{ progressSummary }}</span>
        <a-progress
          :percent="overallProgress"
          :show-info="false"
          :status="stepStatus === 'error' ? 'exception' : 'normal'"
          size="small"
        />
      </div>
      <template #actions>
        <a-button
          v-if="isCurrentFailure"
          aria-label="跳过整个初始化流程"
          @click="forceEnterVisible = true"
        >
          跳过初始化
        </a-button>
      </template>
    </MacPageHeader>

    <main class="initialization-content" aria-label="初始化向导">
      <aside class="stage-rail" aria-label="初始化阶段">
        <div class="stage-rail__heading">
          <span>初始化进度</span>
          <strong>{{ completedStepCount }}/{{ steps.length }}</strong>
        </div>
        <ol class="stage-list">
          <li v-for="(step, index) in steps" :key="step.key">
            <button
              type="button"
              class="stage-nav-item"
              :class="[
                `stage-nav-item--${normalizedStepStatus(stepStates[step.key].status)}`,
                { 'stage-nav-item--active': viewedStepIndex === index },
              ]"
              :disabled="!canViewStep(index)"
              :aria-current="viewedStepIndex === index ? 'step' : undefined"
              @click="selectViewedStep(index)"
            >
              <span class="stage-nav-item__index">
                <span v-if="normalizedStepStatus(stepStates[step.key].status) === 'success'"
                  >✓</span
                >
                <span v-else-if="normalizedStepStatus(stepStates[step.key].status) === 'failure'"
                  >!</span
                >
                <span v-else>{{ index + 1 }}</span>
              </span>
              <span class="stage-nav-item__copy">
                <strong>{{ step.title }}</strong>
                <small>{{ stepStatusLabel(stepStates[step.key].status) }}</small>
              </span>
              <span
                v-if="index === currentStepIndex"
                class="stage-nav-item__current"
                aria-label="当前执行阶段"
              />
            </button>
          </li>
        </ol>
        <p class="stage-rail__hint">可回看已完成阶段；不会重复执行安装操作。</p>
      </aside>

      <MacSection :padding="false" class="init-stage-card">
        <template #header>
          <div class="stage-heading">
            <div>
              <span class="stage-kicker">
                步骤 {{ viewedStepIndex + 1 }}
                <template v-if="isViewingHistory"> · 历史记录</template>
              </span>
              <h2>{{ viewedStep.title }}</h2>
              <p>{{ viewedStepDescription }}</p>
            </div>
            <MacStatePanel
              :type="viewedPanelType"
              :title="viewedPanelTitle"
              compact
              class="current-state-panel"
            >
              <p class="current-state-message">{{ viewedPanelDescription }}</p>
              <p v-if="viewedStep.canSkip && !isViewingHistory" class="current-step-boundary">
                此步骤失败后可以跳过；基础运行环境与插件安装步骤不可跳过。
              </p>
            </MacStatePanel>
          </div>
        </template>

        <div v-if="isViewingHistory" class="step-history" aria-label="阶段执行记录">
          <div class="step-history__summary">
            <span
              class="step-history__badge"
              :class="`step-history__badge--${normalizedStepStatus(viewedStepState.status)}`"
            >
              {{ stepStatusLabel(viewedStepState.status) }}
            </span>
            <strong>{{ viewedStepState.message || `${viewedStep.title}暂无附加信息` }}</strong>
          </div>
          <a-progress
            v-if="viewedStepState.progress > 0"
            :percent="viewedStepState.progress"
            :status="
              normalizedStepStatus(viewedStepState.status) === 'failure' ? 'exception' : 'success'
            "
          />
          <dl class="step-history__facts">
            <div>
              <dt>阶段</dt>
              <dd>{{ viewedStep.title }}</dd>
            </div>
            <div>
              <dt>执行结果</dt>
              <dd>{{ stepStatusLabel(viewedStepState.status) }}</dd>
            </div>
            <div v-if="viewedStepState.checkInfo?.version">
              <dt>检测版本</dt>
              <dd>{{ viewedStepState.checkInfo.version }}</dd>
            </div>
            <div v-if="viewedStepState.currentMirror">
              <dt>使用镜像</dt>
              <dd>{{ viewedStepState.currentMirror }}</dd>
            </div>
          </dl>
          <a-alert
            v-if="viewedStepState.failureDetails"
            type="error"
            show-icon
            message="失败诊断"
            :description="viewedStepState.failureDetails.reason"
          />
          <a-button type="link" class="return-current-step" @click="followCurrentStep">
            返回当前阶段：{{ currentStep.title }}
          </a-button>
        </div>
        <div v-else class="step-content">
          <component
            :is="currentStepComponent"
            v-bind="currentStepProps"
            @update:selected-mirror="handleMirrorSelect"
            @retry="handleRetry"
            @skip="handleSkip"
            @complete="handleBackendComplete"
            @error="handleBackendError"
            @update:status="handleBackendStatus"
          />
        </div>
      </MacSection>
    </main>
  </div>

  <!-- 跳过初始化弹窗 -->
  <a-modal
    v-model:open="forceEnterVisible"
    title="跳过初始化并进入应用？"
    ok-text="我知道我在做什么"
    cancel-text="取消"
    @ok="handleForceEnterConfirm"
  >
    <a-alert
      message="仅在你已经手动完成环境配置时使用"
      description="你正在尝试跳过初始化流程，可能导致程序无法正常运行。请确保你已经手动完成了所有配置。"
      type="warning"
      show-icon
    />
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import MacPageHeader from '@/components/mac/PageHeader.vue'
import MacSection from '@/components/mac/Section.vue'
import MacStatePanel from '@/components/mac/StatePanel.vue'
import { enterApp, forceEnterApp } from '@/utils/appEntry.ts'
import { getBackendVersion } from '@/composables/useVersionService'
import StepPanel from './components/StepPanel.vue'
import BackendStartStep from './components/BackendStartStep.vue'
import type { MirrorConfig } from '@/types/mirror'
import {
  transitionToFailure as toFailure,
  transitionToSkipped as toSkipped,
  transitionToRetry as toRetry,
  parsePluginWarnings,
  type InitStepFailureDetails,
  type InitStepCheckInfo,
  type PluginBootstrapWarningLike,
  type PluginVersionConflict,
} from '@/composables/useInitializationStateMachine'

const logger = window.electronAPI.getLogger('初始化流程')

// ==================== 步骤定义 ====================
const steps = [
  { key: 'python', title: 'Python 安装', canSkip: false },
  { key: 'pip', title: 'Pip 安装', canSkip: false },
  { key: 'git', title: 'Git 安装', canSkip: false },
  { key: 'repository', title: '源码拉取', canSkip: true },
  { key: 'dependency', title: '依赖安装', canSkip: true },
  { key: 'plugin-bootstrap', title: '插件安装', canSkip: false },
  { key: 'backend', title: '后端启动', canSkip: true },
]

// ==================== 状态管理 ====================
const currentStepIndex = ref(0)
const viewedStepIndex = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const initCompleted = ref(false)
const forceEnterVisible = ref(false)
const isDev = import.meta.env.DEV
const version = import.meta.env.VITE_APP_VERSION
const targetBranch = ref(isDev ? 'dev' : 'dev_v2')

logger.info(`当前环境: ${isDev ? '开发环境' : '生产环境'}, 目标分支: ${targetBranch.value}`)

// 各步骤状态
// Lane 8：状态机包含 waiting/processing/running/success/failed/failure/skipped/retry
// 保留 'processing' 与 'failed' 用于兼容已有逻辑；新代码统一用 running/failure/skipped/retry
interface StepState {
  status:
    | 'waiting'
    | 'processing'
    | 'running'
    | 'success'
    | 'failed'
    | 'failure'
    | 'skipped'
    | 'retry'
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
  checkInfo?: InitStepCheckInfo
  mirrorProgress?: {
    current: number
    total: number
  }
  /** Lane 8：结构化失败诊断 */
  failureDetails?: InitStepFailureDetails
  /** Lane 8：插件安装步骤的原始 warnings（来自 installPluginBootstrap） */
  pluginWarnings?: PluginBootstrapWarningLike[]
  /** Lane 8：解析后的版本锁冲突结构化列表 */
  pluginVersionConflicts?: PluginVersionConflict[]
}

const createInitialStepState = (): StepState => ({
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
})

const stepStates = ref<Record<string, StepState>>(
  Object.fromEntries(steps.map(s => [s.key, createInitialStepState()]))
)

// 倒计时定时器
let countdownTimer: NodeJS.Timeout | null = null

// ==================== 计算属性 ====================
const currentStep = computed(() => steps[currentStepIndex.value])
const currentStepState = computed(() => stepStates.value[currentStep.value.key])
const viewedStep = computed(() => steps[viewedStepIndex.value])
const viewedStepState = computed(() => stepStates.value[viewedStep.value.key])
const isViewingHistory = computed(() => viewedStepIndex.value !== currentStepIndex.value)
const isCurrentFailure = computed(
  () => currentStepState.value.status === 'failed' || currentStepState.value.status === 'failure'
)

const progressSummary = computed(() => `第 ${currentStepIndex.value + 1} 步，共 ${steps.length} 步`)
const completedStepCount = computed(
  () =>
    Object.values(stepStates.value).filter(state => ['success', 'skipped'].includes(state.status))
      .length
)
const overallProgress = computed(() =>
  Math.round(
    ((completedStepCount.value + Math.min(1, Math.max(0, currentStepState.value.progress / 100))) /
      steps.length) *
      100
  )
)

const viewedPanelType = computed<'neutral' | 'info' | 'success' | 'warning' | 'error'>(() => {
  const status = viewedStepState.value.status
  if (status === 'success') return 'success'
  if (status === 'failed' || status === 'failure') return 'error'
  if (status === 'skipped') return 'warning'
  if (status === 'running' || status === 'processing' || status === 'retry') return 'info'
  return 'neutral'
})

const viewedPanelTitle = computed(() => {
  const status = viewedStepState.value.status
  if (status === 'success') return `${viewedStep.value.title}已完成`
  if (status === 'failed' || status === 'failure') return `${viewedStep.value.title}需要处理`
  if (status === 'skipped') return `${viewedStep.value.title}已跳过`
  if (status === 'retry') return `正在重试${viewedStep.value.title}`
  if (status === 'running' || status === 'processing') return `正在执行${viewedStep.value.title}`
  return `等待执行${viewedStep.value.title}`
})

const viewedPanelDescription = computed(
  () =>
    viewedStepState.value.failureDetails?.reason ||
    viewedStepState.value.message ||
    '正在准备此阶段所需的资源。'
)

const viewedStepDescription = computed(() => {
  if (viewedStep.value.key === 'backend') {
    return '启动后端、建立 WebSocket 连接并确认版本检查可用'
  }
  if (viewedStep.value.canSkip) {
    return '失败时可选择镜像重试，或在确认影响后跳过此步骤'
  }
  return '此步骤是运行所必需的；失败时请选择镜像源并重试'
})

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
  const isFailure = state.status === 'failed' || state.status === 'failure'

  return {
    title: step.title,
    status: state.status,
    message: state.message,
    progress: state.progress,
    showProgress: true,
    progressStatus: (isFailure ? 'exception' : 'normal') as 'normal' | 'exception' | 'success',
    successTitle: `${step.title}完成`,
    showMirrorSelection: state.showMirrorSelection, // 所有步骤失败时都显示镜像源选择
    showSkipButton: step.canSkip && isFailure, // 只有可跳过的步骤且失败时才显示跳过按钮
    mirrors: state.mirrors,
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
    failureDetails: state.failureDetails,
    // Lane 8：插件版本锁冲突展示
    pluginVersionConflicts: state.pluginVersionConflicts,
  }
})

// ==================== 方法 ====================

function normalizedStepStatus(status: StepState['status']) {
  if (status === 'success') return 'success'
  if (status === 'failed' || status === 'failure') return 'failure'
  if (status === 'skipped') return 'skipped'
  if (status === 'processing' || status === 'running' || status === 'retry') return 'running'
  return 'waiting'
}

function stepStatusLabel(status: StepState['status']) {
  const normalized = normalizedStepStatus(status)
  if (normalized === 'success') return '已完成'
  if (normalized === 'failure') return '需要处理'
  if (normalized === 'skipped') return '已跳过'
  if (normalized === 'running') return status === 'retry' ? '重试中' : '进行中'
  return '等待中'
}

function canViewStep(index: number) {
  if (index <= currentStepIndex.value) return true
  const status = normalizedStepStatus(stepStates.value[steps[index].key].status)
  return status !== 'waiting'
}

function selectViewedStep(index: number) {
  if (!canViewStep(index)) return
  viewedStepIndex.value = index
}

function followCurrentStep() {
  viewedStepIndex.value = currentStepIndex.value
}

function setCurrentStep(index: number) {
  const wasFollowingCurrent = viewedStepIndex.value === currentStepIndex.value
  currentStepIndex.value = index
  if (wasFollowingCurrent) {
    viewedStepIndex.value = index
  }
}

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
  // 防御 IPC 回调传入 null/undefined 或非对象导致解构抛错
  if (!progressData || typeof progressData !== 'object') return

  const { stage, progress, message: msg, details } = progressData

  // 更新状态
  if (progress >= 100) {
    // 进度达到 100%，标记为成功
    state.status = 'success'
    state.message = msg || '完成'
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
    state.status = 'running'
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
      state.status = 'running'
      state.message = msg || '准备中...'
      state.progress = 0
      logger.info(`[${stepKey}] 开始 - ${msg}`)
    } else {
      // 如果已经有进度了，忽略 progress: 0 的更新，保持当前进度
      logger.debug(`[${stepKey}] 忽略 progress: 0 更新（当前进度: ${state.progress}%）`)
    }
  }
}

// 执行单个步骤
async function executeStep(stepKey: string): Promise<boolean> {
  const state = stepStates.value[stepKey]
  state.status = 'running'
  state.progress = 0
  state.message = '正在执行...'
  state.showMirrorSelection = false
  state.countdown = 0

  try {
    let result: any

    switch (stepKey) {
      case 'python':
        result = await window.electronAPI.installPython(state.selectedMirror)
        break
      case 'pip':
        result = await window.electronAPI.installPip(state.selectedMirror)
        break
      case 'git':
        result = await window.electronAPI.installGit(state.selectedMirror)
        break
      case 'repository':
        result = await window.electronAPI.pullRepository(targetBranch.value, state.selectedMirror)
        break
      case 'dependency':
        result = await window.electronAPI.installDependencies(state.selectedMirror)
        break
      case 'plugin-bootstrap':
        result = await window.electronAPI.installPluginBootstrap(state.selectedMirror)
        break
      case 'backend':
        // 后端启动由BackendStartStep组件处理
        // 该组件会触发 complete 事件，由 handleBackendComplete 处理
        // 这里直接返回 true，让循环结束
        // 但不触发自动进入应用，由 handleBackendComplete 控制
        return true
      default:
        throw new Error(`未知步骤: ${stepKey}`)
    }

    if (result.success) {
      // 确保进度更新到 100%
      state.status = 'success'
      state.progress = 100
      state.message = '阶段完成'
      state.currentMirror = ''
      state.downloadSpeed = ''
      state.downloadSize = ''
      state.installMessage = ''
      state.installProgress = 0
      state.operationDesc = ''
      state.failureDetails = undefined

      // Lane 8：插件安装成功时仍保留 warnings（非致命警告，需向用户披露）
      if (
        stepKey === 'plugin-bootstrap' &&
        Array.isArray(result.warnings) &&
        result.warnings.length > 0
      ) {
        state.pluginWarnings = result.warnings
        state.pluginVersionConflicts = parsePluginWarnings(result.warnings)
        logger.warn(`[${stepKey}] 完成但携带 ${result.warnings.length} 条警告：`, result.warnings)
      } else {
        state.pluginWarnings = undefined
        state.pluginVersionConflicts = undefined
      }

      logger.info(`步骤 ${stepKey} 完成`)

      // 显示成功状态，让用户看到阶段完成
      await new Promise(resolve => setTimeout(resolve, 600))

      return true
    } else {
      // Lane 8：后端错误必须保留具体原因，不得只显示"执行失败"
      const backendError = result.error || result.message || ''
      // Lane 8：插件安装失败时，把 warnings 一并交给状态机解析为版本冲突
      const pluginWarnings =
        stepKey === 'plugin-bootstrap' && Array.isArray(result.warnings)
          ? result.warnings
          : undefined
      const err = new Error(backendError || '后端未返回具体错误，请查看应用日志')
      ;(err as any).pluginWarnings = pluginWarnings
      throw err
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`步骤 ${stepKey} 失败: ${errorMsg}`)

    // Lane 8：使用状态机生成结构化失败诊断
    const pluginWarnings = (error as any)?.pluginWarnings as
      | PluginBootstrapWarningLike[]
      | undefined
    const nextState = toFailure(state, errorMsg, {
      stepKey,
      mirrorTried: state.currentMirror || undefined,
      mirrorProgress: state.mirrorProgress,
      pluginWarnings,
    })
    Object.assign(state, nextState)
    state.status = 'failure'
    state.showMirrorSelection = true

    // 开始倒计时
    startCountdown(stepKey)

    return false
  }
}

// 开始初始化流程
async function startInitialization(startIndex: number = 0) {
  logger.info('开始初始化流程...')

  try {
    // 依次执行每个步骤
    for (let i = startIndex; i < steps.length; i++) {
      const step = steps[i]
      setCurrentStep(i)

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
    message.error('初始化失败')
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
    stepStatus.value = 'process'
    // 清除倒计时
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }

    // Lane 8：使用 skipped 状态而非 success+message
    const skippedState = toSkipped(state)
    Object.assign(state, skippedState)
    state.status = 'skipped'
    state.showMirrorSelection = false

    message.warning(`已跳过 ${currentStep.value.title}`)

    // 等待一下让用户看到跳过状态
    await new Promise(resolve => setTimeout(resolve, 500))

    // 继续执行后续步骤
    for (let i = currentStepIndex.value + 1; i < steps.length; i++) {
      const step = steps[i]
      setCurrentStep(i)

      logger.info(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)

      const stepSuccess = await executeStep(step.key)

      if (!stepSuccess) {
        stepStatus.value = 'error'
        return
      }
    }

    // 只有显式跳过 backend 步骤本身时才直接进入应用（用户选择离线）
    // 跳过非 backend 步骤时，循环结束后需等待 BackendStartStep 组件 emit complete
    if (stepKey === 'backend') {
      logger.info('后端步骤已跳过，准备进入应用')
      handleLocalEnterApp()
    } else {
      // 所有步骤完成，等待 BackendStartStep 启动后端并 emit complete
      logger.info('初始化流程执行完成，等待后端启动完成...')
    }
  }
}

async function handleRetry() {
  const stepKey = currentStep.value.key
  const state = stepStates.value[stepKey]

  if (state) {
    stepStatus.value = 'process'
    // 清除倒计时
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }

    // Lane 8：先进入 retry 状态，便于用户感知
    const retryState = toRetry(state)
    Object.assign(state, retryState)
    state.status = 'retry'
    state.showMirrorSelection = false
    state.countdown = 0

    logger.info(`重试 ${stepKey}，使用镜像源: ${state.selectedMirror}`)

    // 重新执行当前步骤
    const success = await executeStep(stepKey)

    if (success) {
      // 继续执行后续步骤
      for (let i = currentStepIndex.value + 1; i < steps.length; i++) {
        const step = steps[i]
        setCurrentStep(i)

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

function handleBackendStatus(status: 'waiting' | 'starting' | 'running' | 'success' | 'failed') {
  const state = stepStates.value.backend
  if (status === 'waiting') {
    state.status = 'waiting'
    return
  }
  if (status === 'starting' || status === 'running') {
    state.status = 'running'
    state.message = status === 'starting' ? '正在启动后端服务' : '后端已启动，正在完成连接检查'
    return
  }
  if (status === 'success') {
    state.status = 'success'
    state.progress = 100
    state.message = '后端服务启动成功'
    return
  }
  state.status = 'failure'
}

// 处理后端启动完成
async function handleBackendComplete() {
  logger.info('后端启动完成，准备进入应用')
  const state = stepStates.value.backend
  state.status = 'success'
  state.progress = 100
  state.message = '后端服务启动成功'

  // 标记初始化完成
  initCompleted.value = true
  stepStatus.value = 'finish'
  message.success('初始化完成')

  // 保存初始化版本号，用于下次启动时比对
  const api = window.electronAPI
  await api.setInitializedVersion?.(version)
  logger.info(`初始化版本号已保存: ${version}`)

  // 初始化完成后刷新后端版本状态，消除标题栏更新提示
  await getBackendVersion()
  logger.info('后端版本状态已刷新')

  logger.info('等待后端服务完全稳定...')

  // 延迟进入应用，确保：
  // 1. 后端服务完全启动
  // 2. WebSocket 连接已建立
  // 3. 版本检查任务已启动
  // 4. 所有初始化工作已完成
  await new Promise(resolve => setTimeout(resolve, 2000))

  logger.info('准备进入主应用界面')
  handleLocalEnterApp()
}

// 处理后端启动错误
function handleBackendError(error: string) {
  logger.error(`后端启动失败: ${error}`)
  const state = stepStates.value.backend
  // Lane 8：后端失败也使用状态机生成结构化诊断
  const nextState = toFailure(state, error, { stepKey: 'backend' })
  Object.assign(state, nextState)
  state.status = 'failure'
  state.showMirrorSelection = false
  stepStatus.value = 'error'
}

function startCountdown(stepKey: string) {
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
      // 自动重试
      handleRetry()
    }
  }, 1000)
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
    stepStates.value['plugin-bootstrap'].mirrors = pipMirrors.map(convertMirror)

    logger.info('镜像源配置加载完成')
    logger.info(`Python 镜像源: ${stepStates.value.python.mirrors.map(m => m.name)}`)
    logger.info(`Pip 镜像源: ${stepStates.value.pip.mirrors.map(m => m.name)}`)
    logger.info(`Git 镜像源: ${stepStates.value.git.mirrors.map(m => m.name)}`)
    logger.info(`Repository 镜像源: ${stepStates.value.repository.mirrors.map(m => m.name)}`)
    logger.info(`Dependency 镜像源: ${stepStates.value.dependency.mirrors.map(m => m.name)}`)
    logger.info(
      `Plugin bootstrap 镜像源: ${stepStates.value['plugin-bootstrap'].mirrors.map(m => m.name)}`
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载镜像源配置失败: ${errorMsg}`)
    // 镜像源配置由 Electron MirrorService 管理，如果失败则使用其默认配置
    logger.warn('镜像源配置加载失败，将使用 Electron MirrorService 的默认配置')
    message.warning('镜像源云端配置加载失败，已切换为本地默认配置')
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
      IfAutoUpdate = config.Update.IfAutoUpdate
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

    // 跳过前 3 步（python, pip, git）— Lane 8：使用 skipped 状态
    for (let i = 0; i < 3; i++) {
      const stepKey = steps[i].key
      const state = stepStates.value[stepKey]
      Object.assign(state, toSkipped(state))
      state.status = 'skipped'
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

      // 跳过前 5 步（python, pip, git, repository, dependency）— Lane 8：使用 skipped 状态
      for (let i = 0; i < steps.length - 1; i++) {
        const stepKey = steps[i].key
        const state = stepStates.value[stepKey]
        Object.assign(state, toSkipped(state))
        state.status = 'skipped'
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
  api.onPluginBootstrapProgress?.((progress: any) => handleProgress('plugin-bootstrap', progress))

  api.onBackendStatus?.((status: any) => {
    // 防御 IPC 回调传入 null/undefined 导致 status.isRunning 抛错
    if (!status || typeof status !== 'object') return
    logger.info(`后端状态更新: ${status.isRunning ? '运行中' : '已停止'}`)
    if (status.isRunning) {
      const state = stepStates.value.backend
      state.status = 'success'
      state.progress = 100
      state.message = `后端服务已启动，PID: ${status.pid}`
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
  api.removePluginBootstrapProgressListener?.()
  api.removeBackendStatusListener?.()
})
</script>

<style scoped>
.initialization-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  /* macOS 风格中性背景：窗口灰 + 极轻的顶部到底部明度渐变（两种主题均由 token 驱动） */
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--v6-color-surface) 45%, var(--v6-color-window)) 0%,
    var(--v6-color-window) 36%
  );
  background-color: var(--v6-color-window);
  color: var(--v6-color-text);
  overflow: auto;
}

.initialization-hero {
  display: flex;
  flex: 0 0 auto;
  width: min(930px, calc(100% - 48px));
  margin: 0 auto;
  padding: 24px 0 14px;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.initialization-hero :deep(.mac-page-header__content) {
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.initialization-hero :deep(.mac-page-header__title-group) {
  align-items: center;
}

.initialization-hero :deep(.mac-page-header__aside) {
  width: 100%;
  margin-left: 0;
}

.initialization-hero :deep(.mac-page-header__actions) {
  position: absolute;
  top: var(--v6-space-3);
  right: var(--v6-content-padding-inline);
}

.initialization-brand {
  text-align: center;
}

.initialization-brand h1 {
  margin: 14px 0 4px;
  color: var(--v6-color-text);
  font-size: 30px;
  font-weight: 720;
  letter-spacing: -0.035em;
}

.initialization-brand p {
  margin: 0;
  color: var(--v6-color-text-secondary);
}

.initialization-subtitle {
  margin: 0;
  color: var(--v6-color-text-secondary);
}

.robot-mark {
  position: relative;
  display: flex;
  width: 88px;
  height: 88px;
  margin: 0 auto;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border: 1px solid var(--v6-color-border);
  border-radius: 24px;
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--v6-color-info) 58%, white),
    var(--v6-color-info)
  );
  box-shadow:
    var(--v6-shadow-lg),
    inset 0 1px 0 rgb(255 255 255 / 42%);
}

.robot-mark::before {
  position: absolute;
  width: 52px;
  height: 34px;
  border: 4px solid rgb(255 255 255 / 96%);
  border-radius: 11px;
  content: '';
}

.robot-mark::after {
  position: absolute;
  top: 19px;
  width: 4px;
  height: 11px;
  border-radius: 4px;
  background: rgb(255 255 255 / 96%);
  box-shadow: 0 -3px 0 2px rgb(255 255 255 / 95%);
  content: '';
}

.robot-eye {
  z-index: 1;
  width: 5px;
  height: 7px;
  border-radius: 4px;
  background: rgb(255 255 255 / 96%);
}

.hero-progress {
  display: flex;
  width: min(620px, 100%);
  align-items: center;
  gap: var(--v6-space-3);
  color: var(--v6-color-text-secondary);
  font-size: 12px;
}

.hero-progress :deep(.ant-progress) {
  flex: 1;
  margin: 0;
}

.hero-progress__label {
  flex: 0 0 auto;
}

.initialization-content {
  display: flex;
  flex: 1;
  min-height: 0;
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: 0 24px 28px;
  padding-inline: var(--v6-content-padding-inline);
  box-sizing: border-box;
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
}

/* 顶部横向 stepper：七个阶段横排在标题区下方、内容卡上方 */
.stage-rail {
  flex: 0 0 auto;
  min-width: 0;
  padding: var(--v6-space-3) var(--v6-space-4);
  border: 1px solid var(--v6-color-border);
  border-radius: 18px;
  background: var(--v6-color-surface);
  box-shadow: var(--v6-shadow-card);
  color: var(--v6-color-text);
}

.stage-rail__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--v6-space-2);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

.stage-rail__heading strong {
  color: var(--v6-color-text);
}

.stage-list {
  display: flex;
  margin: 0;
  padding: 0 0 var(--v6-space-1);
  flex-direction: row;
  gap: var(--v6-space-1);
  list-style: none;
  overflow-x: auto;
  scroll-snap-type: x proximity;
}

.stage-list li {
  min-width: 140px;
  flex: 1 1 140px;
  scroll-snap-align: start;
}

.stage-nav-item {
  position: relative;
  display: flex;
  width: 100%;
  min-height: 54px;
  padding: var(--v6-space-2) var(--v6-space-3);
  border: 0;
  border-radius: 12px;
  align-items: center;
  gap: var(--v6-space-3);
  background: transparent;
  color: var(--v6-color-text);
  text-align: left;
  cursor: pointer;
  transition:
    background-color 160ms ease,
    transform 160ms ease;
}

.stage-nav-item:not(:disabled):hover {
  background: color-mix(in srgb, var(--v6-color-info) 10%, transparent);
  transform: translateY(-1px);
}

.stage-nav-item:disabled {
  color: var(--v6-color-text-tertiary);
  cursor: default;
}

.stage-nav-item--active {
  background: color-mix(in srgb, var(--v6-color-info) 16%, transparent);
}

.stage-nav-item__index {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border: 1px solid color-mix(in srgb, var(--v6-color-text-tertiary) 42%, transparent);
  border-radius: 50%;
  place-items: center;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  font-weight: 700;
}

.stage-nav-item--success .stage-nav-item__index {
  border-color: color-mix(in srgb, var(--v6-color-success) 46%, transparent);
  background: color-mix(in srgb, var(--v6-color-success) 14%, transparent);
  color: var(--v6-color-success);
}

.stage-nav-item--failure .stage-nav-item__index {
  border-color: color-mix(in srgb, var(--v6-color-error) 48%, transparent);
  background: color-mix(in srgb, var(--v6-color-error) 12%, transparent);
  color: var(--v6-color-error);
}

.stage-nav-item--running .stage-nav-item__index,
.stage-nav-item--active .stage-nav-item__index {
  border-color: var(--v6-color-info);
  background: var(--v6-color-info);
  color: var(--v6-color-surface);
}

.stage-nav-item__copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.stage-nav-item__copy strong,
.stage-nav-item__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-nav-item__copy strong {
  font-size: var(--v6-font-size-sm);
}

.stage-nav-item__copy small {
  color: var(--v6-color-text-tertiary);
  font-size: 11px;
}

.stage-nav-item__current {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: var(--v6-color-info);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--v6-color-info) 13%, transparent);
}

.stage-rail__hint {
  margin: var(--v6-space-2) var(--v6-space-1) 0;
  color: var(--v6-color-text-tertiary);
  font-size: 11px;
  line-height: 1.55;
}

.current-state-panel {
  width: min(360px, 46%);
  flex-shrink: 0;
}

.current-state-message,
.current-step-boundary {
  margin: 0;
}

.current-step-boundary {
  margin-top: var(--v6-space-1);
  color: var(--v6-color-text-tertiary);
}

.init-stage-card {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--v6-color-border);
  border-radius: 18px;
  background: var(--v6-color-surface);
  box-shadow: var(--v6-shadow-md);
  color: var(--v6-color-text);
  flex-direction: column;
}

.stage-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px 18px;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.stage-heading h2 {
  margin: 3px 0 5px;
  color: var(--v6-color-text);
  font-size: 20px;
}

.stage-heading p {
  max-width: 520px;
  margin: 0;
  color: var(--v6-color-text-secondary);
  font-size: 13px;
}

.stage-kicker {
  color: var(--v6-color-info);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.step-content {
  display: flex;
  min-height: 330px;
  height: 100%;
  padding: 18px 22px 22px;
  flex-direction: column;
  overflow: auto;
}

.step-history {
  display: flex;
  min-height: 330px;
  padding: var(--v6-space-6);
  flex-direction: column;
  gap: var(--v6-space-5);
  overflow: auto;
}

.step-history__summary {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
}

.step-history__badge {
  flex: 0 0 auto;
  padding: 5px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--v6-color-text-tertiary) 12%, transparent);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

.step-history__badge--success {
  background: color-mix(in srgb, var(--v6-color-success) 14%, transparent);
  color: var(--v6-color-success);
}

.step-history__badge--failure {
  background: color-mix(in srgb, var(--v6-color-error) 13%, transparent);
  color: var(--v6-color-error);
}

.step-history__badge--skipped {
  background: color-mix(in srgb, var(--v6-color-warning) 14%, transparent);
  color: var(--v6-color-warning);
}

.step-history__facts {
  display: grid;
  margin: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v6-space-3);
}

.step-history__facts > div {
  padding: var(--v6-space-3);
  border-radius: 12px;
  background: color-mix(in srgb, var(--v6-color-fill-tertiary) 62%, transparent);
}

.step-history__facts dt {
  color: var(--v6-color-text-tertiary);
  font-size: 11px;
}

.step-history__facts dd {
  margin: 4px 0 0;
  color: var(--v6-color-text);
  overflow-wrap: anywhere;
}

.return-current-step {
  align-self: flex-start;
  padding-inline: 0;
}

@media (max-width: 900px) {
  .initialization-content {
    padding: var(--v6-space-3);
    gap: var(--v6-space-3);
  }

  .initialization-hero {
    width: calc(100% - 24px);
  }

  .stage-rail {
    padding: var(--v6-space-2) var(--v6-space-3);
  }

  .stage-rail__heading,
  .stage-rail__hint {
    display: none;
  }

  .stage-nav-item {
    min-height: 50px;
  }

  .stage-nav-item:not(:disabled):hover {
    transform: none;
  }

  .stage-heading {
    flex-direction: column;
  }

  .current-state-panel {
    width: 100%;
  }

  .step-content {
    min-height: 300px;
  }

  .step-history__facts {
    grid-template-columns: minmax(0, 1fr);
  }
}

:root[data-perf-mode='low'] .initialization-page {
  scroll-behavior: auto;
}

@media (prefers-reduced-motion: reduce) {
  .initialization-page {
    scroll-behavior: auto;
  }
}
</style>
