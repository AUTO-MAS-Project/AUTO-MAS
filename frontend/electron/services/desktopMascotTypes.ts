import type { Point, Rectangle, WebContents } from 'electron'
import type {
  DesktopMascotColors,
  DesktopMascotData,
  DesktopMascotIdleMessage,
  DesktopMascotMenuAction,
  DesktopMascotMenuCapability,
  DesktopMascotMenuResult,
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
  getInitialBounds(): Rectangle | undefined
  onContextMenu(position: Point): void
  onClosed(): void
  onError(error: unknown): void
}

/** 宿主与 IPC 共用的运行契约，不依赖具体窗口服务类。 */
export interface DesktopMascotRuntime {
  setReady(ready: boolean, colors?: DesktopMascotColors): void
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

/** 应用适配器接入运行输入，运行宿主不解释业务标签和任务协议。 */
export type DesktopMascotHostInputs = Pick<
  DesktopMascotRuntime,
  | 'setReady'
  | 'getData'
  | 'setIdleMessage'
  | 'setActivity'
  | 'showNotice'
  | 'handlePointer'
  | 'startDrag'
  | 'setDecodedImage'
>

export interface DesktopMascotCapabilities {
  snapshot(): { capabilities: DesktopMascotMenuCapability[]; unavailableLabel: string } | null
  subscribe(listener: () => void): () => void
  open(): void
  close(): void
  reset(): void
  execute(action: DesktopMascotMenuAction): Promise<DesktopMascotMenuResult>
  dispose(): void
}
