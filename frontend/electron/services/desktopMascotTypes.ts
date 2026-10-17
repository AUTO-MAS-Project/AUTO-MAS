import type { Point, Rectangle, WebContents } from 'electron'
import type {
  DesktopMascotColors,
  DesktopMascotData,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
} from '../../src/types/desktopMascot'
import type { MascotAssets } from '../../src/types/mascotPack'

export interface DesktopMascotPreferences {
  desktopMascotEnabled?: boolean
  /** 为空时使用动画包的帧率。 */
  desktopMascotFps?: number | null
  desktopMascotAnimationPaused?: boolean
  desktopMascotIdleMessagePaused?: boolean
  desktopMascotPosition?: Point
}

/** 主题选择和配置文件由宿主负责，运行服务只消费当前素材与播放偏好。 */
export interface DesktopMascotOptions {
  readPreferences(): DesktopMascotPreferences
  resolveAssets(): MascotAssets | null
  savePosition(position: Point): void
  saveAnimationPaused(paused: boolean): void
  saveIdleMessagePaused(paused: boolean): void
  getInitialBounds(): Rectangle | undefined
  onError(error: unknown): void
}

/** 宿主与 IPC 共用的运行契约，不依赖具体窗口服务类。 */
export interface DesktopMascotRuntime {
  setReady(ready: boolean, labels?: DesktopMascotMenuLabels, colors?: DesktopMascotColors): void
  getData(sender: WebContents): DesktopMascotData | null
  setIdleMessage(message: DesktopMascotIdleMessage): void
  setActivity(working: boolean, animate: boolean): void
  showNotice(text: string, reaction?: 'success' | 'failure' | 'stopped'): void
  handlePointer(sender: WebContents, action: unknown, session: unknown): void
  startDrag(sender: WebContents, offset: unknown): boolean
  setDecodedImage(sender: WebContents, imageUrl: string, pngDataUrl: string): void
  sync(): void
  syncPreferences(): void
  dispose(): void
}
