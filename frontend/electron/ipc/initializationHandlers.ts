/**
 * 初始化相关的 IPC 处理器
 * 使用新的服务
 */

import { ipcMain, BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { getAppRoot } from '../services/environmentService'
import { InitializationService, BackendService } from '../services'
import { getLogger } from '../services/logger'
import type { ApiEndpoints, MirrorConfig } from '../services/mirrorService'
import type {
  CriticalFilesCheck,
  InitializationRunStage,
  RuntimeStageOutcome,
} from '../services/runtimeInitializationService'
import { mapDoctorChecksToCriticalFiles } from '../services/runtimeInitializationService'

const logger = getLogger('初始化处理器')
const mirrorTypes = new Set<keyof MirrorConfig>(['python', 'get_pip', 'git', 'repo', 'pip_mirror'])
const apiEndpointKeys = new Set<keyof ApiEndpoints>(['local', 'websocket'])

const isMirrorType = (value: unknown): value is keyof MirrorConfig =>
  typeof value === 'string' && mirrorTypes.has(value as keyof MirrorConfig)

const isApiEndpointKey = (value: unknown): value is keyof ApiEndpoints =>
  typeof value === 'string' && apiEndpointKeys.has(value as keyof ApiEndpoints)

// 全局实例
let initService: InitializationService | null = null
let backendService: BackendService | null = null

/**
 * 获取或创建初始化服务实例
 */
function getInitService(targetBranch: string = 'dev'): InitializationService {
  const appRoot = getAppRoot()

  if (!initService) {
    initService = new InitializationService(appRoot, targetBranch)
  }

  return initService
}

/**
 * 获取后端服务实例（主进程协调关闭时用于开发模式判定与限定范围强杀）
 */
export function getBackendService(): BackendService {
  if (!backendService) {
    const appRoot = getAppRoot()
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()
    backendService = new BackendService(appRoot, mirrorService)
  }

  return backendService
}

/**
 * 主进程与渲染进程共用的后端端点解析。
 *
 * Runtime 监督链路就绪后必须用它在 `state:running` 事件里下发的 baseUrl（协议 v1 固定
 * 36163），不能再按 `resolveHttpPort()` 的开发/正式分流算端口；旧链路仍走镜像源服务。
 */
function resolveApiEndpoints(): ApiEndpoints {
  const initService = getInitService()
  // 完整初始化流程用 InitializationService 内部的实例启动后端，backend-start 用模块级实例，
  // 两条路径都可能持有 Runtime 句柄，取先就绪的那个。
  const runtimeEndpoints =
    getBackendService().getRuntimeApiEndpoints() ??
    initService.getBackendService().getRuntimeApiEndpoints()
  if (runtimeEndpoints) return runtimeEndpoints

  return initService.getMirrorService().getApiEndpoints()
}

export function getLocalApiEndpoint(): string {
  return resolveApiEndpoints().local
}

/**
 * Runtime 链路下的单步执行与重试。
 *
 * 界面上的「重试」与「切换镜像后重试」用的都是下面这几个安装 handler，Runtime 链路下
 * 它们转成对应的下层命令（`environment ensure` / `workspace sync` / `dependencies sync`），
 * 选了镜像源则整条 `bootstrap` 带 `--mirror` 重跑。返回 null 表示灰度开关关闭，走旧链路。
 *
 * 逐步进度通道是按步骤分的，渲染进程只看进度数值不看段名，所以这里只转发本段的进度，
 * 否则整条 bootstrap 重跑时 `mirror` / `pip` / `git` 的完成进度会把当前步骤误标成完成。
 */
async function runStageViaRuntime(
  event: IpcMainInvokeEvent,
  stage: InitializationRunStage,
  progressChannel: string,
  selectedMirror?: string
): Promise<RuntimeStageOutcome | null> {
  const initService = getInitService()
  return initService.retryStageViaRuntime(
    stage,
    progress => {
      if (progress.stage !== stage) return
      event.sender.send(progressChannel, progress)
    },
    selectedMirror
  )
}

/**
 * Runtime 链路下的关键文件检查。
 *
 * 旧链路数 exe 文件，新链路问 Runtime `doctor`：受管布局里 `repo` 缺失就是没装过。
 * 返回 null 表示灰度开关关闭或 doctor 没跑成，调用方继续走旧的文件存在性检查。
 */
export async function checkCriticalFilesViaRuntime(): Promise<CriticalFilesCheck | null> {
  const runtimeService = getInitService().getRuntimeService()
  if (!runtimeService) return null

  const checks = await runtimeService.doctor()
  if (!checks) {
    logger.warn('Runtime doctor 未给出检查结果，按未初始化处理')
    return { pythonExists: false, pipExists: false, gitExists: false, mainPyExists: false }
  }

  const result = mapDoctorChecksToCriticalFiles(checks)
  logger.info(`Runtime doctor 检查结果 - 受管仓库${result.mainPyExists ? '已就绪' : '缺失'}`)
  return result
}

/**
 * 注册所有初始化相关的 IPC 处理器
 */
export function registerInitializationHandlers(_mainWindow: BrowserWindow) {
  // ==================== 镜像源初始化 ====================

  ipcMain.handle('init-mirrors', async () => {
    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    try {
      await mirrorService.initialize()
      logger.info('镜像源初始化成功')
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`镜像源初始化失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  })

  // ==================== Python 安装 ====================

  ipcMain.handle('install-python', async (event, selectedMirror?: string) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装Python: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(
      event,
      'python',
      'python-progress',
      selectedMirror
    )
    if (runtimeOutcome) return runtimeOutcome

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

  // ==================== Pip 安装 ====================

  ipcMain.handle('install-pip', async (event, selectedMirror?: string) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装Pip: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(event, 'pip', 'pip-progress', selectedMirror)
    if (runtimeOutcome) return runtimeOutcome

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

  // ==================== Git 安装 ====================

  ipcMain.handle('install-git', async (event, selectedMirror?: string) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装Git: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(event, 'git', 'git-progress', selectedMirror)
    if (runtimeOutcome) return runtimeOutcome

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

  // ==================== 源码拉取 ====================

  ipcMain.handle(
    'pull-repository',
    async (event, targetBranch: string = 'dev', selectedMirror?: string) => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源拉取源码: ${selectedMirror}`)
      }

      // Runtime 链路的目标分支由目标版本推导（`release/<版本>`），targetBranch 不参与。
      const runtimeOutcome = await runStageViaRuntime(
        event,
        'repository',
        'repository-progress',
        selectedMirror
      )
      if (runtimeOutcome) return runtimeOutcome

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
    }
  )

  // ==================== 依赖安装 ====================

  ipcMain.handle('install-dependencies', async (event, selectedMirror?: string) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装依赖: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(
      event,
      'dependency',
      'dependency-progress',
      selectedMirror
    )
    if (runtimeOutcome) return runtimeOutcome

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

  // ==================== 获取镜像源列表 ====================

  ipcMain.handle('get-mirrors', async (_event, type: unknown) => {
    if (!isMirrorType(type)) throw new TypeError(`不支持的镜像源类型: ${String(type)}`)

    const initService = getInitService()
    const mirrorService = initService.getMirrorService()

    const mirrors = mirrorService.getMirrors(type)
    return mirrors
  })

  // ==================== 获取 API 端点 ====================

  ipcMain.handle('get-api-endpoint', async (_event, key: unknown) => {
    if (!isApiEndpointKey(key)) throw new TypeError(`不支持的 API 端点: ${String(key)}`)

    return resolveApiEndpoints()[key]
  })

  ipcMain.handle('get-api-endpoints', async () => {
    return resolveApiEndpoints()
  })

  // ==================== 完整初始化流程（保留用于兼容） ====================

  ipcMain.handle(
    'initialize',
    async (event, targetBranch: string = 'dev', startBackend: boolean = true) => {
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
    }
  )

  // ==================== 仅更新模式 ====================

  ipcMain.handle('update-only', async (event, targetBranch: string = 'dev') => {
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

  // ==================== 清理 ====================

  ipcMain.handle('cleanup', async () => {
    logger.info('清理初始化资源')

    if (backendService) {
      await backendService.cleanup()
      backendService = null
    }

    initService = null

    logger.info('资源清理完成')

    return { success: true }
  })
}

/**
 * 清理所有资源（应用退出时调用）
 */
export async function cleanupInitializationResources() {
  logger.info('清理初始化资源')

  if (backendService) {
    await backendService.cleanup()
    backendService = null
  }

  initService = null

  logger.info('初始化资源清理完成')
}
