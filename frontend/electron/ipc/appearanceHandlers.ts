import { app, BrowserWindow, ipcMain, net } from 'electron'
import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import {
  AppearanceError,
  getAppearance,
  importAppearancePackage,
  inspectAppearancePackage,
  isAppearanceGone,
  listAppearances,
  removeAppearance,
} from '../services/appearanceService'
import { getLogger } from '../services/logger'
import { getAppRoot } from '../services/environmentService'
import { createNetRequestFetch } from '../services/onlineAppearanceFetch'
import {
  createOnlineAppearanceService,
  imageMimeFromMagic,
  ONLINE_APPEARANCE_DEFAULTS,
  removeAppearanceSource,
  type OnlineAppearanceServiceOptions,
} from '../services/onlineAppearanceService'
import { clearAppearanceConfigIfCurrent } from '../utils/configFile'

const logger = getLogger('外观包')
let isRegistered = false

const INVALID_ARGUMENT = { success: false, error: '参数无效' } as const

export interface AppearanceHandlerOptions {
  /** 仅供测试替换分享站地址、fetch 实现与目录。 */
  online?: Partial<OnlineAppearanceServiceOptions>
}

/** 外观不再是分享站那份（本地导入覆盖或被移除）时删掉来源记录。 */
function forgetAppearanceSource(id: string): void {
  try {
    if (removeAppearanceSource(userDataPath(), id, logger)) {
      logger.info(`已清除外观来源记录: ${id}`)
    }
  } catch (error) {
    logger.warn(
      `清除外观来源记录失败: ${id}，${error instanceof Error ? error.message : String(error)}`
    )
  }
}

function userDataPath(): string {
  return app.getPath('userData')
}

// 开发版和正式版的 userData 不同、可以同时运行，却共用系统临时目录；按 userData 分子目录，
// 免得一个实例启动清理时删掉另一个实例刚下好的临时包。
function onlineCacheDir(): string {
  const instance = crypto.createHash('sha256').update(userDataPath()).digest('hex').slice(0, 12)
  return path.join(app.getPath('temp'), 'auto-mas-online-appearance', instance)
}

function broadcastAppearanceChange(): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) window.webContents.send('appearance-changed')
  }
}

function clearInvalidAppearance(id: string) {
  const configPath = path.join(getAppRoot(), 'config', 'frontend_config.json')
  const result = clearAppearanceConfigIfCurrent(configPath, id, () =>
    isAppearanceGone(userDataPath(), id)
  )
  if (result.cleared) {
    for (const window of BrowserWindow.getAllWindows()) {
      if (!window.isDestroyed()) {
        window.webContents.send('theme-config-changed', {
          themeMode: result.config.themeMode,
          themeColor: result.config.themeColor,
          appearanceId: null,
        })
      }
    }
  }
  return {
    success: true,
    cleared: result.cleared,
    appearanceId:
      typeof result.config.appearanceId === 'string' ? result.config.appearanceId : null,
  }
}

/** 注册自定义外观包的受限 IPC；素材始终由主进程校验并转换为 data URL。 */
export function registerAppearanceHandlers(options: AppearanceHandlerOptions = {}): void {
  if (isRegistered) return
  isRegistered = true

  const online = createOnlineAppearanceService({
    fetch: createNetRequestFetch(net),
    userDataPath,
    cacheDir: onlineCacheDir,
    logger,
    ...options.online,
  })
  // 上次运行留下的临时包在内存里已没有 token，启动时一并清掉。
  online.clearCacheDirectory()

  ipcMain.handle('appearance:list', () => listAppearances(userDataPath()))

  ipcMain.handle('appearance:get', (_event, id: unknown) => {
    if (typeof id !== 'string') return null
    return getAppearance(userDataPath(), id)
  })

  ipcMain.handle('appearance:clear-invalid', (_event, expectedId: unknown) => {
    if (typeof expectedId !== 'string' || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(expectedId)) {
      return { success: false, error: '外观 ID 无效' }
    }
    try {
      return clearInvalidAppearance(expectedId)
    } catch (error) {
      logger.warn(`清理失效外观配置失败: ${error instanceof Error ? error.message : String(error)}`)
      return { success: false, error: '清理失效外观配置失败' }
    }
  })

  ipcMain.handle('appearance:import', (_event, zipPath: unknown, replace = false) => {
    if (typeof zipPath !== 'string' || !zipPath.toLowerCase().endsWith('.zip')) {
      return { success: false, code: 'INVALID_PACKAGE', error: '请选择 ZIP 外观包' }
    }
    const resolved = path.resolve(zipPath)
    try {
      const stat = fs.statSync(resolved)
      if (!stat.isFile())
        return { success: false, code: 'INVALID_PACKAGE', error: '选择的路径不是文件' }
    } catch {
      return { success: false, code: 'INVALID_PACKAGE', error: '外观 ZIP 不存在' }
    }
    const result = importAppearancePackage(userDataPath(), resolved, replace === true)
    if (result.success) {
      logger.info(`外观包已导入: ${result.appearance?.id ?? 'unknown'}`)
      if (result.appearance) forgetAppearanceSource(result.appearance.id)
      broadcastAppearanceChange()
    } else {
      logger.warn(`外观包导入失败: ${result.error ?? result.code ?? 'unknown'}`)
    }
    return result
  })

  ipcMain.handle('appearance:remove', (_event, id: unknown) => {
    if (typeof id !== 'string') return { success: false, error: '外观 ID 无效' }
    const result = removeAppearance(userDataPath(), id)
    if (result.success) {
      logger.info(`外观包已移除: ${id}`)
      forgetAppearanceSource(id)
      try {
        clearInvalidAppearance(id)
      } catch (error) {
        logger.warn(
          `清理已移除外观配置失败: ${error instanceof Error ? error.message : String(error)}`
        )
      }
      broadcastAppearanceChange()
    } else {
      logger.warn(`外观包移除失败: ${id}，${result.error ?? '未知错误'}`)
    }
    return result
  })

  // ==================== 在线外观（分享站） ====================
  // 渲染进程只能传查询条件、file_key、版本号和 token；URL、路径、哈希一律由主进程决定。

  ipcMain.handle('appearance:online-list', (_event, query: unknown) => {
    if (query === undefined || query === null) return online.list({})
    if (typeof query !== 'object' || Array.isArray(query)) return INVALID_ARGUMENT
    return online.list(query)
  })

  ipcMain.handle('appearance:online-detail', (_event, fileKey: unknown) => {
    if (typeof fileKey !== 'string') return INVALID_ARGUMENT
    return online.detail(fileKey)
  })

  ipcMain.handle('appearance:online-prepare', (_event, fileKey: unknown, versionNo: unknown) => {
    if (typeof fileKey !== 'string' || typeof versionNo !== 'number') return INVALID_ARGUMENT
    return online.prepare(fileKey, versionNo)
  })

  ipcMain.handle(
    'appearance:online-install',
    (_event, token: unknown, replace: unknown = false) => {
      if (typeof token !== 'string' || typeof replace !== 'boolean') return INVALID_ARGUMENT
      try {
        const result = online.install(token, replace)
        if (result.success) broadcastAppearanceChange()
        return result
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        logger.warn(`在线外观安装出错: ${message}`)
        return { success: false, code: 'IMPORT_FAILED', error: `安装外观时出错：${message}` }
      }
    }
  )

  ipcMain.handle('appearance:online-discard', (_event, token: unknown) => {
    if (typeof token !== 'string') return { success: false }
    return online.discard(token)
  })

  ipcMain.handle('appearance:online-cover', (_event, fileKey: unknown, versionNo: unknown) => {
    if (typeof fileKey !== 'string') return INVALID_ARGUMENT
    if (versionNo !== undefined && versionNo !== null && typeof versionNo !== 'number') {
      return INVALID_ARGUMENT
    }
    return online.cover(fileKey, versionNo ?? undefined)
  })

  // ==================== 上传前预览 ====================
  // 与导入同一套只读校验，不写任何目录；上传对话框据此显示外观摘要。

  ipcMain.handle('appearance:inspect-local', (_event, zipPath: unknown) => {
    if (typeof zipPath !== 'string' || !zipPath.toLowerCase().endsWith('.zip')) {
      return { success: false, code: 'INVALID_PACKAGE', error: '请选择 ZIP 外观包' }
    }
    const resolved = path.resolve(zipPath)
    try {
      const { manifest, previewUrl } = inspectAppearancePackage(resolved)
      const tokens = Object.fromEntries(
        Object.entries(manifest.tokens).filter(([, value]) => value !== undefined)
      )
      return {
        success: true,
        fileSize: fs.statSync(resolved).size,
        appearance: {
          id: manifest.id,
          name: manifest.name,
          ...(manifest.description === undefined ? {} : { description: manifest.description }),
          mode: manifest.mode,
          tokens,
          ...(previewUrl ? { previewUrl } : {}),
        },
      }
    } catch (error) {
      if (error instanceof AppearanceError) {
        return { success: false, code: 'INVALID_PACKAGE', error: error.message }
      }
      const code = (error as NodeJS.ErrnoException | undefined)?.code
      if (code === 'ENOENT') {
        return { success: false, code: 'INVALID_PACKAGE', error: '外观 ZIP 不存在' }
      }
      const message = error instanceof Error ? error.message : String(error)
      logger.warn(`读取本地外观包失败: ${message}`)
      return { success: false, code: 'INVALID_PACKAGE', error: `无法读取外观包：${message}` }
    }
  })

  // 上传对话框里预览另选的封面：只读、限 2 MiB、按文件头认 PNG / JPEG / WebP，与后端上传时的检查一致。
  ipcMain.handle('appearance:inspect-cover', (_event, imagePath: unknown) => {
    if (typeof imagePath !== 'string' || imagePath.length === 0) {
      return { success: false, error: '请选择封面图片' }
    }
    try {
      const resolved = path.resolve(imagePath)
      const stat = fs.statSync(resolved)
      if (!stat.isFile()) return { success: false, error: '选择的路径不是文件' }
      if (stat.size > ONLINE_APPEARANCE_DEFAULTS.coverBytes) {
        return { success: false, error: '封面图片不能超过 2 MB' }
      }
      const data = fs.readFileSync(resolved)
      const mime = imageMimeFromMagic(data)
      if (!mime) return { success: false, error: '封面只支持 PNG、JPEG 或 WebP 图片' }
      return { success: true, dataUrl: `data:${mime};base64,${data.toString('base64')}` }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      logger.warn(`读取封面图片失败: ${message}`)
      return { success: false, error: `无法读取封面图片：${message}` }
    }
  })
}
