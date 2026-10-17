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

  constructor(private readonly options: DesktopMascotMenuOptions) {
    ipcMain.handle('desktop-mascot-menu:get', event =>
      event.sender === this.window?.webContents ? this.data : null
    )
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

  open(position: Point, data: DesktopMascotMenuData): void {
    if (this.disposed) return
    this.close()
    this.data = data
    const area = screen.getDisplayNearestPoint(position).workArea
    const style = data.presentation.style
    const width = Math.min(Math.round(style?.width ?? 180), Math.max(1, area.width - 16))
    const columns = data.presentation.layout === 'grid' ? 2 : 1
    let rows = 0
    let separators = 0
    let column = 0
    for (const item of data.presentation.items) {
      if ('separator' in item) {
        separators++
        column = 0
      } else {
        if (column === 0) rows++
        column = (column + 1) % columns
      }
    }
    // 与菜单的内边距、行间距及分隔线高度一致，避免按整行给分隔线留白。
    const height = Math.min(
      Math.max(
        160,
        Math.round(
          rows * (style?.itemHeight ?? 32) +
            separators * 9 +
            Math.max(0, rows + separators - 1) * 2 +
            18
        )
      ),
      Math.max(1, area.height - 16)
    )
    const win = new BrowserWindow({
      x: Math.max(area.x, Math.min(position.x, area.x + area.width - width)),
      y: Math.max(area.y, Math.min(position.y, area.y + area.height - height)),
      width,
      height,
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
        nodeIntegration: false,
        contextIsolation: true,
        preload: path.join(__dirname, '..', 'desktopMascotMenuPreload.js'),
      },
    })
    this.window = win
    win.once('ready-to-show', () => {
      if (this.window === win && !win.isDestroyed()) {
        win.show()
        win.focus()
      }
    })
    win.on('blur', () => {
      if (this.window === win) this.close()
    })
    win.on('closed', () => {
      if (this.window === win) this.close()
    })
    const devServer = process.env.VITE_DEV_SERVER_URL
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
    if (win) this.options.onClosed()
    if (win && !win.isDestroyed()) win.destroy()
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.close()
    for (const channel of ['desktop-mascot-menu:get', 'desktop-mascot-menu:execute'])
      ipcMain.removeHandler(channel)
    ipcMain.removeListener('desktop-mascot-menu:close', this.onClose)
  }
}
