import type { MascotMenuDefinition } from './mascotPack'

export interface DesktopMascotData {
  imageUrl: string
  needsImageDecode?: boolean
  opacity: number
  state: 'idle' | 'working'
  animate: boolean
  motionOverride: boolean
  /** 为空时按动画包的待机、工作帧率播放。 */
  fps?: number | null
  width: number
  height: number
  offsetX: number
  offsetY: number
  noticeBelow: boolean
  noticeWidth: number
  noticeHeight: number
  revision: number
  dragging: boolean
  dragSession?: number
  colors: DesktopMascotColors
  notice?: string
  idleMessage?: DesktopMascotIdleMessage
  lookFrame?: number | null
  reaction?: 'success' | 'failure' | 'stopped'
  animation?: {
    imageUrl: string
    columns: number
    frameCount: number
    idleFps: number
    workingFps: number
    lookImageUrl?: string
    resultImageUrl?: string
    dragImageUrl?: string
  }
}

// 日常状态更新不携带图片，完整素材只在首次加载或更换皮肤时发送。
export type DesktopMascotUpdate = Partial<
  Omit<DesktopMascotData, 'imageUrl' | 'animation' | 'opacity'>
>

export interface DesktopMascotSelection {
  id: string | null
  enabled: boolean
}

export type DesktopMascotPointerAction = 'hover' | 'move' | 'end'

export interface DesktopMascotDragStart {
  x: number
  y: number
  session: number
  revision: number
}

export interface DesktopMascotColors {
  background: string
  text: string
  border: string
  radius: number
}

export interface DesktopMascotIdleMessage {
  text: string
  author: string
}

export interface DesktopMascotMenuLabels {
  pauseAnimation: string
  resumeAnimation: string
  pauseIdleMessage: string
  resumeIdleMessage: string
  refreshIdleMessage: string
  refreshUnavailable: string
  quickStart: string
  stopTask: string
  noTasks: string
  noRunningTasks: string
  tasksUnavailable: string
  loadingTasks: string
  capabilityUnavailable: string
}

export interface DesktopMascotTaskMenuItem {
  taskId: string
  label: string
  enabled: boolean
}

export interface DesktopMascotTaskMenu {
  enabled: boolean
  start: DesktopMascotTaskMenuItem[]
  stop: DesktopMascotTaskMenuItem[]
  startFailed: boolean
  startLoading: boolean
}

export interface DesktopMascotTaskAction {
  action: 'start' | 'stop'
  taskId: string
}

export interface DesktopMascotMenuResult {
  success: boolean
  message?: string
}

/** 渲染器只消费能力，不解释任务、配置或宿主模块。 */
export interface DesktopMascotMenuCapability {
  id: string
  label: string
  enabled: boolean
  disabledReason?: string
  loading?: boolean
  checked?: boolean
  options?: Array<{ value: string; label: string; enabled: boolean }>
  emptyLabel?: string
}

export interface DesktopMascotMenuData {
  protocolVersion: 1
  presentation: MascotMenuDefinition
  capabilities: DesktopMascotMenuCapability[]
  colors: DesktopMascotColors
  unavailableLabel: string
}

export interface DesktopMascotMenuAction {
  capability: string
  value?: string
}

export interface DesktopMascotMenuAPI {
  getData(): Promise<DesktopMascotMenuData | null>
  getViewport(): Promise<DesktopMascotMenuSize | null>
  resize(size: DesktopMascotMenuSize): void
  onChanged(callback: (data: DesktopMascotMenuData) => void): () => void
  execute(action: DesktopMascotMenuAction): Promise<DesktopMascotMenuResult>
  close(): void
}

export interface DesktopMascotMenuSize {
  width: number
  height: number
}

/** 应用适配器提供任务能力，桌宠不直接依赖调度 API 或运行状态实现。 */
export interface DesktopMascotTaskControl {
  list(): { result: Promise<DesktopMascotTaskMenuItem[]>; cancel(): void }
  running(): DesktopMascotTaskMenuItem[]
  start(taskId: string): Promise<{ taskId: string }>
  stop(taskId: string): Promise<void>
}

export interface DesktopMascotTaskSnapshot {
  taskId: string
  name: string | null
  working: boolean
}

export type DesktopMascotTaskEvent =
  | {
      type: 'snapshot'
      tasks: DesktopMascotTaskSnapshot[]
      activeTaskIds: ReadonlySet<string>
    }
  | { type: 'started'; task: DesktopMascotTaskSnapshot }
  | {
      type: 'completed'
      task: DesktopMascotTaskSnapshot
      result: 'success' | 'failure' | 'stopped' | 'partialFailure'
    }
  | { type: 'removed'; taskId: string }

export interface DesktopMascotTaskEvents {
  snapshot(): DesktopMascotTaskSnapshot[]
  subscribe(listener: (event: DesktopMascotTaskEvent) => void): () => void
}

/** 任务菜单由应用提供，桌宠只展示选项并回传用户选择。 */
export interface DesktopMascotTaskHostAPI {
  onDesktopMascotTaskMenuRequest(callback: (requestId: number) => void): () => void
  onDesktopMascotTaskMenuClosed(callback: (requestId: number) => void): () => void
  setDesktopMascotTaskMenu(requestId: number, menu: DesktopMascotTaskMenu): Promise<void>
  onDesktopMascotTaskAction(
    callback: (action: DesktopMascotTaskAction, requestId: number) => void
  ): () => void
  setDesktopMascotTaskActionResult(
    requestId: number,
    result: DesktopMascotMenuResult
  ): Promise<void>
}

/** 主界面向桌宠宿主同步状态的最小能力面。 */
export interface DesktopMascotHostAPI {
  setDesktopMascotReady(
    ready: boolean,
    labels?: DesktopMascotMenuLabels,
    colors?: DesktopMascotColors
  ): Promise<void>
  setDesktopMascotActivity(working: boolean, animate: boolean): Promise<void>
  setDesktopMascotIdleMessage(message: DesktopMascotIdleMessage): Promise<void>
  showDesktopMascotNotice(text: string, reaction?: 'success' | 'failure' | 'stopped'): Promise<void>
  onDesktopMascotError(callback: () => void): () => void
  onDesktopMascotRefreshIdleMessage(callback: () => void): () => void
}

export interface DesktopMascotAPI {
  getData(): Promise<DesktopMascotData | null>
  onChanged(callback: (data: DesktopMascotData) => void): () => void
  onUpdated(callback: (update: DesktopMascotUpdate) => void): () => void
  pointer(...args: ['hover'] | ['move' | 'end', number]): void
  startDrag(offset: DesktopMascotDragStart): Promise<boolean>
  imageDecoded(imageUrl: string, pngDataUrl: string): void
  onLookChanged(callback: (frame: number | null) => void): () => void
}

declare global {
  interface Window {
    desktopMascotAPI: DesktopMascotAPI
    desktopMascotMenuAPI: DesktopMascotMenuAPI
  }
}
