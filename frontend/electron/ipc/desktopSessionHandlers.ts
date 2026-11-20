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
  'emulator-only': ['acknowledge'],
  takeover: ['takeover', 'cancel'],
  close: ['logoff', 'cancel'],
  'close-adopted': ['disconnect', 'logoff', 'cancel'],
  'close-failed': ['acknowledge'],
}

interface PendingPrompt {
  data: DesktopSessionPrompt
  finish: (action: DesktopSessionPromptAction) => void
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

  const service = new DesktopSessionService(
    snapshot => {
      if (preview && !preview.isDestroyed())
        preview.webContents.send('desktop-session:state', snapshot)
    },
    action => {
      if (action === 'close') void confirmClose(true)
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

  function promptOwner(event: IpcMainInvokeEvent): BrowserWindow | null {
    const main = getMainWindow()
    if (isApplicationWindowSender(event, main, { allowDevelopment: true })) return main
    return fromPreview(event) ? preview : null
  }

  function showPrompt(
    window: BrowserWindow | null,
    content: DesktopSessionPromptContent
  ): Promise<DesktopSessionPromptAction> {
    if (!window || window.isDestroyed() || prompts.has(window)) return Promise.resolve('cancel')

    return new Promise(resolve => {
      const contents = window.webContents
      const cancel = () => finish('cancel')
      const finish = (action: DesktopSessionPromptAction) => {
        prompts.delete(window)
        window.removeListener('closed', cancel)
        contents.removeListener('render-process-gone', cancel)
        resolve(action)
      }

      prompts.set(window, { data: { ...content, id: ++promptId }, finish })
      window.once('closed', cancel)
      contents.once('render-process-gone', cancel)
      contents.send('desktop-session:prompt')
    })
  }

  async function showPreviewPrompt(
    window: BrowserWindow,
    content: DesktopSessionPromptContent
  ): Promise<DesktopSessionPromptAction> {
    const conceal = service.snapshot.state === 'connected' && !hidden
    if (conceal) service.changeWindow('hidden')
    try {
      return await showPrompt(window, content)
    } finally {
      if (conceal && !hidden && !window.isDestroyed() && !window.isMinimized()) {
        service.changeWindow('visible')
      }
    }
  }

  function emulatorPrompt(targets: DesktopQueueResult[]): DesktopSessionPromptContent {
    return { kind: 'emulator-only', main: targets.map(promptTarget) }
  }

  ipcMain.handle('desktop-session:prompt:get', event => {
    const owner = promptOwner(event)
    return owner ? (prompts.get(owner)?.data ?? null) : null
  })
  ipcMain.handle('desktop-session:prompt:respond', (event, id: unknown, action: unknown) => {
    const owner = promptOwner(event)
    const prompt = owner && prompts.get(owner)
    if (!prompt || prompt.data.id !== id) return
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

  function confirmClose(manual: boolean): Promise<boolean> {
    if (closeFlight) return closeFlight
    closeFlight = (async () => {
      const window = preview
      // 关闭窗口也能取消等待中的分发或接管，避免互相等待。
      if (window) prompts.get(window)?.finish('cancel')
      await service.waitForStart()
      const owner = window && !window.isDestroyed() ? window : getMainWindow()
      let logoff: boolean | undefined
      try {
        const kind = await service.getClosePrompt(manual)
        if (kind) {
          if (owner && !owner.isDestroyed()) {
            if (owner.isMinimized()) owner.restore()
            if (!owner.isVisible()) owner.show()
            owner.focus()
          }
          service.changeWindow('hidden')
          const action = await showPrompt(owner, { kind })
          if (action !== 'disconnect' && action !== 'logoff') {
            await service.resumeAdmissions()
            if (!hidden) service.changeWindow('visible')
            return false
          }
          logoff = action === 'logoff'
        }
        await service.close({ logoff })
      } catch {
        await service.resumeAdmissions().catch(() => undefined)
        if (!hidden) service.changeWindow('visible')
        if (owner && owner === window) await showPreviewPrompt(owner, { kind: 'close-failed' })
        else await showPrompt(owner, { kind: 'close-failed' })
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
      void confirmClose(true)
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

  ipcMain.handle('desktop-session:supported', event =>
    isApplicationWindowSender(event, getMainWindow(), { allowDevelopment: true }) &&
    supportsDesktopSession()
      ? service.availability()
      : 'unsupported'
  )
  ipcMain.handle('desktop-session:open', async (event, input: unknown) => {
    const main = getMainWindow()
    if (!isApplicationWindowSender(event, main, { allowDevelopment: true })) {
      throw new Error('entry_unavailable')
    }
    if (!supportsDesktopSession()) {
      throw new Error('unsupported_environment')
    }
    const request = normalizeRequest(input)
    if (!request) throw new Error('invalid_selection')
    const availability = await service.availability()
    if (availability !== 'ready') throw new Error(availability)
    if (request.queueIds.length) {
      const targets = await service.previewQueues(request.queueIds)
      const emulator = targets.filter(target => target.code === 'emulator_required')
      if (emulator.length && !targets.some(target => !target.code)) {
        await showPrompt(main, emulatorPrompt(emulator))
        return
      }
    }
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
          !closeFlight && (await showPreviewPrompt(window, { kind: 'takeover' })) === 'takeover',
        notifyEmulatorOnly: async targets => {
          if (!closeFlight) await showPreviewPrompt(window, emulatorPrompt(targets))
        },
        confirmTaskDispatch: async ({ desktop, main }) => {
          if (closeFlight) return 'cancel'
          const action = await showPreviewPrompt(window, {
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
    closeForAppQuit: () => confirmClose(false),
  }
}
