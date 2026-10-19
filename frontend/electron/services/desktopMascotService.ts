import { app, BrowserWindow, nativeImage, screen } from 'electron'
import type { NativeImage, Point, Size, WebContents } from 'electron'
import * as path from 'path'
import type {
  DesktopMascotColors,
  DesktopMascotData,
  DesktopMascotIdleMessage,
  DesktopMascotUpdate,
  DesktopMascotDragStart,
} from '../../src/types/desktopMascot'
import { getMascotLayout, getMascotSize, isMascotVisible } from './desktopMascotGeometry'
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

/** 各动作占连续的行，末行未用的格子不参与显示和鼠标命中。 */
function cropAnimationFrames(
  sheet: NativeImage,
  columns: number,
  frameCount: number,
  actions: number
): NativeImage[] {
  const { width, height } = sheet.getSize()
  const rows = Math.ceil(frameCount / columns)
  const frameWidth = width / columns
  const frameHeight = height / (rows * actions)
  if (sheet.isEmpty() || !Number.isInteger(frameWidth) || !Number.isInteger(frameHeight)) return []
  const frames: NativeImage[] = []
  for (let action = 0; action < actions; action++) {
    for (let frame = 0; frame < frameCount; frame++) {
      frames.push(
        sheet.crop({
          x: (frame % columns) * frameWidth,
          y: (action * rows + Math.floor(frame / columns)) * frameHeight,
          width: frameWidth,
          height: frameHeight,
        })
      )
    }
  }
  return frames
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
  private idleMessage: DesktopMascotIdleMessage | undefined
  private colors: DesktopMascotColors | undefined
  private decodedImage: { imageUrl: string; image: NativeImage } | null = null
  private sourceSize: Size = { width: 1, height: 1 }
  private maskSource: { size: Size; mask: Uint8Array } | null = null
  private hitMasks = new Map<string, Uint8Array>()
  private preferredWidth = 144
  private layoutRevision = 0

  constructor(private readonly options: DesktopMascotOptions) {}

  setReady(ready: boolean, colors?: DesktopMascotColors): void {
    if (this.disposed) return
    this.ready = ready
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
    const { x, y, session, revision } = offset as DesktopMascotDragStart
    if (
      revision !== this.layoutRevision ||
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
    try {
      this.setMouseIgnored(false)
      this.updateData({ dragging: true, dragSession: session })
      this.updateLook(null)
      this.moveToCursor()
      return true
    } catch (error) {
      this.finishDrag(false)
      this.options.onError(error)
      return false
    }
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
      try {
        this.moveToCursor()
      } catch (error) {
        this.finishDrag(true)
        this.options.onError(error)
      }
    } else if (action === 'end' && this.dragOffset) {
      try {
        this.moveToCursor()
      } catch (error) {
        this.options.onError(error)
      } finally {
        this.finishDrag(true)
      }
    } else if (action === 'hover' && !this.dragOffset) {
      this.setMouseIgnored(!hit)
    }
  }

  sync(): void {
    if (this.disposed) return
    this.layoutRevision++
    this.finishDrag(true)
    this.updateData({ revision: this.layoutRevision })
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
    const frameCount = animation?.frameCount ?? animation?.columns ?? 0
    if (animation && appearance.mascotAnimationUrl) {
      const sheet = nativeImage.createFromDataURL(appearance.mascotAnimationUrl)
      frames.push(...cropAnimationFrames(sheet, animation.columns, frameCount, 2))
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
      frames.push(...cropAnimationFrames(resultSheet, animation.columns, frameCount, 2))
    }
    let hasDrag = false
    if (hasAnimation && animation && appearance.mascotDragUrl) {
      const dragSheet = nativeImage.createFromDataURL(appearance.mascotDragUrl)
      const dragFrames = cropAnimationFrames(dragSheet, animation.columns, frameCount, 1)
      hasDrag = dragFrames.length > 0
      frames.push(...dragFrames)
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
    this.sourceSize = frames[0]?.getSize() ?? { width: 1, height: 1 }
    this.preferredWidth = appearance.mascot?.width ?? 144
    const { width, height } = getMascotSize(this.sourceSize, this.preferredWidth, area)
    // 载入时合并一次透明度，并预计算各显示器尺寸；拖动只切换缓存。
    const areas = screen.getAllDisplays().map(display => display.workArea)
    const sizes = areas.map(area => getMascotSize(this.sourceSize, this.preferredWidth, area))
    sizes.push({ width, height })
    const maskSize = sizes.reduce(
      (largest, size) =>
        size.width > largest.width || size.height > largest.height ? size : largest,
      { width, height }
    )
    this.hitMasks.clear()
    this.maskSource = {
      size: maskSize,
      mask: frames.length
        ? createMascotHitMask(frames.map(frame => frame.resize(maskSize)))
        : new Uint8Array(maskSize.width * maskSize.height),
    }
    for (const size of sizes) this.getHitMask(size)
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
      area,
      areas
    )
    const { bounds } = layout
    this.hitSize = { width, height }
    this.hitMask = this.getHitMask({ width, height })
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
      noticeWidth: layout.noticeWidth,
      noticeHeight: layout.noticeHeight,
      revision: this.layoutRevision,
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
              frameCount,
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
        if (this.window === createdWindow) this.options.onContextMenu(screen.getCursorScreenPoint())
      })
      const cancelRendererDrag = (): void => {
        if (this.window !== createdWindow) return
        this.layoutRevision++
        this.finishDrag(true)
        this.updateData({ revision: this.layoutRevision })
      }
      win.webContents.on('render-process-gone', cancelRendererDrag)
      win.webContents.on('did-start-navigation', (_event, _url, inPlace, mainFrame) => {
        if (mainFrame && !inPlace) cancelRendererDrag()
      })
      win.once('ready-to-show', () => {
        if (this.window === createdWindow && !createdWindow.isDestroyed())
          createdWindow.showInactive()
      })
      win.on('closed', () => {
        if (this.window === createdWindow) this.close()
      })
      screen.on('display-removed', this.handleDisplayChanged)
      screen.on('display-added', this.handleDisplayChanged)
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
    this.finishDrag(true)
    const win = this.window
    this.window = null
    if (win) this.options.onClosed()
    this.data = null
    this.decodedImage = null
    this.maskSource = null
    this.hitMasks.clear()
    this.dragOffset = null
    this.mouseIgnored = null
    if (this.noticeTimer) clearTimeout(this.noticeTimer)
    this.noticeTimer = null
    if (this.trackingTimer) clearInterval(this.trackingTimer)
    this.trackingTimer = null
    this.lastCursor = null
    if (win) {
      screen.removeListener('display-removed', this.handleDisplayChanged)
      screen.removeListener('display-added', this.handleDisplayChanged)
      screen.removeListener('display-metrics-changed', this.handleDisplayChanged)
      if (!win.isDestroyed()) win.close()
    }
  }

  private setMouseIgnored(ignore: boolean): void {
    if (!this.window || this.window.isDestroyed() || this.mouseIgnored === ignore) return
    this.window.setIgnoreMouseEvents(ignore, { forward: true })
    this.mouseIgnored = ignore
  }

  private moveToCursor(): void {
    if (!this.window || !this.data || !this.dragOffset) return
    const cursor = screen.getCursorScreenPoint()
    const area = screen.getDisplayNearestPoint(cursor).workArea
    const areas = screen.getAllDisplays().map(display => display.workArea)
    let size = this.hitSize
    const targetSize = getMascotSize(this.sourceSize, this.preferredWidth, area)
    const currentPosition = { x: cursor.x - this.dragOffset.x, y: cursor.y - this.dragOffset.y }
    const targetOffset = {
      x: (this.dragOffset.x / this.hitSize.width) * targetSize.width,
      y: (this.dragOffset.y / this.hitSize.height) * targetSize.height,
    }
    const targetPosition = { x: cursor.x - targetOffset.x, y: cursor.y - targetOffset.y }
    if (
      (isMascotVisible(currentPosition, size, [area]) &&
        isMascotVisible(targetPosition, targetSize, [area])) ||
      !isMascotVisible(currentPosition, size, areas)
    )
      size = targetSize
    const resized = size.width !== this.hitSize.width || size.height !== this.hitSize.height
    const offset = resized ? targetOffset : this.dragOffset
    const layout = getMascotLayout(
      { x: cursor.x - offset.x, y: cursor.y - offset.y },
      size,
      area,
      areas
    )
    const update = {
      width: size.width,
      height: size.height,
      offsetX: layout.offset.x,
      offsetY: layout.offset.y,
      noticeBelow: layout.noticeBelow,
      noticeWidth: layout.noticeWidth,
      noticeHeight: layout.noticeHeight,
    }
    this.window.setBounds(layout.bounds)
    if (resized) {
      this.dragOffset = offset
      this.hitSize = size
      this.hitMask = this.getHitMask(size)
    }
    if (
      Object.entries(update).some(
        ([key, value]) => this.data?.[key as keyof DesktopMascotData] !== value
      )
    )
      this.updateData(update)
  }

  private getHitMask(size: Size): Uint8Array {
    const key = `${size.width}x${size.height}`
    const cached = this.hitMasks.get(key)
    if (cached) return cached
    const source = this.maskSource
    if (source && size.width === source.size.width && size.height === source.size.height) {
      this.hitMasks.set(key, source.mask)
      return source.mask
    }
    const mask = new Uint8Array(size.width * size.height)
    if (source) {
      for (let y = 0; y < size.height; y++) {
        const top = Math.floor((y * source.size.height) / size.height)
        const bottom = Math.ceil(((y + 1) * source.size.height) / size.height)
        for (let x = 0; x < size.width; x++) {
          const left = Math.floor((x * source.size.width) / size.width)
          const right = Math.ceil(((x + 1) * source.size.width) / size.width)
          for (let sourceY = top; sourceY < bottom && !mask[y * size.width + x]; sourceY++) {
            for (let sourceX = left; sourceX < right; sourceX++) {
              if (source.mask[sourceY * source.size.width + sourceX]) {
                mask[y * size.width + x] = 1
                break
              }
            }
          }
        }
      }
    }
    this.hitMasks.set(key, mask)
    return mask
  }

  private finishDrag(savePosition: boolean): void {
    const wasDragging = Boolean(this.dragOffset)
    this.dragOffset = null
    try {
      if (wasDragging && savePosition && this.window && !this.window.isDestroyed() && this.data) {
        const bounds = this.window.getBounds()
        this.options.savePosition({
          x: bounds.x + this.data.offsetX,
          y: bounds.y + this.data.offsetY,
        })
      }
    } catch (error) {
      this.options.onError(error)
    } finally {
      this.setMouseIgnored(true)
      if (wasDragging && this.window && !this.window.isDestroyed())
        this.updateData({ dragging: false, dragSession: this.data?.dragSession })
    }
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
