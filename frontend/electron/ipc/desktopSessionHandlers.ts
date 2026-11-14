import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  screen,
  shell,
  type IpcMainInvokeEvent,
  type Rectangle,
} from 'electron'
import { join } from 'node:path'
import { DesktopSessionService } from '../services/desktopSessionService'
import type { DesktopSessionRequest } from '../services/desktopSessionProtocol'
import {
  getBackendOwnership,
  getDevelopmentServerUrl,
  getRendererEnvironmentArguments,
} from '../services/instanceConfig'
import { isApplicationWindowSender } from './analyticsHandlers'

const confirmation =
  '桌面分身正在启动中或运行中。关闭该窗口会同时关闭桌面分身，其中所有正在运行的软件都会关闭，未保存的数据会丢失。是否继续？'
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function registerDesktopSession(getMainWindow: () => BrowserWindow | null, icon: string) {
  let preview: BrowserWindow | null = null
  let viewport: Rectangle | null = null
  let pending: DesktopSessionRequest | null = null
  let hidden = false
  let closeFlight: Promise<boolean> | null = null

  const service = new DesktopSessionService(
    snapshot => {
      if (preview && !preview.isDestroyed())
        preview.webContents.send('desktop-session:state', snapshot)
    },
    (transition, reconnect) => {
      const main = getMainWindow()
      if (main && !main.isDestroyed()) {
        main.webContents.send('desktop-session:endpoint', { transition, reconnect })
      }
    },
    action => {
      if (action === 'close') void confirmClose(false)
      else preview?.minimize()
    },
    id =>
      id !== undefined &&
      [getMainWindow(), preview].some(
        window => window && !window.isDestroyed() && window.webContents.id === id
      ),
    tasks => {
      const main = getMainWindow()
      if (main && !main.isDestroyed()) main.webContents.send('desktop-session:tasks-started', tasks)
    }
  )

  function fromPreview(event: IpcMainInvokeEvent): boolean {
    return (
      isApplicationWindowSender(event, preview, { allowDevelopment: true }) &&
      new URL(event.senderFrame!.url).hash === '#/desktop-session'
    )
  }

  function physicalBounds(): [number, number, number, number] {
    if (!preview || !viewport) throw new Error('预览尚未就绪')
    const window = preview.getContentBounds()
    const topLeft = screen.dipToScreenPoint({ x: window.x + viewport.x, y: window.y + viewport.y })
    const display = screen.getDisplayMatching(window)
    return [
      topLeft.x,
      topLeft.y,
      Math.max(1, Math.round(viewport.width * display.scaleFactor)),
      Math.max(1, Math.round(viewport.height * display.scaleFactor)),
    ]
  }

  function updateBounds() {
    if (preview && viewport) service.position(physicalBounds())
  }

  function confirmClose(closingApp: boolean): Promise<boolean> {
    if (closeFlight) return closeFlight
    closeFlight = (async () => {
      const window = preview
      if (!window || window.isDestroyed()) return true
      if (service.active) {
        if (window.isMinimized()) window.restore()
        if (!window.isVisible()) window.show()
        service.changeWindow('hidden')
        const { response } = await dialog.showMessageBox(window, {
          type: 'warning',
          title: '关闭桌面分身',
          message: confirmation,
          buttons: ['继续关闭', '取消'],
          defaultId: 1,
          cancelId: 1,
          noLink: true,
        })
        if (response !== 0) {
          if (!hidden) service.changeWindow('visible')
          return false
        }
      }
      try {
        await service.close(closingApp)
      } catch {
        await dialog.showMessageBox(window, {
          type: 'error',
          title: '桌面分身',
          message: '未能确认任务收尾或注销，请查看分身日志后重试。',
        })
        return false
      }
      window.destroy()
      return true
    })().finally(() => {
      closeFlight = null
    })
    return closeFlight
  }

  function showPreview() {
    if (preview && !preview.isDestroyed()) {
      if (preview.isMinimized()) preview.restore()
      preview.show()
      preview.focus()
      if (pending) preview.webContents.send('desktop-session:pending')
      return
    }
    viewport = null
    hidden = false
    const window = new BrowserWindow({
      title: '桌面分身 - AUTO-MAS',
      width: 1100,
      height: 735,
      minWidth: 720,
      minHeight: 470,
      icon,
      show: false,
      autoHideMenuBar: true,
      webPreferences: {
        preload: join(__dirname, '..', 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        additionalArguments: getRendererEnvironmentArguments(),
      },
    })
    preview = window
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    window.webContents.on('will-navigate', event => event.preventDefault())
    window.on('ready-to-show', () => window.show())
    window.on('close', event => {
      event.preventDefault()
      void confirmClose(false)
    })
    window.on('closed', () => {
      if (preview === window) preview = null
    })
    window.on('move', updateBounds)
    window.on('resize', updateBounds)
    window.on('minimize', () => service.changeWindow('minimized'))
    window.on('restore', () => {
      updateBounds()
      service.changeWindow(hidden ? 'hidden' : 'visible')
    })
    const dev = getDevelopmentServerUrl()
    if (dev) void window.loadURL(`${dev}#/desktop-session`)
    else
      void window.loadFile(join(app.getAppPath(), 'dist', 'index.html'), {
        hash: '/desktop-session',
      })
  }

  ipcMain.handle('desktop-session:open', (event, input: DesktopSessionRequest) => {
    if (!isApplicationWindowSender(event, getMainWindow(), { allowDevelopment: true })) {
      throw new Error('桌面分身入口不可用')
    }
    if (
      process.platform !== 'win32' ||
      process.arch !== 'x64' ||
      getBackendOwnership() !== 'owned'
    ) {
      throw new Error('桌面分身需要 Windows x64 和本机 MAS 后端')
    }
    if (
      !input ||
      !Array.isArray(input.queueIds) ||
      input.queueIds.length > 100 ||
      input.queueIds.some(id => typeof id !== 'string' || !uuid.test(id)) ||
      !['proxy', 'native'].includes(input.mode) ||
      !['1080p', 'primary'].includes(input.resolution)
    ) {
      throw new Error('队列选择无效')
    }
    pending = {
      queueIds: [...new Set(input.queueIds)],
      mode: input.mode,
      resolution: input.resolution,
    }
    showPreview()
  })
  ipcMain.handle('desktop-session:check', event => (fromPreview(event) ? service.check() : null))
  ipcMain.handle('desktop-session:pending', event => {
    if (!fromPreview(event)) return null
    const request = pending
    pending = null
    return request
  })
  ipcMain.handle('desktop-session:start', (event, input: DesktopSessionRequest) => {
    if (
      !fromPreview(event) ||
      !preview ||
      !input ||
      !Array.isArray(input.queueIds) ||
      input.queueIds.length > 100 ||
      input.queueIds.some(id => typeof id !== 'string' || !uuid.test(id)) ||
      !['proxy', 'native'].includes(input.mode) ||
      !['1080p', 'primary'].includes(input.resolution) ||
      (input.password !== undefined &&
        (typeof input.password !== 'string' || input.password.length > 512))
    ) {
      return { code: 'invalid_request', queues: [] }
    }
    return service.start(
      {
        queueIds: [...new Set(input.queueIds)],
        password: input.password,
        mode: input.mode,
        resolution: input.resolution,
      },
      preview.getNativeWindowHandle().readBigUInt64LE(),
      physicalBounds()
    )
  })
  ipcMain.on('desktop-session:bounds', (event, bounds: Rectangle) => {
    if (!fromPreview(event) || !bounds || !preview) return
    if (![bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isSafeInteger)) return
    const { width, height } = preview.getContentBounds()
    if (
      bounds.x < 0 ||
      bounds.y < 0 ||
      bounds.width < 1 ||
      bounds.height < 1 ||
      bounds.x + bounds.width > width + 2 ||
      bounds.y + bounds.height > height + 2
    )
      return
    viewport = bounds
    updateBounds()
  })
  ipcMain.on('desktop-session:window', (event, command: unknown) => {
    if (!fromPreview(event)) return
    if (command === 'minimize') preview?.minimize()
    else if (command === 'show' || command === 'hide') {
      hidden = command === 'hide'
      service.changeWindow(hidden ? 'hidden' : 'visible')
    }
  })
  ipcMain.on('desktop-session:volume', (event, volume: unknown) => {
    if (
      fromPreview(event) &&
      Number.isInteger(volume) &&
      Number(volume) >= 0 &&
      Number(volume) <= 100
    ) {
      service.changeVolume(Number(volume))
    }
  })
  ipcMain.handle('desktop-session:logs', event =>
    fromPreview(event) && service.logFolder ? shell.openPath(service.logFolder) : ''
  )

  return {
    get active() {
      return service.active
    },
    closeForAppQuit: () => confirmClose(true),
  }
}
