import { app, BrowserWindow, Menu, nativeImage, screen, systemPreferences } from 'electron'
import type { NativeImage, Point, WebContents } from 'electron'
import * as path from 'path'
import type {
  DesktopMascotColors,
  DesktopMascotData,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
  DesktopMascotUpdate,
} from '../../src/types/desktopMascot'
import { getAppearance } from './appearanceService'
import { getMascot } from './mascotPackageService'

export interface DesktopMascotPreferences {
  appearanceId?: string | null
  /** 为空时跟随主题；有值时使用独立安装的桌宠。 */
  desktopMascotId?: string | null
  desktopMascotEnabled?: boolean
  desktopMascotAnimationPaused?: boolean
  desktopMascotIdleMessagePaused?: boolean
  desktopMascotPosition?: Point
}

interface DesktopMascotOptions {
  readPreferences(): DesktopMascotPreferences
  savePosition(position: Point): void
  saveAnimationPaused(paused: boolean): void
  saveIdleMessagePaused(paused: boolean): void
  getMainWindow(): BrowserWindow | null
  onError(error: unknown): void
}

const MASCOT_MARGIN = 16
const NOTICE_WIDTH = 280
const NOTICE_HEIGHT = 108

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

export class DesktopMascotService {
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

  constructor(private readonly options: DesktopMascotOptions) {}

  setReady(ready: boolean, labels?: DesktopMascotMenuLabels, colors?: DesktopMascotColors): void {
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

  handlePointer(sender: WebContents, action: unknown): void {
    const win = this.window
    if (!win || sender !== win.webContents) return
    const cursor = screen.getCursorScreenPoint()
    const bounds = win.getBounds()
    const x = Math.floor(cursor.x - bounds.x - (bounds.width - this.hitSize.width))
    const y = Math.floor(cursor.y - bounds.y - (bounds.height - this.hitSize.height))
    const hit =
      x >= 0 &&
      y >= 0 &&
      x < this.hitSize.width &&
      y < this.hitSize.height &&
      this.hitMask[y * this.hitSize.width + x] === 1
    if (action === 'start' && hit) {
      this.dragOffset = { x: cursor.x - bounds.x, y: cursor.y - bounds.y }
      this.setMouseIgnored(false)
    } else if (action === 'move' && this.dragOffset) {
      win.setPosition(
        Math.round(cursor.x - this.dragOffset.x),
        Math.round(cursor.y - this.dragOffset.y)
      )
    } else if (action === 'end' && this.dragOffset) {
      this.dragOffset = null
      const area = screen.getDisplayMatching(bounds).workArea
      const left = Math.max(area.x, Math.min(bounds.x, area.x + area.width - bounds.width))
      const top = Math.max(area.y, Math.min(bounds.y, area.y + area.height - bounds.height))
      win.setPosition(left, top)
      try {
        this.options.savePosition({
          x: left + bounds.width - this.hitSize.width,
          y: top + bounds.height - this.hitSize.height,
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
    const preferences = this.options.readPreferences()
    this.animationPaused = preferences.desktopMascotAnimationPaused === true
    this.idleMessagePaused = preferences.desktopMascotIdleMessagePaused === true
    this.motionOverride = typeof preferences.desktopMascotAnimationPaused === 'boolean'
    if (!this.ready || !this.colors || preferences.desktopMascotEnabled === false) {
      this.close()
      return
    }
    const appearance = preferences.desktopMascotId
      ? getMascot(app.getPath('userData'), preferences.desktopMascotId)
      : preferences.appearanceId
        ? getAppearance(app.getPath('userData'), preferences.appearanceId)
        : null
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
    const mainBounds = this.options.getMainWindow()?.getBounds()
    const display = currentBounds
      ? screen.getDisplayMatching(currentBounds)
      : mainBounds
        ? screen.getDisplayMatching(mainBounds)
        : screen.getPrimaryDisplay()
    const area = display.workArea
    const sourceSize = frames[0]?.getSize() ?? { width: 1, height: 1 }
    const scale = Math.min(
      (appearance.mascot?.width ?? 144) / sourceSize.width,
      (area.width * 0.35) / sourceSize.width,
      (area.height * 0.3) / sourceSize.height
    )
    const width = Math.max(1, Math.round(sourceSize.width * scale))
    const height = Math.max(1, Math.round(sourceSize.height * scale))
    const position = appearance.mascot?.position ?? 'bottom-right'
    // 保存角色坐标；说话框始终预留透明空间，显示和收起都不改变窗口大小。
    const saved = currentBounds
      ? {
          x: currentBounds.x + currentBounds.width - this.hitSize.width,
          y: currentBounds.y + currentBounds.height - this.hitSize.height,
        }
      : preferences.desktopMascotPosition
    const windowWidth = Math.max(width, NOTICE_WIDTH)
    const windowHeight = height + NOTICE_HEIGHT
    const bounds = {
      x:
        (saved?.x ??
          (position.endsWith('left')
            ? area.x + MASCOT_MARGIN
            : area.x + area.width - width - MASCOT_MARGIN)) -
        (windowWidth - width),
      y:
        (saved?.y ??
          (position.startsWith('top')
            ? area.y + MASCOT_MARGIN
            : area.y + area.height - height - MASCOT_MARGIN)) - NOTICE_HEIGHT,
      width: windowWidth,
      height: windowHeight,
    }
    const targetArea = screen.getDisplayMatching(bounds).workArea
    bounds.x = Math.max(
      targetArea.x,
      Math.min(bounds.x, targetArea.x + targetArea.width - windowWidth)
    )
    bounds.y = Math.max(
      targetArea.y,
      Math.min(bounds.y, targetArea.y + targetArea.height - windowHeight)
    )
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
      width,
      height,
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
      win.webContents.on('context-menu', () => this.showContextMenu(createdWindow))
      win.once('ready-to-show', () => {
        if (!createdWindow.isDestroyed()) createdWindow.showInactive()
      })
      win.on('closed', () => {
        if (this.window !== createdWindow) return
        this.window = null
        this.data = null
        this.decodedImage = null
        if (this.noticeTimer) clearTimeout(this.noticeTimer)
        this.noticeTimer = null
        if (this.trackingTimer) clearInterval(this.trackingTimer)
        this.trackingTimer = null
        this.lastCursor = null
        screen.removeListener('display-removed', this.handleDisplayChanged)
        screen.removeListener('display-metrics-changed', this.handleDisplayChanged)
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

  close(): void {
    const win = this.window
    this.window = null
    this.data = null
    this.decodedImage = null
    this.dragOffset = null
    this.mouseIgnored = null
    if (this.noticeTimer) clearTimeout(this.noticeTimer)
    this.noticeTimer = null
    if (this.trackingTimer) clearInterval(this.trackingTimer)
    this.trackingTimer = null
    this.lastCursor = null
    if (win && !win.isDestroyed()) {
      screen.removeListener('display-removed', this.handleDisplayChanged)
      screen.removeListener('display-metrics-changed', this.handleDisplayChanged)
      win.close()
    }
  }

  private setMouseIgnored(ignore: boolean): void {
    if (!this.window || this.mouseIgnored === ignore) return
    this.window.setIgnoreMouseEvents(ignore, { forward: true })
    this.mouseIgnored = ignore
  }

  private showContextMenu(win: BrowserWindow): void {
    const labels = this.menuLabels
    if (this.window !== win || !labels) return
    const animationPaused =
      this.animationPaused ||
      (!this.motionOverride && systemPreferences.getAnimationSettings().prefersReducedMotion)
    Menu.buildFromTemplate([
      {
        label: this.idleMessagePaused ? labels.resumeIdleMessage : labels.pauseIdleMessage,
        click: () => {
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
    const x = cursor.x - (bounds.x + bounds.width - this.hitSize.width / 2)
    const y = cursor.y - (bounds.y + bounds.height - this.hitSize.height / 2)
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
