import type { MirrorConfig } from '@/types/mirror'

export type InitializationStepKey =
  | 'python'
  | 'pip'
  | 'git'
  | 'repository'
  | 'dependency'
  | 'backend'

export interface InitializationStep {
  key: InitializationStepKey
  title: string
  canSkip: boolean
}

export interface StepState {
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
}

export type StepStateMap = Record<InitializationStepKey, StepState>

export const initializationSteps: InitializationStep[] = [
  { key: 'python', title: 'Python 安装', canSkip: false },
  { key: 'pip', title: 'Pip 安装', canSkip: false },
  { key: 'git', title: 'Git 安装', canSkip: false },
  { key: 'repository', title: '源码拉取', canSkip: true },
  { key: 'dependency', title: '依赖安装', canSkip: true },
  { key: 'backend', title: '后端启动', canSkip: true },
]

export const BACKEND_UPDATE_START_INDEX = initializationSteps.findIndex(
  step => step.key === 'repository'
)
export const BACKEND_STABILIZATION_DELAY_MS = 2000
export const INITIALIZATION_START_DELAY_MS = 500
export const RETRY_COUNTDOWN_SECONDS = 60

export function createDefaultStepState(): StepState {
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
  }
}

export function createInitialStepStates(): StepStateMap {
  return {
    python: createDefaultStepState(),
    pip: createDefaultStepState(),
    git: createDefaultStepState(),
    repository: createDefaultStepState(),
    dependency: createDefaultStepState(),
    backend: createDefaultStepState(),
  }
}
