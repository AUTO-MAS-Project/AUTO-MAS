import { app, BrowserWindow, ipcMain } from 'electron'
import type { DesktopMascotService } from '../services/desktopMascotService'
import type {
  DesktopMascotColors,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
} from '../../src/types/desktopMascot'
import * as fs from 'fs'
import * as path from 'path'
import type { MascotSummary } from '../../src/types/mascotPack'
import { getAppRoot } from '../services/environmentService'
import { getLogger } from '../services/logger'
import { importMascotPackage, listMascots, removeMascot } from '../services/mascotPackageService'
import { patchConfigFile } from '../utils/configFile'
import { removeAppearanceSource } from '../services/onlineAppearanceService'

const logger = getLogger('桌宠包')
let registered = false

function forgetSource(id: string): void {
  try {
    removeAppearanceSource(app.getPath('userData'), id, logger, 'mascot')
  } catch (error) {
    logger.warn('清理桌宠来源记录失败:', error)
  }
}

export function broadcastMascotChange(): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) window.webContents.send('mascot-changed')
  }
}

const summary = (mascot: MascotSummary): MascotSummary => ({
  id: mascot.id,
  name: mascot.name,
  ...(mascot.description ? { description: mascot.description } : {}),
  ...(mascot.previewUrl ? { previewUrl: mascot.previewUrl } : {}),
})

export function registerMascotHandlers(onChanged: () => void): void {
  if (registered) return
  registered = true
  const notify = (): void => {
    onChanged()
    broadcastMascotChange()
  }
  ipcMain.handle('mascot:list', () => listMascots(app.getPath('userData')))
  ipcMain.handle('mascot:import', (_event, zipPath: unknown, replace: unknown = false) => {
    if (typeof zipPath !== 'string' || !zipPath.toLowerCase().endsWith('.zip')) {
      return { success: false, code: 'INVALID_PACKAGE', error: '请选择 ZIP 桌宠包' }
    }
    const { mascot, existing, ...result } = importMascotPackage(
      app.getPath('userData'),
      path.resolve(zipPath),
      replace === true
    )
    if (result.success) {
      logger.info(`桌宠已导入: ${mascot?.id}`)
      if (mascot) forgetSource(mascot.id)
      notify()
    } else {
      logger.warn(`桌宠导入失败: ${result.error}`)
    }
    return {
      ...result,
      ...(mascot ? { mascot: summary(mascot) } : {}),
      ...(existing ? { existing: summary(existing) } : {}),
    }
  })
  ipcMain.handle('mascot:remove', (_event, id: unknown) => {
    if (typeof id !== 'string') return { success: false, error: '桌宠 ID 无效' }
    const result = removeMascot(app.getPath('userData'), id)
    if (result.success) {
      logger.info(`桌宠已移除: ${id}`)
      forgetSource(id)
      try {
        const configPath = path.join(getAppRoot(), 'config', 'frontend_config.json')
        const config = fs.existsSync(configPath)
          ? JSON.parse(fs.readFileSync(configPath, 'utf8'))
          : {}
        if (config.desktopMascotId === id) patchConfigFile(configPath, { desktopMascotId: null })
      } catch (error) {
        logger.warn('清理已移除桌宠的选择失败:', error)
      }
      notify()
    }
    return result
  })
}

/** 运行时 IPC 与资源包 IPC 分开释放，应用共享的安装器不随主窗口重建。 */
export function registerDesktopMascotHandlers(
  service: Pick<
    DesktopMascotService,
    | 'setReady'
    | 'getData'
    | 'setIdleMessage'
    | 'handlePointer'
    | 'startDrag'
    | 'setDecodedImage'
    | 'setActivity'
    | 'showNotice'
  >,
  getMainWindow: () => BrowserWindow | null
): () => void {
  ipcMain.handle(
    'desktop-mascot:ready',
    (event, ready: unknown, labels?: DesktopMascotMenuLabels, colors?: DesktopMascotColors) => {
      if (event.sender !== getMainWindow()?.webContents || typeof ready !== 'boolean') return
      if (
        ready &&
        (!colors ||
          typeof colors.background !== 'string' ||
          typeof colors.text !== 'string' ||
          typeof colors.border !== 'string' ||
          !Number.isFinite(colors.radius))
      )
        return
      service.setReady(
        ready,
        labels &&
          typeof labels.pauseAnimation === 'string' &&
          typeof labels.resumeAnimation === 'string' &&
          typeof labels.pauseIdleMessage === 'string' &&
          typeof labels.resumeIdleMessage === 'string'
          ? labels
          : undefined,
        colors
      )
    }
  )
  ipcMain.handle('desktop-mascot:get', event => service.getData(event.sender))
  ipcMain.handle('desktop-mascot:drag-start', (event, offset: unknown) =>
    service.startDrag(event.sender, offset)
  )
  ipcMain.handle('desktop-mascot:idle-message', (event, message?: DesktopMascotIdleMessage) => {
    if (
      event.sender !== getMainWindow()?.webContents ||
      !message ||
      typeof message.text !== 'string' ||
      typeof message.author !== 'string'
    )
      return
    service.setIdleMessage(message)
  })
  const onPointer = (event: Electron.IpcMainEvent, action: unknown, session: unknown): void =>
    service.handlePointer(event.sender, action, session)
  ipcMain.on('desktop-mascot:pointer', onPointer)
  const onImageDecoded = (
    event: Electron.IpcMainEvent,
    imageUrl: unknown,
    pngDataUrl: unknown
  ): void => {
    if (
      typeof imageUrl !== 'string' ||
      typeof pngDataUrl !== 'string' ||
      !pngDataUrl.startsWith('data:image/png;base64,')
    )
      return
    service.setDecodedImage(event.sender, imageUrl, pngDataUrl)
  }
  ipcMain.on('desktop-mascot:image-decoded', onImageDecoded)
  ipcMain.handle('desktop-mascot:activity', (event, working: unknown, animate: unknown) => {
    if (
      event.sender !== getMainWindow()?.webContents ||
      typeof working !== 'boolean' ||
      typeof animate !== 'boolean'
    )
      return
    service.setActivity(working, animate)
  })
  ipcMain.handle('desktop-mascot:notice', (event, text: unknown, reaction: unknown) => {
    if (event.sender !== getMainWindow()?.webContents || typeof text !== 'string') return
    service.showNotice(
      text,
      reaction === 'success' || reaction === 'failure' || reaction === 'stopped'
        ? reaction
        : undefined
    )
  })

  return () => {
    for (const channel of [
      'desktop-mascot:ready',
      'desktop-mascot:get',
      'desktop-mascot:drag-start',
      'desktop-mascot:idle-message',
      'desktop-mascot:activity',
      'desktop-mascot:notice',
    ])
      ipcMain.removeHandler(channel)
    ipcMain.removeListener('desktop-mascot:pointer', onPointer)
    ipcMain.removeListener('desktop-mascot:image-decoded', onImageDecoded)
  }
}
