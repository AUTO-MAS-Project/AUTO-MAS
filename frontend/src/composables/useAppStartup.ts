import { computed, ref } from 'vue'
import type {
  AppStartupStage,
  AppStartupState,
  AppStartupStatus,
} from '@/components/app-shell/types.ts'

const DEFAULT_MESSAGES: Record<AppStartupStatus, string> = {
  initializing: '正在初始化应用...',
  'backend-starting': '正在启动后端服务...',
  connected: '连接成功',
  offline: '后端离线',
  reconnecting: '正在重新连接后端...',
  timeout: '启动超时',
  failed: '启动失败',
  closing: '正在关闭应用...',
}

const STATUS_CAPABILITIES: Record<
  AppStartupStatus,
  { canRetry: boolean; canCopyDiagnostics: boolean; canExit: boolean; canOpenLogs: boolean }
> = {
  initializing: { canRetry: false, canCopyDiagnostics: false, canExit: true, canOpenLogs: false },
  'backend-starting': {
    canRetry: false,
    canCopyDiagnostics: false,
    canExit: true,
    canOpenLogs: false,
  },
  connected: { canRetry: false, canCopyDiagnostics: false, canExit: false, canOpenLogs: false },
  offline: { canRetry: true, canCopyDiagnostics: true, canExit: true, canOpenLogs: true },
  reconnecting: { canRetry: false, canCopyDiagnostics: false, canExit: true, canOpenLogs: false },
  timeout: { canRetry: true, canCopyDiagnostics: true, canExit: true, canOpenLogs: true },
  failed: { canRetry: true, canCopyDiagnostics: true, canExit: true, canOpenLogs: true },
  closing: { canRetry: false, canCopyDiagnostics: false, canExit: false, canOpenLogs: false },
}

interface StartupStatusOptions {
  message?: string
  detail?: string
  stage?: AppStartupStage
}

interface StartupStateInternal extends AppStartupState {
  /** 代际计数，用于隔离旧 Promise/timer/回调 */
  generation: number
  /** 当前会话重试次数 */
  retryCount: number
}

const state = ref<StartupStateInternal>({
  status: 'initializing',
  stage: 'renderer',
  message: DEFAULT_MESSAGES.initializing,
  canRetry: false,
  canCopyDiagnostics: false,
  canExit: true,
  canOpenLogs: false,
  generation: 0,
  retryCount: 0,
})

function buildPublicState(internal: StartupStateInternal): AppStartupState {
  return {
    status: internal.status,
    stage: internal.stage,
    message: internal.message,
    detail: internal.detail,
    canRetry: internal.canRetry,
    canCopyDiagnostics: internal.canCopyDiagnostics,
    canExit: internal.canExit,
    canOpenLogs: internal.canOpenLogs,
  }
}

export function useAppStartup() {
  const publicState = computed(() => buildPublicState(state.value))

  const setStatus = (status: AppStartupStatus, options?: StartupStatusOptions) => {
    const caps = STATUS_CAPABILITIES[status]
    state.value = {
      ...state.value,
      status,
      stage: options?.stage ?? state.value.stage,
      message: options?.message ?? DEFAULT_MESSAGES[status],
      detail: options?.detail,
      canRetry: caps.canRetry,
      canCopyDiagnostics: caps.canCopyDiagnostics,
      canExit: caps.canExit,
      canOpenLogs: caps.canOpenLogs,
    }
  }

  const reset = () => {
    state.value = {
      status: 'initializing',
      stage: 'renderer',
      message: DEFAULT_MESSAGES.initializing,
      canRetry: false,
      canCopyDiagnostics: false,
      canExit: true,
      canOpenLogs: false,
      generation: state.value.generation + 1,
      retryCount: 0,
    }
  }

  /** 进入真实重试流程：递增 generation 与 retryCount，状态置为 reconnecting */
  const beginRetry = () => {
    state.value = {
      status: 'reconnecting',
      stage: 'connection',
      message: DEFAULT_MESSAGES.reconnecting,
      canRetry: false,
      canCopyDiagnostics: false,
      canExit: true,
      canOpenLogs: false,
      generation: state.value.generation + 1,
      retryCount: state.value.retryCount + 1,
    }
  }

  const isFailure = computed(
    () =>
      state.value.status === 'offline' ||
      state.value.status === 'timeout' ||
      state.value.status === 'failed'
  )

  const isRunning = computed(
    () =>
      state.value.status === 'initializing' ||
      state.value.status === 'backend-starting' ||
      state.value.status === 'reconnecting'
  )

  const currentGeneration = computed(() => state.value.generation)
  const retryCount = computed(() => state.value.retryCount)

  return {
    state: publicState,
    rawState: state,
    setStatus,
    reset,
    beginRetry,
    isFailure,
    isRunning,
    currentGeneration,
    retryCount,
  }
}
