import { app, BrowserWindow, Menu, nativeImage, screen, systemPreferences } from 'electron'
import type { MenuItemConstructorOptions, NativeImage, Point, WebContents } from 'electron'
import * as path from 'path'
import type {
  DesktopMascotColors,
  DesktopMascotData,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
  DesktopMascotUpdate,
  DesktopMascotDragStart,
} from '../../src/types/desktopMascot'
import { getMascotLayout, getMascotSize } from './desktopMascotGeometry'
import type { DesktopMascotOptions, DesktopMascotRuntime } from './desktopMascotTypes'

const MASCOT_MARGIN = 16

// 只做鼠标命中判断，不裁剪原生透明窗口；动画取所有帧的并集，避免边缘随播放闪动。
export function createMascotHitMask(images: NativeImage[]): Uint8Array {
  const { width, height } = images[0].getSize()
  const mask = new Uint8Array(width * height)
  for (const image of images) {
    const bitmap = image.toBitmap({ scaleFactor: 1 })
    for (let pixel = 0; pixel < mask.length; pixel++) {
      if (bitmap[pixel * 4 + 3] > 0) mask[pixel] = 1
    }
  }
  return mask
}

export class DesktopMascotService implements DesktopMascotRuntime {
  private disposed = false
  private window: BrowserWindow | null = null
  private data: DesktopMascotData | null = null
  private ready = false
  private working = false
  private animate = true
  private hitMask: Uint8Array = new Uint8Array()
  private hitSize = { width: 0, height: 0 }
  private dragOffset: Point | null = null
  private mouseIgnored: boolean | null = null
  private noticeTimer: ReturnType<typeof setTimeout> | null = null
  private trackingTimer: ReturnType<typeof setInterval> | null = null
  private lastCursor: Point | null = null
  private cursorMovedAt = 0
  private animationPaused = false
  private idleMessagePaused = false
  private motionOverride = false
  private menuLabels: DesktopMascotMenuLabels | null = null
  private idleMessage: DesktopMascotIdleMessage | undefined
  private colors: DesktopMascotColors | undefined
  private decodedImage: { imageUrl: string; image: NativeImage } | null = null
  private frames: NativeImage[] = []
  private preferredWidth = 144
  private menuRequestId = 0

  constructor(private readonly options: DesktopMascotOptions) {}

  setReady(ready: boolean, labels?: DesktopMascotMenuLabels, colors?: DesktopMascotColors): void {
    if (this.disposed) return
    this.ready = ready
    if (labels) this.menuLabels = labels
    if (colors) this.colors = colors
    if (ready && this.window && this.data) {
      if (colors) this.updateData({ colors })
      return
    }
    this.sync()
  }

  getData(sender: WebContents): DesktopMascotData | null {
    return this.window?.webContents === sender ? this.data : null
  }

  setDecodedImage(sender: WebContents, imageUrl: string, pngDataUrl: string): void {
    if (
      sender !== this.window?.webContents ||
      !this.data?.needsImageDecode ||
      this.data.imageUrl !== imageUrl
    )
      return
    const image = nativeImage.createFromDataURL(pngDataUrl)
    if (image.isEmpty()) return
    this.decodedImage = { imageUrl, image }
    try {
      this.sync()
    } catch (error) {
      this.options.onError(error)
    }
  }

  setIdleMessage(message: DesktopMascotIdleMessage): void {
    this.idleMessage = {
      text: message.text.trim().slice(0, 240),
      author: message.author.trim().slice(0, 80),
    }
    if (!this.data || this.idleMessagePaused) return
    this.updateData({ idleMessage: this.idleMessage })
  }

  setActivity(working: boolean, animate: boolean): void {
    this.working = working
    this.animate = animate
    if (!this.data) return
    this.updateData({
      state: working ? 'working' : 'idle',
      animate: animate && !this.animationPaused,
    })
    if (working || !animate) this.updateLook(null)
  }

  /** 播放偏好只同步状态，不重新读取图集和计算命中区域。 */
  syncPreferences(): void {
    if (this.disposed || !this.data) return
    const preferences = this.options.readPreferences()
    this.animationPaused = preferences.desktopMascotAnimationPaused === true
    this.idleMessagePaused = preferences.desktopMascotIdleMessagePaused === true
    this.motionOverride = typeof preferences.desktopMascotAnimationPaused === 'boolean'
    this.updateData({
      fps: preferences.desktopMascotFps ?? null,
      animate: this.animate && !this.animationPaused,
      motionOverride: this.motionOverride,
      idleMessage: this.idleMessagePaused ? undefined : this.idleMessage,
    })
    if (this.animationPaused) this.updateLook(null)
  }

  showNotice(text: string, reaction?: 'success' | 'failure' | 'stopped'): void {
    if (!this.data || !text.trim()) return
    if (this.noticeTimer) clearTimeout(this.noticeTimer)
    this.updateData({ notice: text.trim().slice(0, 240), reaction })
    if (reaction) this.updateLook(null)
    this.noticeTimer = setTimeout(() => {
      this.noticeTimer = null
      if (!this.data) return
      this.updateData({ notice: undefined, reaction: undefined })
    }, 8000)
  }

  startDrag(sender: WebContents, offset: unknown): boolean {
    if (!this.window || sender !== this.window.webContents || !this.data || this.dragOffset)
      return false
    if (!offset || typeof offset !== 'object') return false
    const { x, y, session } = offset as DesktopMascotDragStart
    if (
      !Number.isSafeInteger(session) ||
      session <= 0 ||
      !Number.isFinite(x) ||
      !Number.isFinite(y) ||
      x < 0 ||
      y < 0 ||
      x >= this.hitSize.width ||
      y >= this.hitSize.height ||
      this.hitMask[Math.floor(y) * this.hitSize.width + Math.floor(x)] !== 1
    )
      return false
    // 抓取点来自按下事件，不用延后处理 IPC 时的鼠标位置重新命中。
    this.dragOffset = { x, y }
    this.setMouseIgnored(false)
    this.updateData({ dragging: true, dragSession: session })
    this.updateLook(null)
    this.moveToCursor()
    return true
  }

  handlePointer(sender: WebContents, action: unknown, session?: unknown): void {
    const win = this.window
    if (!win || sender !== win.webContents) return
    if (action !== 'hover' && session !== this.data?.dragSession) return
    const cursor = screen.getCursorScreenPoint()
    const bounds = win.getBounds()
    const x = Math.floor(cursor.x - bounds.x - (this.data?.offsetX ?? 0))
    const y = Math.floor(cursor.y - bounds.y - (this.data?.offsetY ?? 0))
    const hit =
      x >= 0 &&
      y >= 0 &&
      x < this.hitSize.width &&
      y < this.hitSize.height &&
      this.hitMask[y * this.hitSize.width + x] === 1
    if (action === 'move' && this.dragOffset) {
      this.moveToCursor()
    } else if (action === 'end' && this.dragOffset) {
      this.moveToCursor()
      this.dragOffset = null
      this.updateData({ dragging: false, dragSession: this.data?.dragSession })
      const finalBounds = win.getBounds()
      try {
        this.options.savePosition({
          x: finalBounds.x + (this.data?.offsetX ?? 0),
          y: finalBounds.y + (this.data?.offsetY ?? 0),
        })
      } catch (error) {
        this.options.onError(error)
      }
      this.setMouseIgnored(true)
    } else if (action === 'hover' && !this.dragOffset) {
      this.setMouseIgnored(!hit)
    }
  }

  sync(): void {
    if (this.disposed) return
    if (this.dragOffset) {
      this.dragOffset = null
      this.updateData({ dragging: false, dragSession: this.data?.dragSession })
    }
    const preferences = this.options.readPreferences()
    this.animationPaused = preferences.desktopMascotAnimationPaused === true
    this.idleMessagePaused = preferences.desktopMascotIdleMessagePaused === true
    this.motionOverride = typeof preferences.desktopMascotAnimationPaused === 'boolean'
    if (!this.ready || !this.colors || preferences.desktopMascotEnabled === false) {
      this.close()
      return
    }
    const appearance = this.options.resolveAssets()
    if (!appearance?.mascotUrl || appearance.mascot?.opacity === 0) {
      this.close()
      return
    }
    if (this.decodedImage?.imageUrl !== appearance.mascotUrl) this.decodedImage = null
    const image = this.decodedImage?.image ?? nativeImage.createFromDataURL(appearance.mascotUrl)
    const frames: NativeImage[] = []
    const animation = appearance.mascot?.animation
    if (animation && appearance.mascotAnimationUrl) {
      const sheet = nativeImage.createFromDataURL(appearance.mascotAnimationUrl)
      const sheetSize = sheet.getSize()
      const frameWidth = sheetSize.width / animation.columns
      const frameHeight = sheetSize.height / 2
      if (!sheet.isEmpty() && Number.isInteger(frameWidth) && Number.isInteger(frameHeight)) {
        for (let row = 0; row < 2; row++) {
          for (let column = 0; column < animation.columns; column++) {
            frames.push(
              sheet.crop({
                x: column * frameWidth,
                y: row * frameHeight,
                width: frameWidth,
                height: frameHeight,
              })
            )
          }
        }
      }
    }
    const hasAnimation = frames.length > 0
    const needsImageDecode =
      !hasAnimation && image.isEmpty() && appearance.mascotUrl.startsWith('data:image/webp;')
    if (!hasAnimation && !needsImageDecode) {
      if (image.isEmpty()) {
        this.close()
        return
      }
      frames.push(image)
    }
    if (hasAnimation && animation && appearance.mascotResultUrl) {
      const resultSheet = nativeImage.createFromDataURL(appearance.mascotResultUrl)
      const size = resultSheet.getSize()
      const frameWidth = size.width / animation.columns
      const frameHeight = size.height / 2
      if (!resultSheet.isEmpty() && Number.isInteger(frameWidth) && Number.isInteger(frameHeight)) {
        for (let row = 0; row < 2; row++) {
          for (let column = 0; column < animation.columns; column++) {
            frames.push(
              resultSheet.crop({
                x: column * frameWidth,
                y: row * frameHeight,
                width: frameWidth,
                height: frameHeight,
              })
            )
          }
        }
      }
    }
    let hasDrag = false
    if (hasAnimation && animation && appearance.mascotDragUrl) {
      const dragSheet = nativeImage.createFromDataURL(appearance.mascotDragUrl)
      const size = dragSheet.getSize()
      const frameWidth = size.width / animation.columns
      if (!dragSheet.isEmpty() && Number.isInteger(frameWidth)) {
        hasDrag = true
        for (let column = 0; column < animation.columns; column++) {
          frames.push(
            dragSheet.crop({ x: column * frameWidth, y: 0, width: frameWidth, height: size.height })
          )
        }
      }
    }
    let hasLook = false
    if (hasAnimation && appearance.mascotLookUrl) {
      const lookSheet = nativeImage.createFromDataURL(appearance.mascotLookUrl)
      const size = lookSheet.getSize()
      if (!lookSheet.isEmpty() && size.width >= 3 && size.height >= 3) {
        const lookWidth = Math.floor(size.width / 3)
        const lookHeight = Math.floor(size.height / 3)
        hasLook = true
        for (let row = 0; row < 3; row++) {
          for (let column = 0; column < 3; column++) {
            frames.push(
              lookSheet.crop({
                x: column * lookWidth,
                y: row * lookHeight,
                width: lookWidth,
                height: lookHeight,
              })
            )
          }
        }
      }
    }

    const currentBounds = this.window?.getBounds()
    const mainBounds = this.options.getInitialBounds()
    const saved = currentBounds
      ? {
          x: currentBounds.x + (this.data?.offsetX ?? 0),
          y: currentBounds.y + (this.data?.offsetY ?? 0),
        }
      : preferences.desktopMascotPosition
    const display = saved
      ? screen.getDisplayNearestPoint(saved)
      : mainBounds
        ? screen.getDisplayMatching(mainBounds)
        : screen.getPrimaryDisplay()
    const area = display.workArea
    this.frames = frames
    this.preferredWidth = appearance.mascot?.width ?? 144
    const { width, height } = getMascotSize(
      frames[0]?.getSize() ?? { width: 1, height: 1 },
      this.preferredWidth,
      area
    )
    const position = appearance.mascot?.position ?? 'bottom-right'
    // 保存角色坐标；气泡换边或横向避让时不移动角色。
    const layout = getMascotLayout(
      saved ?? {
        x: position.endsWith('left')
          ? area.x + MASCOT_MARGIN
          : area.x + area.width - width - MASCOT_MARGIN,
        y: position.startsWith('top')
          ? area.y + MASCOT_MARGIN
          : area.y + area.height - height - MASCOT_MARGIN,
      },
      { width, height },
      area
    )
    const { bounds } = layout
    this.hitSize = { width, height }
    this.hitMask = frames.length
      ? createMascotHitMask(frames.map(frame => frame.resize({ width, height })))
      : new Uint8Array(width * height)
    this.data = {
      imageUrl: appearance.mascotUrl,
      needsImageDecode,
      opacity: appearance.mascot?.opacity ?? 1,
      state: this.working ? 'working' : 'idle',
      animate: this.animate && !this.animationPaused,
      motionOverride: this.motionOverride,
      fps: preferences.desktopMascotFps ?? null,
      width,
      height,
      offsetX: layout.offset.x,
      offsetY: layout.offset.y,
      noticeBelow: layout.noticeBelow,
      dragging: false,
      colors: this.colors,
      notice: this.data?.notice,
      idleMessage: this.idleMessagePaused ? undefined : this.idleMessage,
      reaction: this.data?.reaction,
      lookFrame: null,
      ...(hasAnimation && animation
        ? {
            animation: {
              imageUrl: appearance.mascotAnimationUrl!,
              columns: animation.columns,
              idleFps: animation.idleFps ?? 4,
              workingFps: animation.workingFps ?? 8,
              ...(hasLook ? { lookImageUrl: appearance.mascotLookUrl } : {}),
              ...(appearance.mascotResultUrl ? { resultImageUrl: appearance.mascotResultUrl } : {}),
              ...(hasDrag ? { dragImageUrl: appearance.mascotDragUrl } : {}),
            },
          }
        : {}),
    }

    let win = this.window
    if (!win) {
      win = new BrowserWindow({
        ...bounds,
        frame: false,
        transparent: true,
        backgroundColor: '#00000000',
        hasShadow: false,
        resizable: false,
        minimizable: false,
        maximizable: false,
        fullscreenable: false,
        focusable: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        show: false,
        webPreferences: {
          nodeIntegration: false,
          contextIsolation: true,
          preload: path.join(__dirname, '..', 'desktopMascotPreload.js'),
        },
      })
      this.window = win
      const createdWindow = win
      win.webContents.on('context-menu', () => {
        void this.showContextMenu(createdWindow).catch(error => this.options.onError(error))
      })
      win.once('ready-to-show', () => {
        if (this.window === createdWindow && !createdWindow.isDestroyed())
          createdWindow.showInactive()
      })
      win.on('closed', () => {
        if (this.window === createdWindow) this.close()
      })
      screen.on('display-removed', this.handleDisplayChanged)
      screen.on('display-metrics-changed', this.handleDisplayChanged)
      const devServer = process.env.VITE_DEV_SERVER_URL
      const loading = devServer
        ? win.loadURL(`${devServer.replace(/\/$/, '')}/mascot.html`)
        : win.loadFile(path.join(app.getAppPath(), 'dist', 'mascot.html'))
      void loading.catch(error => {
        if (this.window !== createdWindow) return
        this.close()
        this.options.onError(error)
      })
    } else {
      win.setBounds(bounds)
      win.webContents.send('desktop-mascot:changed', this.data)
    }

    this.setMouseIgnored(true)
    if (this.trackingTimer) clearInterval(this.trackingTimer)
    this.trackingTimer = this.data.animation?.lookImageUrl
      ? setInterval(this.trackCursor, 100)
      : null
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.ready = false
    this.close()
  }

  private close(): void {
    const win = this.window
    this.window = null
    this.data = null
    this.decodedImage = null
    this.frames = []
    this.dragOffset = null
    this.mouseIgnored = null
    if (this.noticeTimer) clearTimeout(this.noticeTimer)
    this.noticeTimer = null
    if (this.trackingTimer) clearInterval(this.trackingTimer)
    this.trackingTimer = null
    this.lastCursor = null
    if (win) {
      screen.removeListener('display-removed', this.handleDisplayChanged)
      screen.removeListener('display-metrics-changed', this.handleDisplayChanged)
      if (!win.isDestroyed()) win.close()
    }
  }

  private setMouseIgnored(ignore: boolean): void {
    if (!this.window || this.mouseIgnored === ignore) return
    this.window.setIgnoreMouseEvents(ignore, { forward: true })
    this.mouseIgnored = ignore
  }

  private moveToCursor(): void {
    if (!this.window || !this.data || !this.dragOffset) return
    const cursor = screen.getCursorScreenPoint()
    const area = screen.getDisplayNearestPoint(cursor).workArea
    const size = getMascotSize(
      this.frames[0]?.getSize() ?? { width: 1, height: 1 },
      this.preferredWidth,
      area
    )
    if (size.width !== this.hitSize.width || size.height !== this.hitSize.height) {
      this.dragOffset = {
        x: (this.dragOffset.x / this.hitSize.width) * size.width,
        y: (this.dragOffset.y / this.hitSize.height) * size.height,
      }
      this.hitSize = size
      this.hitMask = this.frames.length
        ? createMascotHitMask(this.frames.map(frame => frame.resize(size)))
        : new Uint8Array(size.width * size.height)
    }
    const layout = getMascotLayout(
      { x: cursor.x - this.dragOffset.x, y: cursor.y - this.dragOffset.y },
      size,
      area
    )
    const update = {
      width: size.width,
      height: size.height,
      offsetX: layout.offset.x,
      offsetY: layout.offset.y,
      noticeBelow: layout.noticeBelow,
    }
    this.window.setBounds(layout.bounds)
    if (
      Object.entries(update).some(
        ([key, value]) => this.data?.[key as keyof DesktopMascotData] !== value
      )
    )
      this.updateData(update)
  }

  private async showContextMenu(win: BrowserWindow): Promise<void> {
    const requestId = ++this.menuRequestId
    const tasks = await this.options.loadTaskMenu()
    const labels = this.menuLabels
    if (this.window !== win || !labels || requestId !== this.menuRequestId) return
    const taskItems = (action: 'start' | 'stop'): MenuItemConstructorOptions[] => {
      const items = tasks?.[action] ?? []
      return items.length
        ? items.map(item => ({
            label: item.label.replace(/&/g, '&&'),
            enabled: Boolean(tasks?.enabled && item.enabled),
            click: () => {
              if (this.window === win) this.options.onTaskAction({ action, taskId: item.taskId })
            },
          }))
        : [
            {
              label:
                !tasks || (action === 'start' && tasks.startFailed)
                  ? labels.tasksUnavailable
                  : action === 'start'
                    ? labels.noTasks
                    : labels.noRunningTasks,
              enabled: false,
            },
          ]
    }
    const animationPaused =
      this.animationPaused ||
      (!this.motionOverride && systemPreferences.getAnimationSettings().prefersReducedMotion)
    Menu.buildFromTemplate([
      { label: labels.quickStart, submenu: taskItems('start') },
      { label: labels.stopTask, submenu: taskItems('stop') },
      { type: 'separator' },
      {
        label: labels.refreshIdleMessage,
        enabled: !this.idleMessagePaused && !this.working,
        click: () => {
          if (this.window === win && !this.idleMessagePaused && !this.working)
            this.options.onRefreshIdleMessage()
        },
      },
      {
        label: this.idleMessagePaused ? labels.resumeIdleMessage : labels.pauseIdleMessage,
        click: () => {
          if (this.window !== win) return
          const paused = !this.idleMessagePaused
          try {
            this.options.saveIdleMessagePaused(paused)
            this.idleMessagePaused = paused
            if (this.data) {
              this.updateData({ idleMessage: paused ? undefined : this.idleMessage })
            }
          } catch (error) {
            this.options.onError(error)
          }
        },
      },
      {
        label: animationPaused ? labels.resumeAnimation : labels.pauseAnimation,
        click: () => {
          if (this.window !== win) return
          const paused = !animationPaused
          try {
            this.options.saveAnimationPaused(paused)
            this.animationPaused = paused
            this.motionOverride = true
            this.updateData({ motionOverride: true })
            this.setActivity(this.working, this.animate)
          } catch (error) {
            this.options.onError(error)
          }
        },
      },
    ]).popup({ window: win })
  }

  private updateData(update: DesktopMascotUpdate): void {
    if (!this.data) return
    this.data = { ...this.data, ...update }
    this.window?.webContents.send('desktop-mascot:updated', update)
  }

  private updateLook(frame: number | null): void {
    if (!this.data || this.data.lookFrame === frame) return
    this.data = { ...this.data, lookFrame: frame }
    // 追踪只发送方向，不在鼠标移动时反复传输整张精灵图。
    this.window?.webContents.send('desktop-mascot:look', frame)
  }

  private readonly trackCursor = (): void => {
    if (
      !this.window ||
      !this.data ||
      this.working ||
      !this.animate ||
      this.animationPaused ||
      this.data.reaction ||
      this.dragOffset
    ) {
      this.updateLook(null)
      return
    }
    const cursor = screen.getCursorScreenPoint()
    if (!this.lastCursor || cursor.x !== this.lastCursor.x || cursor.y !== this.lastCursor.y) {
      this.cursorMovedAt = Date.now()
      this.lastCursor = cursor
    }
    const bounds = this.window.getBounds()
    const x = cursor.x - (bounds.x + this.data.offsetX + this.hitSize.width / 2)
    const y = cursor.y - (bounds.y + this.data.offsetY + this.hitSize.height / 2)
    const distance = Math.hypot(x, y)
    if (Date.now() - this.cursorMovedAt > 1000 || distance > 900) {
      this.updateLook(null)
      return
    }
    const directions = [5, 8, 7, 6, 3, 0, 1, 2]
    const direction = (Math.round(Math.atan2(y, x) / (Math.PI / 4)) + 8) % 8
    this.updateLook(distance < 24 ? 4 : directions[direction])
  }

  private readonly handleDisplayChanged = (): void => {
    try {
      this.sync()
    } catch (error) {
      this.options.onError(error)
    }
  }
}
