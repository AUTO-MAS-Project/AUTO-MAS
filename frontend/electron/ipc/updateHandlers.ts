import { app, BrowserWindow, ipcMain } from 'electron'

import { getAppRoot } from '../services/environmentService'
import { AppUpdateService } from '../services/appUpdateService'
import { getLogger } from '../services/logger'

const logger = getLogger('更新处理器')

let appUpdateService: AppUpdateService | null = null

function getAppUpdateService(): AppUpdateService {
    if (!appUpdateService) {
        appUpdateService = new AppUpdateService(getAppRoot())
    }
    return appUpdateService
}

export function registerUpdateHandlers(mainWindow: BrowserWindow) {
    ipcMain.handle('app-update:check', async (_event, currentVersion: string, ifForce: boolean = false) => {
        const service = getAppUpdateService()
        return await service.checkUpdate(currentVersion, ifForce)
    })

    ipcMain.handle('app-update:download', async (event, targetVersion: string) => {
        const service = getAppUpdateService()

        const result = await service.downloadUpdate(targetVersion, progress => {
            event.sender.send('app-update:event', {
                id: 'Update',
                type: 'Update',
                data: {
                    downloaded_size: progress.downloadedSize,
                    file_size: progress.totalSize,
                    speed: progress.speed,
                },
            })
        })

        if (result.code === 200) {
            event.sender.send('app-update:event', {
                id: 'Update',
                type: 'Signal',
                data: {
                    Accomplish: String(result.data?.path || ''),
                },
            })
        } else {
            event.sender.send('app-update:event', {
                id: 'Update',
                type: 'Signal',
                data: {
                    Failed: result.message,
                },
            })
        }

        return result
    })

    ipcMain.handle('app-update:install', async event => {
        const service = getAppUpdateService()
        const result = await service.installUpdate()

        if (result.code !== 200) {
            event.sender.send('app-update:event', {
                id: 'Update',
                type: 'Info',
                data: {
                    Error: result.message,
                },
            })
            return result
        }

        event.sender.send('app-update:event', {
            id: 'Update',
            type: 'Info',
            data: {
                Message: result.message,
            },
        })

        setTimeout(() => {
            if (!mainWindow.isDestroyed()) {
                mainWindow.hide()
            }
            app.quit()
        }, 200)

        return result
    })

    ipcMain.handle('app-update:status', async () => {
        const service = getAppUpdateService()
        return service.getStatus()
    })

    ipcMain.handle('app-update:cancel', async () => {
        logger.warn('当前版本暂未实现下载取消，返回固定提示')
        return {
            code: 501,
            status: 'error',
            message: '当前版本暂不支持取消下载',
        }
    })

    logger.info('应用更新处理器已注册')
}

export async function cleanupUpdateResources() {
    appUpdateService = null
    logger.info('应用更新资源已清理')
}
