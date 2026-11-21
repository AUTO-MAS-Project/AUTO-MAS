import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  screen,
  shell,
  type IpcMainInvokeEvent,
  type MessageBoxOptions,
  type Rectangle,
} from 'electron'
import { join } from 'node:path'
import { readdir, readFile } from 'node:fs/promises'
import AdmZip = require('adm-zip')
import { DesktopSessionService } from '../services/desktopSessionService'
import { beginMainFeature } from '../services/featureAnalytics'
import {
  MAX_DESKTOP_SESSION_TARGETS,
  type DesktopSessionRequest,
} from '../services/desktopSessionProtocol'
import {
  getBackendOwnership,
  getDevelopmentServerUrl,
  getRendererEnvironmentArguments,
} from '../services/instanceConfig'
import { isApplicationWindowSender } from './analyticsHandlers'
import desktopSessionMessages from '../services/desktopSessionMessages.json'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const MODES: readonly DesktopSessionRequest['mode'][] = ['proxy', 'native']
const RESOLUTIONS: readonly DesktopSessionRequest['resolution'][] = ['1080p', 'primary']

/** 入口与启动都走同一份校验；区别只在非法请求怎么报告，由调用方决定。 */
function normalizeRequest(input: unknown): DesktopSessionRequest | null {
  if (!input || typeof input !== 'object') return null
  const request = input as Partial<DesktopSessionRequest>
  if (
    !Array.isArray(request.queueIds) ||
    request.queueIds.length > MAX_DESKTOP_SESSION_TARGETS ||
    request.queueIds.some(id => typeof id !== 'string' || !uuid.test(id)) ||
    !MODES.includes(request.mode as DesktopSessionRequest['mode']) ||
    !RESOLUTIONS.includes(request.resolution as DesktopSessionRequest['resolution'])
  ) {
    return null
  }
  return {
    queueIds: [...new Set(request.queueIds.map(id => id.toLowerCase()))],
    mode: request.mode as DesktopSessionRequest['mode'],
    resolution: request.resolution as DesktopSessionRequest['resolution'],
  }
}

function supportsDesktopSession(): boolean {
  return process.platform === 'win32' && process.arch === 'x64' && getBackendOwnership() === 'owned'
}

export function registerDesktopSession(
  getMainWindow: () => BrowserWindow | null,
  icon: string,
  getLanguage: () => unknown
) {
  function labels() {
    const configured = getLanguage()
    const locale = (typeof configured === 'string' ? configured : app.getLocale()).toLowerCase()
    if (locale.startsWith('zh')) return desktopSessionMessages['zh-CN']
    if (locale.startsWith('ja')) return desktopSessionMessages['ja-JP']
    return desktopSessionMessages['en-US']
  }
  let preview: BrowserWindow | null = null
  let viewport: Rectangle | null = null
  const pending: DesktopSessionRequest[] = []
  let hidden = false
  let closeFlight: Promise<boolean> | null = null

  const service = new DesktopSessionService(
    snapshot => {
      if (preview && !preview.isDestroyed())
        preview.webContents.send('desktop-session:state', snapshot)
    },
    action => {
      if (action === 'close') void confirmClose()
      else preview?.minimize()
    },
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
    if (!preview || !viewport) throw new Error('preview_unavailable')
    const window = preview.getContentBounds()
    const display = screen.getDisplayMatching(window)
    return [
      Math.round(viewport.x * display.scaleFactor),
      Math.round(viewport.y * display.scaleFactor),
      Math.max(1, Math.round(viewport.width * display.scaleFactor)),
      Math.max(1, Math.round(viewport.height * display.scaleFactor)),
    ]
  }

  function updateBounds() {
    if (preview && viewport) service.position(physicalBounds())
  }

  function confirmClose(): Promise<boolean> {
    if (closeFlight) return closeFlight
    closeFlight = (async () => {
      await service.waitForStart()
      const window = preview
      const text = labels()
      let logoff = false
      if (service.active) {
        const owner = window && !window.isDestroyed() ? window : getMainWindow()
        if (owner && !owner.isDestroyed()) {
          if (owner.isMinimized()) owner.restore()
          if (!owner.isVisible()) owner.show()
        }
        service.changeWindow('hidden')
        const adopted = service.adopted
        const options: MessageBoxOptions = {
          type: 'warning',
          title: text.closeTitle,
          message: adopted ? text.adoptedCloseConfirm : text.closeConfirm,
          buttons: adopted
            ? [text.disconnectOnly, text.logoffDesktopSession, text.cancel]
            : [text.closeContinue, text.cancel],
          defaultId: adopted ? 0 : 1,
          cancelId: adopted ? 2 : 1,
          noLink: true,
        }
        const { response } =
          owner && !owner.isDestroyed()
            ? await dialog.showMessageBox(owner, options)
            : await dialog.showMessageBox(options)
        if (response !== 0 && !(adopted && response === 1)) {
          if (!hidden) service.changeWindow('visible')
          return false
        }
        logoff = !adopted || response === 1
      }
      try {
        await service.close({ logoff })
      } catch {
        const options: MessageBoxOptions = {
          type: 'error',
          title: text.title,
          message: text.closeFailed,
        }
        if (window && !window.isDestroyed()) {
          if (!hidden) service.changeWindow('visible')
          await dialog.showMessageBox(window, options)
        } else {
          await dialog.showMessageBox(options)
        }
        return false
      }
      if (window && !window.isDestroyed()) window.destroy()
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
      if (pending.length) preview.webContents.send('desktop-session:pending')
      return
    }
    viewport = null
    hidden = false
    const window = new BrowserWindow({
      title: `${labels().title} - AUTO-MAS`,
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
    window.on('page-title-updated', event => event.preventDefault())
    window.on('ready-to-show', () => window.show())
    window.on('close', event => {
      event.preventDefault()
      void confirmClose()
    })
    window.on('closed', () => {
      if (preview === window) {
        preview = null
        pending.length = 0
      }
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

  ipcMain.handle(
    'desktop-session:supported',
    event =>
      isApplicationWindowSender(event, getMainWindow(), { allowDevelopment: true }) &&
      supportsDesktopSession()
  )
  ipcMain.handle('desktop-session:open', (event, input: unknown) => {
    if (!isApplicationWindowSender(event, getMainWindow(), { allowDevelopment: true })) {
      throw new Error('entry_unavailable')
    }
    if (!supportsDesktopSession()) {
      throw new Error('unsupported_environment')
    }
    const request = normalizeRequest(input)
    if (!request) throw new Error('invalid_selection')
    pending.push(request)
    showPreview()
  })
  ipcMain.handle('desktop-session:check', event => (fromPreview(event) ? service.check() : null))
  ipcMain.handle('desktop-session:repair', (event, approved: unknown) =>
    fromPreview(event) ? service.repair(approved) : 'invalid_request'
  )
  ipcMain.handle('desktop-session:pending', event => {
    if (!fromPreview(event)) return null
    return pending.shift() ?? null
  })
  ipcMain.handle('desktop-session:start', (event, input: unknown) => {
    // 先确认来源，再做任何解析：fromPreview 之外的调用方拿不到校验细节。
    if (!fromPreview(event) || !preview) return { code: 'invalid_request', queues: [] }
    if (closeFlight) return { code: 'busy', queues: [] }
    const window = preview
    const request = normalizeRequest(input)
    const password = (input as Partial<DesktopSessionRequest> | null)?.password
    if (
      !request ||
      (password !== undefined && (typeof password !== 'string' || password.length > 512))
    ) {
      return { code: 'invalid_request', queues: [] }
    }
    return service.start(
      { ...request, password },
      window.getNativeWindowHandle().readBigUInt64LE(),
      physicalBounds(),
      {
        confirmTakeover: async () => {
          const text = labels()
          const { response } = await dialog.showMessageBox(window, {
            type: 'warning',
            title: text.takeoverTitle,
            message: text.takeoverConfirm,
            buttons: [text.takeoverContinue, text.cancel],
            defaultId: 1,
            cancelId: 1,
            noLink: true,
          })
          return response === 0
        },
        confirmTaskDispatch: async ({ desktop, main }) => {
          const text = labels()
          const detail = [
            [text.mainFallbackMainGroup, ...main.map(target => `• ${target.label}`)].join('\n'),
          ]
          if (desktop.length) {
            detail.push(
              [text.mainFallbackDesktopGroup, ...desktop.map(target => `• ${target.label}`)].join(
                '\n'
              )
            )
          }
          service.changeWindow('hidden')
          try {
            const { response } = await dialog.showMessageBox(window, {
              type: 'warning',
              title: text.mainFallbackTitle,
              message: text.mainFallbackConfirm,
              detail: detail.join('\n\n'),
              buttons: [text.mainFallbackContinue, text.mainFallbackDesktopOnly, text.cancel],
              defaultId: 2,
              cancelId: 2,
              noLink: true,
            })
            if (response === 0) return 'split'
            return response === 1 ? 'desktop' : 'cancel'
          } finally {
            if (!hidden) service.changeWindow('visible')
          }
        },
      }
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
    if (command === 'show' || command === 'hide') {
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
  ipcMain.handle('desktop-session:export-logs', async event => {
    const window = preview
    const folder = service.logFolder
    if (!fromPreview(event) || !window || !folder) return false
    const operation = beginMainFeature('diagnostic_export_finished')
    let outcome: 'success' | 'failure' | 'cancelled' = 'failure'
    try {
      const { canceled, filePath } = await dialog.showSaveDialog(window, {
        title: labels().exportLogs,
        defaultPath: 'auto-mas-desktop-session-logs.zip',
        filters: [{ name: 'ZIP', extensions: ['zip'] }],
      })
      if (canceled || !filePath) {
        outcome = 'cancelled'
        return false
      }
      const zip = new AdmZip()
      const files = (await readdir(folder, { withFileTypes: true })).filter(
        file => file.isFile() && /^(host|control)\.log(\.[1-4])?$/.test(file.name)
      )
      for (const file of files) zip.addFile(file.name, await readFile(join(folder, file.name)))
      await zip.writeZipPromise(filePath)
      outcome = 'success'
      return true
    } finally {
      operation.finish({ outcome, bundle_kind: 'logs', script_type: 'none', incomplete: 'unknown' })
    }
  })

  return {
    get active() {
      return preview !== null || service.active
    },
    closeForAppQuit: confirmClose,
  }
}
