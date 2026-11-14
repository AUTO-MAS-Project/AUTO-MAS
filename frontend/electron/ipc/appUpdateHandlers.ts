import { ipcMain, type BrowserWindow } from 'electron'
import { isApplicationWindowSender } from './analyticsHandlers'
import { AppUpdateService, checkAppUpdate } from '../services/appUpdateService'
import type { BackendService } from '../services/backendService'
import type { AppUpdateSettings } from '../services/appUpdateTypes'

export function registerAppUpdateHandlers(options: {
  root: string
  window: () => BrowserWindow | null
  backendUrl: () => string
  backend: () => BackendService
  ownsBackend: () => boolean
  quit: () => void
}): void {
  // 注册应用更新 IPC，绑定主窗口、后端归属与更新服务，并限制请求必须来自应用页面。
  const service = new AppUpdateService(options.root, options.backendUrl, event => {
    // 把更新服务事件发送给仍存活的主窗口，供渲染进程刷新下载和安装状态。
    const window = options.window()
    if (window && !window.isDestroyed()) window.webContents.send('app-update:event', event)
  })
  const register = <T extends unknown[]>(name: string, action: (...args: T) => unknown) =>
    /* 为更新操作创建统一的 IPC 注册入口，在调用业务前校验消息发送方。 */ ipcMain.handle(
      name,
      (event, ...args: unknown[]) => {
        // 确认请求来自允许的应用窗口，再把原始参数交给对应更新动作。
        if (!isApplicationWindowSender(event, options.window(), { allowDevelopment: true }))
          throw new Error('不允许此页面执行更新操作')
        return action(...(args as T))
      }
    )
  const owned = () => {
    // 确认本应用拥有后端进程，防止连接外部后端时执行需要停止后端的更新。
    if (!options.ownsBackend()) throw new Error('当前只连接外部后端，请在所属应用中更新')
  }
  register('app-update:check', (input: AppUpdateSettings) =>
    /* 按当前版本和更新设置查询应用可用版本及更新日志。 */ checkAppUpdate(input)
  )
  register(
    'app-update:status',
    () => /* 返回更新服务当前状态的副本，供页面首次打开或重连时恢复显示。 */ ({
      ...service.snapshot,
    })
  )
  register(
    'app-update:start',
    async (version: string, input: AppUpdateSettings, downloader?: 'builtin' | 'fluxdown') => {
      // 确认后端归属后启动指定版本下载，完成后返回统一成功响应。
      owned()
      await service.start(version, input, downloader)
      return { code: 200 }
    }
  )
  register('app-update:cancel', async () => {
    // 等待当前更新下载取消收尾，再返回操作结果。
    await service.cancel()
    return { code: 200 }
  })
  register('app-update:switch', async () => {
    // 确认后端归属后取消原下载并切换到 CNB 来源重新下载。
    owned()
    await service.switchToCnb()
    return { code: 200 }
  })
  register('app-update:install', async () => {
    // 确认后端归属后执行已准备更新包的安装，并退出当前应用。
    owned()
    await service.install(options.backend())
    options.quit()
    return { code: 200 }
  })
}
