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
  quickStart: string
  stopTask: string
  noTasks: string
  noRunningTasks: string
  tasksUnavailable: string
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
}

export interface DesktopMascotTaskAction {
  action: 'start' | 'stop'
  taskId: string
}

/** 任务菜单由应用提供，桌宠只展示选项并回传用户选择。 */
export interface DesktopMascotTaskHostAPI {
  onDesktopMascotTaskMenuRequest(callback: (requestId: number) => void): () => void
  setDesktopMascotTaskMenu(requestId: number, menu: DesktopMascotTaskMenu): Promise<void>
  onDesktopMascotTaskAction(callback: (action: DesktopMascotTaskAction) => void): () => void
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
}

export interface DesktopMascotAPI {
  getData(): Promise<DesktopMascotData | null>
  onChanged(callback: (data: DesktopMascotData) => void): () => void
  onUpdated(callback: (update: DesktopMascotUpdate) => void): () => void
  pointer(action: DesktopMascotPointerAction, session?: number): void
  startDrag(offset: DesktopMascotDragStart): Promise<boolean>
  imageDecoded(imageUrl: string, pngDataUrl: string): void
  onLookChanged(callback: (frame: number | null) => void): () => void
}

declare global {
  interface Window {
    desktopMascotAPI: DesktopMascotAPI
  }
}
