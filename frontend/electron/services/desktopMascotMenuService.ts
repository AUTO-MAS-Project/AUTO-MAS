import { getDevelopmentServerUrl, getRendererEnvironmentArguments } from './instanceConfig'
import { app, BrowserWindow, ipcMain, screen } from 'electron'
import type { Point } from 'electron'
import * as path from 'path'
import type {
  DesktopMascotMenuAction,
  DesktopMascotMenuData,
  DesktopMascotMenuResult,
} from '../../src/types/desktopMascot'

export interface DesktopMascotMenuOptions {
  execute(action: DesktopMascotMenuAction): Promise<DesktopMascotMenuResult>
  onError(error: unknown): void
  onClosed(): void
}

export interface DesktopMascotMenuRuntime {
  open(position: Point, data: DesktopMascotMenuData): void
  update(data: DesktopMascotMenuData): void
  close(): void
  dispose(): void
}

/** 菜单弹层只承载包的声明式 UI，能力执行始终交回宿主。 */
export class DesktopMascotMenuService implements DesktopMascotMenuRuntime {
  private window: BrowserWindow | null = null
  private data: DesktopMascotMenuData | null = null
  private disposed = false
  private pending = false
  private anchor: Point | null = null
  private ready = false
  private sized = false
  private shown = false

  constructor(private readonly options: DesktopMascotMenuOptions) {
    ipcMain.handle('desktop-mascot-menu:get', event =>
      event.sender === this.window?.webContents ? this.data : null
    )
    ipcMain.handle('desktop-mascot-menu:viewport', event => {
      if (event.sender !== this.window?.webContents || !this.anchor) return null
      const area = screen.getDisplayNearestPoint(this.anchor).workArea
      return { width: Math.max(1, area.width - 16), height: Math.max(1, area.height - 16) }
    })
    this.onResize = (event, size: unknown) => {
      const win = this.window
      if (
        !win ||
        event.sender !== win.webContents ||
        !this.anchor ||
        !size ||
        typeof size !== 'object' ||
        !('width' in size) ||
        typeof size.width !== 'number' ||
        !Number.isFinite(size.width) ||
        size.width <= 0 ||
        !('height' in size) ||
        typeof size.height !== 'number' ||
        !Number.isFinite(size.height) ||
        size.height <= 0
      )
        return
      const area = screen.getDisplayNearestPoint(this.anchor).workArea
      const width = Math.min(Math.ceil(size.width), Math.max(1, area.width - 16))
      const height = Math.min(Math.ceil(size.height), Math.max(1, area.height - 16))
      win.setBounds({
        x: Math.max(area.x, Math.min(this.anchor.x, area.x + area.width - width)),
        y: Math.max(area.y, Math.min(this.anchor.y, area.y + area.height - height)),
        width,
        height,
      })
      this.sized = true
      this.showWhenReady()
    }
    ipcMain.on('desktop-mascot-menu:resize', this.onResize)
    ipcMain.handle('desktop-mascot-menu:execute', async (event, action: unknown) => {
      if (event.sender !== this.window?.webContents || !this.data || this.pending)
        return { success: false }
      if (
        !action ||
        typeof action !== 'object' ||
        !('capability' in action) ||
        typeof action.capability !== 'string' ||
        ('value' in action && typeof action.value !== 'string')
      )
        return { success: false }
      const win = this.window
      this.pending = true
      try {
        return await this.options.execute({
          capability: action.capability,
          ...('value' in action ? { value: action.value as string } : {}),
        })
      } catch (error) {
        this.options.onError(error)
        return { success: false, message: this.data?.unavailableLabel }
      } finally {
        if (this.window === win) this.pending = false
      }
    })
    this.onClose = event => {
      if (event.sender === this.window?.webContents) this.close()
    }
    ipcMain.on('desktop-mascot-menu:close', this.onClose)
  }

  private readonly onClose: (event: Electron.IpcMainEvent) => void
  private readonly onResize: (event: Electron.IpcMainEvent, size: unknown) => void

  private showWhenReady(): void {
    if (!this.window || !this.ready || !this.sized || this.shown) return
    this.shown = true
    this.window.show()
    this.window.focus()
  }

  open(position: Point, data: DesktopMascotMenuData): void {
    if (this.disposed) return
    this.close()
    this.data = data
    this.anchor = position
    const area = screen.getDisplayNearestPoint(position).workArea
    const win = new BrowserWindow({
      x: Math.max(area.x, Math.min(position.x, area.x + area.width - 1)),
      y: Math.max(area.y, Math.min(position.y, area.y + area.height - 1)),
      width: 1,
      height: 1,
      frame: false,
      transparent: true,
      backgroundColor: '#00000000',
      resizable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      show: false,
      webPreferences: {
        additionalArguments: getRendererEnvironmentArguments(),
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, '..', 'desktopMascotMenuPreload.js'),
      },
    })
    this.window = win
    win.once('ready-to-show', () => {
      if (this.window === win && !win.isDestroyed()) {
        this.ready = true
        this.showWhenReady()
      }
    })
    win.on('blur', () => {
      if (this.window === win) this.close()
    })
    win.on('closed', () => {
      if (this.window === win) this.close()
    })
    const devServer = getDevelopmentServerUrl()
    const loading = devServer
      ? win.loadURL(`${devServer.replace(/\/$/, '')}/mascot-menu.html`)
      : win.loadFile(path.join(app.getAppPath(), 'dist', 'mascot-menu.html'))
    void loading.catch(error => {
      if (this.window !== win) return
      this.close()
      this.options.onError(error)
    })
  }

  update(data: DesktopMascotMenuData): void {
    if (!this.window) return
    this.data = data
    this.window.webContents.send('desktop-mascot-menu:changed', data)
  }

  close(): void {
    const win = this.window
    this.window = null
    this.data = null
    this.pending = false
    this.anchor = null
    this.ready = false
    this.sized = false
    this.shown = false
    if (win) this.options.onClosed()
    if (win && !win.isDestroyed()) win.destroy()
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.close()
    for (const channel of [
      'desktop-mascot-menu:get',
      'desktop-mascot-menu:execute',
      'desktop-mascot-menu:viewport',
    ])
      ipcMain.removeHandler(channel)
    ipcMain.removeListener('desktop-mascot-menu:close', this.onClose)
    ipcMain.removeListener('desktop-mascot-menu:resize', this.onResize)
  }
}
