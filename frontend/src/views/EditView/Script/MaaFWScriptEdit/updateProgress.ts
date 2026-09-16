/**
 * MFW 脚本编辑页「更新过程」面板的纯逻辑：把后端推来的进度事件折叠成一份面板状态，
 * 并把字节 / 速度 / 文件数格式化成可读文本。
 *
 * 不碰 Vue、不碰 i18n：阶段只归成有限几个 phase，文案由组件按 phase 取词表。
 * 独立成文件是为了能在 vitest（无 DOM）里直接测。
 */
import type { WSMaaFWProjectUpdateProgressData } from '@/services/websocket/types'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'

export type MaaFWUpdateProgressPhase =
  | 'idle'
  | 'checking'
  | 'downloading'
  | 'preparing'
  | 'applying'
  | 'validating'
  | 'completed'
  | 'rolled_back'
  | 'failed'

export type MaaFWUpdatePackageKind = 'full' | 'incremental'

export interface MaaFWUpdateProgressState {
  phase: MaaFWUpdateProgressPhase
  /** 后端原始阶段名，调试与日志用；面板文案看 phase。 */
  stage: string
  message: string
  percent: number | null
  downloadedBytes: number | null
  totalBytes: number | null
  speedBytesPerSec: number | null
  packageKind: MaaFWUpdatePackageKind | null
  appliedFiles: number | null
  totalFiles: number | null
  logs: string[]
}

/** 日志框最多留这么多行；更新日志一般几十行，留有余量即可。 */
export const MAX_UPDATE_LOG_LINES = 300

const TERMINAL_PHASES: ReadonlySet<MaaFWUpdateProgressPhase> = new Set([
  'completed',
  'rolled_back',
  'failed',
])

const STAGE_PHASES: Record<string, MaaFWUpdateProgressPhase> = {
  checking: 'checking',
  downloading: 'downloading',
  downloaded: 'downloading',
  plan_validated: 'preparing',
  staged: 'preparing',
  applying: 'applying',
  post_validating: 'validating',
  committed: 'validating',
  rolled_back: 'rolled_back',
  completed: 'completed',
  failed: 'failed',
}

export function createUpdateProgressState(
  phase: MaaFWUpdateProgressPhase = 'idle'
): MaaFWUpdateProgressState {
  return {
    phase,
    stage: '',
    message: '',
    percent: null,
    downloadedBytes: null,
    totalBytes: null,
    speedBytesPerSec: null,
    packageKind: null,
    appliedFiles: null,
    totalFiles: null,
    logs: [],
  }
}

export function isTerminalPhase(phase: MaaFWUpdateProgressPhase): boolean {
  return TERMINAL_PHASES.has(phase)
}

function toNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function normalizePackageKind(value: unknown): MaaFWUpdatePackageKind | null {
  if (value === 'full' || value === 'incremental') return value
  return null
}

/**
 * 折叠一条 WS 事件。返回新对象而不是原地改，方便直接赋给 ref。
 *
 * - `stage: log` 只追加日志行，不改阶段。
 * - 已到终态（完成 / 回滚 / 失败）后再来的 running 事件一律忽略：WS 与 HTTP
 *   响应到达顺序没有保证，别让迟到的「下载中」把「已完成」又翻回去。
 */
export function reduceUpdateProgress(
  state: MaaFWUpdateProgressState,
  data: WSMaaFWProjectUpdateProgressData
): MaaFWUpdateProgressState {
  const logs = data.log ? [...state.logs.slice(-(MAX_UPDATE_LOG_LINES - 1)), data.log] : state.logs
  if (data.stage === 'log') {
    return logs === state.logs ? state : { ...state, logs }
  }

  const packageKind = normalizePackageKind(data.packageKind) ?? state.packageKind
  const failed = data.status === 'failed'
  const phase: MaaFWUpdateProgressPhase = failed
    ? 'failed'
    : (STAGE_PHASES[data.stage] ?? state.phase)

  if (isTerminalPhase(state.phase) && !isTerminalPhase(phase)) {
    return { ...state, logs, packageKind }
  }

  const next: MaaFWUpdateProgressState = {
    ...state,
    phase,
    stage: data.stage,
    message: data.message || state.message,
    packageKind,
    logs,
  }
  if (phase === 'downloading') {
    next.percent = toNumber(data.percent)
    next.downloadedBytes = toNumber(data.downloadedBytes)
    next.totalBytes = toNumber(data.totalBytes)
    next.speedBytesPerSec = toNumber(data.speedBytesPerSec)
  } else if (phase === 'applying') {
    next.percent = toNumber(data.percent)
    next.appliedFiles = toNumber(data.appliedFiles)
    next.totalFiles = toNumber(data.totalFiles)
  } else if (phase === 'completed') {
    next.percent = 100
  }
  return next
}

/**
 * HTTP 响应回来时的兜底收尾：WS 断连或迟到时也要能落到终态。
 * 已经由 WS 收尾的不再改写（后端那句更具体）。
 */
export function finishUpdateProgress(
  state: MaaFWUpdateProgressState,
  result: { success: boolean; message: string }
): MaaFWUpdateProgressState {
  if (isTerminalPhase(state.phase)) return state
  return {
    ...state,
    phase: result.success ? 'completed' : 'failed',
    stage: result.success ? 'completed' : 'failed',
    message: result.message || state.message,
    percent: result.success ? 100 : state.percent,
  }
}

/** `12.3 MB / 50 MB`；总量未知时只给已下载量。 */
export function formatDownloadSize(state: MaaFWUpdateProgressState): string {
  if (state.downloadedBytes === null) return ''
  const done = formatBytes(state.downloadedBytes)
  return state.totalBytes ? `${done} / ${formatBytes(state.totalBytes)}` : done
}

/** `3.2 MB/s`；没有采样点时为空串。 */
export function formatDownloadSpeed(state: MaaFWUpdateProgressState): string {
  if (state.speedBytesPerSec === null || state.speedBytesPerSec <= 0) return ''
  return formatSpeed(state.speedBytesPerSec)
}

/** `120/450`；后端还没给文件数时为空串。 */
export function formatAppliedFiles(state: MaaFWUpdateProgressState): string {
  if (state.appliedFiles === null || state.totalFiles === null) return ''
  return `${state.appliedFiles}/${state.totalFiles}`
}

/** 进度条要显示的整数百分比；没有可量化进度的阶段返回 null。 */
export function progressBarPercent(state: MaaFWUpdateProgressState): number | null {
  if (state.phase !== 'downloading' && state.phase !== 'applying') return null
  if (state.percent === null) return null
  return Math.max(0, Math.min(100, Math.round(state.percent)))
}
