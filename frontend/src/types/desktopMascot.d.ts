export interface DesktopMascotData {
  imageUrl: string
  needsImageDecode?: boolean
  opacity: number
  state: 'idle' | 'working'
  animate: boolean
  motionOverride: boolean
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
  }
}
