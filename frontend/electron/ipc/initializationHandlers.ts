/**
 * 初始化相关的 IPC 处理器
 * 使用新的服务
 */

import { ipcMain, BrowserWindow } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import { getAppRoot } from '../services/environmentService'
import {
  InitializationService,
  BackendService,
  type PluginBootstrapProgressCallback,
} from '../services'
import {
  InitializationOperationBusyError,
  InitializationOperationLock,
} from '../services/initializationOperationLock'
import { requiresBundledRuntimeLock } from '../services/bundledRuntimePolicy'
import { getLogger } from '../services/logger'
import { assertAllowedMainFrameSender } from '../services/ipcSenderPolicy'

const logger = getLogger('初始化处理器')

// 全局实例
let initService: InitializationService | null = null
let backendService: BackendService | null = null
const initializationOperationLock = new InitializationOperationLock()

interface InitializationOperationFailure {
  success: false
  error: string
}

export interface InitializationCleanupResult {
  success: boolean
  error?: string
}

let cleanupPromise: Promise<InitializationCleanupResult> | null = null
let runtimeStartupPromise: Promise<RuntimeStartResult> | null = null

interface RuntimeStartResult {
  success: boolean
  error?: string
  logs?: string
  summary?: string
}

export interface BackendPrewarmRequest {
  currentVersion: string
  initializedVersion?: string | null
  autoUpdateEnabled: boolean
}

export function shouldPrewarmBackend(request: BackendPrewarmRequest): boolean {
  return (
    !request.autoUpdateEnabled &&
    Boolean(request.currentVersion) &&
    request.initializedVersion === request.currentVersion
  )
}

async function runInitializationOperation<T>(
  operationName: string,
  operation: () => Promise<T>
): Promise<T | InitializationOperationFailure> {
  try {
    return await initializationOperationLock.runExclusive(operationName, operation)
  } catch (error) {
    if (error instanceof InitializationOperationBusyError) {
      const message = `另一个初始化操作正在执行: ${error.activeOperation}`
      logger.warn(`${operationName} 已拒绝: ${message}`)
      return { success: false, error: message }
    }
    throw error
  }
}

async function prepareRuntimeMutation(): Promise<InitializationOperationFailure | null> {
  const stopResult = await getBackendService().stopBackendForRuntimeMutation()
  if (stopResult.success) {
    return null
  }

  const error = stopResult.error || '无法安全停止当前安装目录的后端，已取消运行时修改'
  logger.error(error)
  return { success: false, error }
}

/**
 * 获取或创建初始化服务实例
 */
function getInitService(targetBranch: string = 'dev'): InitializationService {
  const appRoot = getAppRoot()

  if (!initService) {
    initService = new InitializationService(appRoot, targetBranch)
    if (backendService) {
      initService.setBackendService(backendService)
    }
  } else {
    initService.setTargetBranch(targetBranch)
  }

  return initService
}

/**
 * 获取后端服务实例
 */
export function getBackendService(): BackendService {
  if (!backendService) {
    const appRoot = getAppRoot()
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()
    backendService = new BackendService(appRoot, mirrorService)
    initService.setBackendService(backendService)
  }

  return backendService
}

function hasPrewarmRuntimeFiles(appRoot: string): boolean {
  return [
    path.join(appRoot, 'main.py'),
    path.join(appRoot, 'pyproject.toml'),
    path.join(appRoot, '.venv', 'Scripts', 'python.exe'),
  ].every(candidate => fs.existsSync(candidate))
}

async function ensureRuntimeReadyAndStarted(
  onProgress?: PluginBootstrapProgressCallback,
  selectedMirror?: string
): Promise<RuntimeStartResult> {
  if (runtimeStartupPromise) {
    return await runtimeStartupPromise
  }

  const startupPromise = runInitializationOperation('快速运行时修复', async () => {
    const appRoot = getAppRoot()
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    if (requiresBundledRuntimeLock(appRoot)) {
      mirrorService.initializeLocal()
      logger.info('随包锁定运行时使用本地/默认镜像配置，跳过 MirrorChyan 云端刷新')
    } else {
      await mirrorService.initialize()
    }

    const preparationFailure = await prepareRuntimeMutation()
    if (preparationFailure) {
      return preparationFailure
    }

    const { PluginBootstrapService } = await import('../services/pluginBootstrapService')
    const bootstrapService = new PluginBootstrapService(appRoot, mirrorService)
    const bootstrapResult = await bootstrapService.installPackages(onProgress, selectedMirror)
    if (!bootstrapResult.success) {
      const error = bootstrapResult.error || bootstrapResult.summary
      logger.error(`快速插件修复失败: ${error}`)
      return { success: false, error, summary: bootstrapResult.summary }
    }

    const backend = getBackendService()
    await backend.prewarmBackend()
    const backendResult = await backend.startBackend()
    if (!backendResult.success) {
      logger.error(`快速插件修复后启动后端失败: ${backendResult.error}`)
      return backendResult
    }

    return { success: true, summary: bootstrapResult.summary }
  })
  runtimeStartupPromise = startupPromise

  try {
    return await startupPromise
  } finally {
    if (runtimeStartupPromise === startupPromise) {
      runtimeStartupPromise = null
    }
  }
}

/**
 * 在已初始化的随包运行时中尽早校验插件并预热后端。
 *
 * 同一个 Promise 也供 renderer 的 repair-runtime-and-start IPC 使用，避免
 * 生命周期预热与初始化页重复修复、重复启动或争抢初始化写锁。
 */
export async function prewarmBackend(request: BackendPrewarmRequest): Promise<void> {
  if (!shouldPrewarmBackend(request)) {
    return
  }

  const appRoot = getAppRoot()
  if (!requiresBundledRuntimeLock(appRoot) || !hasPrewarmRuntimeFiles(appRoot)) {
    logger.info('后端预热跳过：当前不是完整且已初始化的随包运行时')
    return
  }

  const result = await ensureRuntimeReadyAndStarted()
  if (!result.success) {
    throw new Error(result.error || result.summary || '后端预热失败')
  }
}

/**
 * 注册所有初始化相关的 IPC 处理器
 */
export function registerInitializationHandlers(_mainWindow: BrowserWindow) {
  // ==================== 镜像源初始化 ====================

  ipcMain.handle('init-mirrors', async () => {
    const appRoot = getAppRoot()
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    try {
      if (requiresBundledRuntimeLock(appRoot)) {
        mirrorService.initializeLocal()
        logger.info('随包锁定运行时使用本地/默认镜像配置，跳过 MirrorChyan 云端刷新')
      } else {
        await mirrorService.initialize()
      }
      logger.info('镜像源初始化成功')
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`镜像源初始化失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  })

  // ==================== Python 安装 ====================

  ipcMain.handle('install-python', async (event, selectedMirror?: string) =>
    runInitializationOperation('Python 安装', async () => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源安装Python: ${selectedMirror}`)
      }
      const appRoot = getAppRoot()
      const initService = getInitService()
      const mirrorService = initService.getMirrorService()

      const { PythonInstaller } = await import('../services/environmentService')
      const installer = new PythonInstaller(appRoot, mirrorService)

      const result = await installer.install(progress => {
        event.sender.send('python-progress', progress)
      }, selectedMirror)

      if (!result.success) {
        logger.error(`Python安装失败: ${result.error}`)
      }

      return result
    })
  )

  // ==================== Pip 安装 ====================

  ipcMain.handle('install-pip', async (event, selectedMirror?: string) =>
    runInitializationOperation('uv 安装', async () => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源安装Pip: ${selectedMirror}`)
      }
      const appRoot = getAppRoot()
      const initService = getInitService()
      const mirrorService = initService.getMirrorService()

      const { PipInstaller } = await import('../services/environmentService')
      const installer = new PipInstaller(appRoot, mirrorService)

      const result = await installer.install(progress => {
        event.sender.send('pip-progress', progress)
      }, selectedMirror)

      if (!result.success) {
        logger.error(`Pip安装失败: ${result.error}`)
      }

      return result
    })
  )

  // ==================== Git 安装 ====================

  ipcMain.handle('install-git', async (event, selectedMirror?: string) =>
    runInitializationOperation('Git 安装', async () => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源安装Git: ${selectedMirror}`)
      }
      const appRoot = getAppRoot()
      const initService = getInitService()
      const mirrorService = initService.getMirrorService()

      const { GitInstaller } = await import('../services/environmentService')
      const installer = new GitInstaller(appRoot, mirrorService)

      const result = await installer.install(progress => {
        event.sender.send('git-progress', progress)
      }, selectedMirror)

      if (!result.success) {
        logger.error(`Git安装失败: ${result.error}`)
      }

      return result
    })
  )

  // ==================== 源码拉取 ====================

  ipcMain.handle(
    'pull-repository',
    async (event, targetBranch: string = 'dev', selectedMirror?: string) =>
      runInitializationOperation('源码更新', async () => {
        if (selectedMirror) {
          logger.info(`使用指定镜像源拉取源码: ${selectedMirror}`)
        }
        const preparationFailure = await prepareRuntimeMutation()
        if (preparationFailure) {
          return preparationFailure
        }

        const appRoot = getAppRoot()
        const initService = getInitService(targetBranch)
        const mirrorService = initService.getMirrorService()

        const { RepositoryService } = await import('../services/repositoryService')
        const repoService = new RepositoryService(appRoot, mirrorService, targetBranch)

        const result = await repoService.pullRepository(progress => {
          event.sender.send('repository-progress', progress)
        }, selectedMirror)

        if (!result.success) {
          logger.error(`源码拉取失败: ${result.error}`)
        }

        return result
      })
  )

  // ==================== 依赖安装 ====================

  ipcMain.handle('install-dependencies', async (event, selectedMirror?: string) =>
    runInitializationOperation('依赖安装', async () => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源安装依赖: ${selectedMirror}`)
      }
      const preparationFailure = await prepareRuntimeMutation()
      if (preparationFailure) {
        return preparationFailure
      }

      const appRoot = getAppRoot()
      const initService = getInitService()
      const mirrorService = initService.getMirrorService()

      const { DependencyService } = await import('../services/dependencyService')
      const depService = new DependencyService(appRoot, mirrorService)

      const result = await depService.installDependencies(progress => {
        event.sender.send('dependency-progress', progress)
      }, selectedMirror)

      if (!result.success) {
        logger.error(`依赖安装失败: ${result.error}`)
      }

      return result
    })
  )

  // ==================== 插件引导安装 ====================

  ipcMain.handle('install-plugin-bootstrap', async (event, selectedMirror?: string) =>
    runInitializationOperation('插件引导安装', async () => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源安装随包插件: ${selectedMirror}`)
      }
      const preparationFailure = await prepareRuntimeMutation()
      if (preparationFailure) {
        return preparationFailure
      }

      const appRoot = getAppRoot()
      const initService = getInitService()
      const mirrorService = initService.getMirrorService()

      const { PluginBootstrapService } = await import('../services/pluginBootstrapService')
      const bootstrapService = new PluginBootstrapService(appRoot, mirrorService)

      const result = await bootstrapService.installPackages(progress => {
        event.sender.send('plugin-bootstrap-progress', progress)
      }, selectedMirror)

      if (!result.success) {
        logger.error(`插件引导安装失败: ${result.error || result.summary}`)
      }

      return result
    })
  )

  // 快速修复必须在同一把锁内完成“停后端 -> 修复插件 -> 重启”，避免步骤间被更新插队。
  ipcMain.handle('repair-runtime-and-start', async (event, selectedMirror?: string) => {
    const backend = getBackendService()
    backend.setStatusCallback(status => {
      event.sender.send('backend-status', status)
    })
    return await ensureRuntimeReadyAndStarted(
      progress => event.sender.send('plugin-bootstrap-progress', progress),
      selectedMirror
    )
  })

  // ==================== 获取镜像源列表 ====================

  ipcMain.handle('get-mirrors', async (event, type: string) => {
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    const mirrors = mirrorService.getMirrors(type as any)
    return mirrors
  })

  // ==================== 获取 API 端点 ====================

  ipcMain.handle('get-api-endpoint', async (event, key: string) => {
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    return mirrorService.getApiEndpoint(key as any)
  })

  ipcMain.handle('get-api-endpoints', async () => {
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    return mirrorService.getApiEndpoints()
  })

  ipcMain.handle('get-backend-auth-token', async event => {
    assertAllowedMainFrameSender(event, [_mainWindow])
    return await getBackendService().getBackendAuthToken()
  })

  // ==================== 完整初始化流程（保留用于兼容） ====================

  ipcMain.handle(
    'initialize',
    async (event, targetBranch: string = 'dev', startBackend: boolean = true) =>
      runInitializationOperation('完整初始化', async () => {
        logger.info(`开始初始化 - 目标分支: ${targetBranch}, 启动后端: ${startBackend}`)

        const initService = getInitService(targetBranch)

        const result = await initService.initialize(progress => {
          // 发送进度到渲染进程
          event.sender.send('initialization-progress', progress)
        }, startBackend)

        if (result.success) {
          // 保存后端服务实例
          backendService = initService.getBackendService()

          // 设置状态回调
          backendService.setStatusCallback(status => {
            event.sender.send('backend-status', status)
          })

          logger.info(`初始化成功完成，阶段: ${result.completedStages.join(', ')}`)
        } else {
          logger.error(`初始化失败 - 错误: ${result.error}, 失败阶段: ${result.failedStage}`)
        }

        return result
      })
  )

  // ==================== 仅更新模式 ====================

  ipcMain.handle('update-only', async (event, targetBranch: string = 'dev') =>
    runInitializationOperation('完整更新', async () => {
      logger.info(`开始更新模式 - 目标分支: ${targetBranch}`)

      const initService = getInitService(targetBranch)

      const result = await initService.updateOnly(progress => {
        event.sender.send('initialization-progress', progress)
      })

      if (!result.success) {
        logger.error(`更新失败: ${result.error}`)
      }

      return result
    })
  )

  // ==================== 后端服务管理 ====================

  ipcMain.handle('backend-start', async event => {
    logger.info('启动后端服务')

    const backend = getBackendService()

    // 设置状态回调
    backend.setStatusCallback(status => {
      event.sender.send('backend-status', status)
    })

    const result = await backend.startBackend()

    if (!result.success) {
      logger.error(`后端启动失败: ${result.error}`)
    }

    return result
  })

  ipcMain.handle('backend-stop', async () => {
    logger.info('停止后端服务')

    const backend = getBackendService()
    const result = await backend.stopBackend()

    if (!result.success) {
      logger.error(`后端停止失败: ${result.error}`)
    }

    return result
  })

  ipcMain.handle('backend-restart', async event => {
    logger.info('重启后端服务')

    const backend = getBackendService()

    // 设置状态回调
    backend.setStatusCallback(status => {
      event.sender.send('backend-status', status)
    })

    const result = await backend.restartBackend()

    if (!result.success) {
      logger.error(`后端重启失败: ${result.error}`)
    }

    return result
  })

  ipcMain.handle('backend-status', () => {
    const backend = getBackendService()
    return backend.getStatus()
  })

  ipcMain.handle('backend-wait-ready', async () => {
    const backend = getBackendService()
    try {
      await backend.waitUntilReady()
      return { ready: true }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      return { ready: false, reason }
    }
  })

  // ==================== 清理 ====================

  ipcMain.handle('cleanup', async () => {
    return await cleanupInitializationResources()
  })
}

/**
 * 仅返回当前 Electron 实例跟踪或经归属标记验证的生产后端。
 */
export async function getManagedBackendProcesses() {
  return await getBackendService().getManagedProcesses()
}

/**
 * 清理所有资源（应用退出时调用）
 */
export async function cleanupInitializationResources(): Promise<InitializationCleanupResult> {
  if (cleanupPromise) {
    return await cleanupPromise
  }

  const service = getBackendService()
  const operation = (async (): Promise<InitializationCleanupResult> => {
    logger.info('安全清理当前安装目录的后端资源')

    try {
      const stopResult = await service.stopBackendForRuntimeMutation()
      if (!stopResult.success) {
        const error = stopResult.error || '无法安全停止当前安装目录的后端'
        logger.warn(`后端资源未清理: ${error}`)
        return { success: false, error }
      }

      if (backendService === service) {
        backendService = null
        initService = null
      }
      logger.info('当前安装目录的后端资源清理完成')
      return { success: true }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      logger.error(`安全清理后端资源失败: ${reason}`)
      return { success: false, error: reason }
    }
  })()

  cleanupPromise = operation
  try {
    return await operation
  } finally {
    if (cleanupPromise === operation) {
      cleanupPromise = null
    }
  }
}
