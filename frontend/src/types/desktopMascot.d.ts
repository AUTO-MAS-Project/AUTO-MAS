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
  Omit<DesktopMascotData, 'imageUrl' | 'animation' | 'width' | 'height' | 'opacity'>
>

export interface DesktopMascotSelection {
  id: string | null
  enabled: boolean
}

export type DesktopMascotPointerAction = 'hover' | 'start' | 'move' | 'end'

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
  pointer(action: DesktopMascotPointerAction): void
  imageDecoded(imageUrl: string, pngDataUrl: string): void
  onLookChanged(callback: (frame: number | null) => void): () => void
}

declare global {
  interface Window {
    desktopMascotAPI: DesktopMascotAPI
  }
}
