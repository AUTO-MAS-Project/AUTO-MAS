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
  type DesktopQueueResult,
  type DesktopSessionPrompt,
  type DesktopSessionPromptAction,
  type DesktopSessionPromptContent,
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

function promptTarget({ label, targetKind }: DesktopQueueResult) {
  return { label, targetKind }
}

const promptActions: Record<DesktopSessionPrompt['kind'], readonly DesktopSessionPromptAction[]> = {
  dispatch: ['split', 'desktop', 'cancel'],
  takeover: ['takeover', 'cancel'],
  close: ['logoff', 'cancel'],
  'close-adopted': ['disconnect', 'logoff', 'cancel'],
  'close-failed': ['acknowledge'],
}

interface PendingPrompt {
  data: DesktopSessionPrompt
  ready: boolean
  finish: (action: DesktopSessionPromptAction | null) => void
}

function hasRenderer(window: BrowserWindow | null): window is BrowserWindow {
  return (
    !!window &&
    !window.isDestroyed() &&
    !window.webContents.isDestroyed() &&
    !window.webContents.isCrashed()
  )
}

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
  let promptId = 0
  const prompts = new Map<BrowserWindow, PendingPrompt>()
  const unresponsive = new WeakSet<BrowserWindow>()

  const service = new DesktopSessionService(
    snapshot => {
      if (hasRenderer(preview)) preview.webContents.send('desktop-session:state', snapshot)
    },
    action => {
      if (action === 'close') void confirmClose()
      else preview?.minimize()
    },
    tasks => {
      const main = getMainWindow()
      if (hasRenderer(main)) main.webContents.send('desktop-session:tasks-started', tasks)
    }
  )

  function fromPreview(event: IpcMainInvokeEvent): boolean {
    return (
      isApplicationWindowSender(event, preview, { allowDevelopment: true }) &&
      new URL(event.senderFrame!.url).hash === '#/desktop-session'
    )
  }

  function promptOwner(event: IpcMainInvokeEvent): BrowserWindow | null {
    const main = getMainWindow()
    if (isApplicationWindowSender(event, main, { allowDevelopment: true })) return main
    return fromPreview(event) ? preview : null
  }

  function showPrompt(
    window: BrowserWindow | null,
    content: DesktopSessionPromptContent
  ): Promise<DesktopSessionPromptAction | null> {
    if (!hasRenderer(window) || unresponsive.has(window)) return Promise.resolve(null)
    if (prompts.has(window)) return Promise.resolve('cancel')

    return new Promise(resolve => {
      const contents = window.webContents
      const cancel = () => finish('cancel')
      const fallback = () => finish(null)
      const finish = (action: DesktopSessionPromptAction | null) => {
        prompts.delete(window)
        window.removeListener('closed', cancel)
        window.removeListener('unresponsive', fallback)
        contents.removeListener('render-process-gone', fallback)
        resolve(action)
        updateWindowState()
      }

      const prompt = { data: { ...content, id: ++promptId }, ready: false, finish }
      prompts.set(window, prompt)
      window.once('closed', cancel)
      window.once('unresponsive', fallback)
      contents.once('render-process-gone', fallback)
      const present = async () => {
        const parked = window !== preview || (await service.parkForPrompt(prompt.data.id))
        if (prompts.get(window) !== prompt) return
        if (!parked) {
          finish(null)
          return
        }
        try {
          prompt.ready = true
          contents.send('desktop-session:prompt')
        } catch {
          finish(null)
        }
      }
      void present()
    })
  }

  ipcMain.handle('desktop-session:prompt:get', event => {
    const owner = promptOwner(event)
    const prompt = owner && prompts.get(owner)
    return prompt?.ready ? prompt.data : null
  })
  ipcMain.handle('desktop-session:prompt:respond', (event, id: unknown, action: unknown) => {
    const owner = promptOwner(event)
    const prompt = owner && prompts.get(owner)
    if (!prompt?.ready || prompt.data.id !== id) return
    const allowed = promptActions[prompt.data.kind].find(candidate => candidate === action)
    if (allowed) prompt.finish(allowed)
  })

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

  function updateWindowState() {
    if (!preview || preview.isDestroyed()) return
    // ActiveX 画面在 Web 内容上方，弹窗期间始终移出预览区域。
    if (closeFlight || prompts.has(preview) || hidden) service.changeWindow('hidden')
    else service.changeWindow(preview.isMinimized() ? 'minimized' : 'visible')
  }

  function showNativePrompt(window: BrowserWindow | null, options: MessageBoxOptions) {
    return window && !window.isDestroyed()
      ? dialog.showMessageBox(window, options)
      : dialog.showMessageBox(options)
  }

  async function askToClose(owner: BrowserWindow | null): Promise<DesktopSessionPromptAction> {
    const adopted = service.adopted
    const action = await showPrompt(owner, { kind: adopted ? 'close-adopted' : 'close' })
    if (action !== null) return action
    const text = labels()
    const { response } = await showNativePrompt(owner, {
      type: 'warning',
      title: text.closeTitle,
      message: adopted ? text.adoptedCloseConfirm : text.closeConfirm,
      buttons: adopted
        ? [text.disconnectOnly, text.logoffDesktopSession, text.cancel]
        : [text.closeContinue, text.cancel],
      defaultId: adopted ? 0 : 1,
      cancelId: adopted ? 2 : 1,
      noLink: true,
    })
    if (response === 0) return adopted ? 'disconnect' : 'logoff'
    return adopted && response === 1 ? 'logoff' : 'cancel'
  }

  function confirmClose(): Promise<boolean> {
    if (closeFlight) return closeFlight
    const window = preview
    closeFlight = (async () => {
      const owner = window && !window.isDestroyed() ? window : getMainWindow()
      try {
        await service.waitForStart()
        let logoff = false
        if (service.active) {
          if (owner && !owner.isDestroyed()) {
            if (owner.isMinimized()) owner.restore()
            if (!owner.isVisible()) owner.show()
            owner.focus()
          }
          const action = await askToClose(owner)
          if (action !== 'disconnect' && action !== 'logoff') return false
          logoff = action === 'logoff'
        }
        await service.close({ logoff })
      } catch {
        if ((await showPrompt(owner, { kind: 'close-failed' })) === null) {
          const text = labels()
          await showNativePrompt(owner, {
            type: 'error',
            title: text.closeFailedTitle,
            message: text.closeFailed,
          })
        }
        return false
      }
      if (window && !window.isDestroyed()) window.destroy()
      return true
    })().finally(() => {
      closeFlight = null
      updateWindowState()
    })
    if (window) prompts.get(window)?.finish('cancel')
    updateWindowState()
    return closeFlight
  }

  function showPreview() {
    if (preview && !preview.isDestroyed()) {
      if (preview.isMinimized()) preview.restore()
      preview.show()
      preview.focus()
      if (pending.length && hasRenderer(preview))
        preview.webContents.send('desktop-session:pending')
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
    window.on('unresponsive', () => unresponsive.add(window))
    window.on('responsive', () => {
      unresponsive.delete(window)
      if (hasRenderer(window)) window.webContents.send('desktop-session:prompt')
    })
    window.on('move', updateBounds)
    window.on('resize', updateBounds)
    window.on('minimize', updateWindowState)
    window.on('restore', () => {
      updateBounds()
      updateWindowState()
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
        confirmTakeover: async () =>
          !closeFlight && (await showPrompt(window, { kind: 'takeover' })) === 'takeover',
        confirmTaskDispatch: async ({ desktop, main }) => {
          if (closeFlight) return 'cancel'
          const action = await showPrompt(window, {
            kind: 'dispatch',
            desktop: desktop.map(promptTarget),
            main: main.map(promptTarget),
          })
          return action === 'split' || action === 'desktop' ? action : 'cancel'
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
      updateWindowState()
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
