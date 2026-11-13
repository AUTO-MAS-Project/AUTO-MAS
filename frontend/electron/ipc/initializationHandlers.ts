/**
 * 初始化相关的 IPC 处理器
 * 使用新的服务
 */

import { app, ipcMain, BrowserWindow, IpcMainInvokeEvent } from 'electron'
import * as path from 'path'
import { getAppRoot } from '../services/environmentService'
import { InitializationService } from '../services'
import { getDefaultApiEndpoints } from '../services/instanceConfig'
import type { BackendService } from '../services/backendService'
import { getLogger } from '../services/logger'
import { prepareCoreUpgrade, prepareRuntimeBinary } from '../services/runtimeUpgradePreparation'
import type { RuntimeBinaryAlignResult } from '../services/runtimeBinaryService'
import type { RuntimeLaunchMode } from '../services/runtime'
import { resolveRuntimeLaunchConfig, resolveRuntimeLaunchMode } from '../services/runtime'
import type {
  CriticalFilesCheck,
  InitializationRunStage,
  RuntimeRetryMode,
  RuntimeStageOutcome,
} from '../services/runtimeInitializationService'
import { mapDoctorChecksToCriticalFiles } from '../services/runtimeInitializationService'
import type {
  RuntimeUpdateOutcome,
  RuntimeUpdateRetryAction,
} from '../services/runtimeUpdateService'
import {
  abortRuntimeUpdateForShutdown,
  cancelBackendUpdate,
  retryBackendUpdate,
  updateBackendViaRuntime,
} from '../services/runtimeUpdateService'

const logger = getLogger('初始化处理器')

// 防止重复注册：强退失败后重建窗口会再走一遍 createWindow
let isRegistered = false
type ApiEndpoints = ReturnType<typeof getDefaultApiEndpoints>
const isApiEndpointKey = (value: unknown): value is keyof ApiEndpoints =>
  value === 'local' || value === 'websocket'

/** 更新流程的进度事件通道，与初始化的分段进度通道分开，互不干扰。 */
const BACKEND_UPDATE_PROGRESS_CHANNEL = 'backend-update-progress'

const retryActions = new Set<RuntimeUpdateRetryAction>([
  'bootstrap',
  'workspace-sync',
  'dependencies-sync',
  'dependencies-rebuild',
  'repair',
])

const isRetryAction = (value: unknown): value is RuntimeUpdateRetryAction =>
  typeof value === 'string' && retryActions.has(value as RuntimeUpdateRetryAction)

// 全局实例
let initService: InitializationService | null = null
let initializationWindow: BrowserWindow | null = null
let runtimeBinaryUpdating = false

/**
 * 向发起 IPC 调用的渲染进程回推事件。
 *
 * 初始化进度回调与后端状态回调都活得比一次 IPC 调用长：窗口已关闭、应用正在退出时，
 * Runtime 子进程仍会往 stdout 吐 bootstrap 进度，后端子进程退出也会触发状态回调。这时
 * 再对已销毁的 `WebContents` 调用 `send` 会抛「Object has been destroyed」，并且是在
 * 子进程事件回调里抛出、无人接住，直接成为主进程的未捕获异常。渲染进程已销毁时静默丢弃。
 */
function sendToSender(event: IpcMainInvokeEvent, channel: string, payload: unknown): void {
  const sender = event.sender
  if (sender.isDestroyed()) return
  sender.send(channel, payload)
}

/**
 * 获取或创建初始化服务实例
 */
function getInitService(): InitializationService {
  const appRoot = getAppRoot()

  if (!initService) {
    initService = new InitializationService(appRoot)
  }

  return initService
}

/**
 * 获取唯一的后端服务实例（初始化、重启和退出共用）
 */
export function getBackendService(): BackendService {
  return getInitService().getBackendService()
}

/** Electron ready 时发起，窗口只接入结果。 */
export function startDesktopStartup(preferences: {
  version: string
  initializedVersion?: string
  autoUpdate: boolean
}) {
  return getInitService().startDesktopStartup(preferences, progress => {
    const sender = initializationWindow?.webContents
    if (sender && !sender.isDestroyed()) sender.send('initialization-progress', progress)
  })
}

export async function stopDesktopStartup(shutdown = false) {
  await Promise.all([
    abortRuntimeUpdateForShutdown(),
    getInitService().stopDesktopStartup(shutdown),
  ])
}

/**
 * 主进程与渲染进程共用的后端端点解析。
 *
 * Runtime 就绪后使用 `state:running` 下发的 baseUrl；开发与受管模式的端口由 Runtime 决定。
 */
function resolveApiEndpoints(): ApiEndpoints {
  if (!getInitService().ownsBackend) return getDefaultApiEndpoints()
  const runtimeEndpoints = getBackendService().getRuntimeApiEndpoints()
  if (runtimeEndpoints) return runtimeEndpoints

  return getDefaultApiEndpoints()
}

export function getLocalApiEndpoint(): string {
  return resolveApiEndpoints().local
}

/** 分段恢复由 Runtime 执行；显式重建与普通重试保持独立。 */
function toRetryMode(rebuild?: boolean): RuntimeRetryMode {
  return rebuild ? 'rebuild' : 'sync'
}

async function runStageViaRuntime(
  event: IpcMainInvokeEvent,
  stage: InitializationRunStage,
  rebuild?: boolean
): Promise<RuntimeStageOutcome> {
  const initService = getInitService()
  return initService.runEnvironmentOperation(() =>
    initService.retryStageViaRuntime(
      stage,
      progress => {
        sendToSender(event, 'initialization-progress', progress)
      },
      toRetryMode(rebuild)
    )
  )
}

/** 初始化界面的运行模式与 Runtime 日志缺失时的回退路径。 */
interface RuntimeInitContext {
  mode: RuntimeLaunchMode
  fallbackLogPath: string
}

export function resolveRuntimeInitContext(): RuntimeInitContext {
  return {
    mode: resolveRuntimeLaunchMode(),
    fallbackLogPath: path.join(getAppRoot(), 'debug', 'frontend.log'),
  }
}

/**
 * Runtime 链路下的关键文件检查。
 *
 * 使用 Runtime doctor 的检查结果；未给出可靠结果时按未初始化处理。
 */
export async function checkCriticalFilesViaRuntime(): Promise<CriticalFilesCheck> {
  const runtimeService = getInitService().getRuntimeService()

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
export function registerInitializationHandlers(mainWindow: BrowserWindow) {
  // 注册环境初始化及 Runtime 更新入口，复用当前应用窗口并避免重复注册处理器。
  initializationWindow = mainWindow
  if (isRegistered) {
    logger.info('初始化处理器已经注册，跳过重复注册')
    return
  }
  isRegistered = true

  ipcMain.handle('install-python', (event, rebuild?: boolean) =>
    runStageViaRuntime(event, 'python', rebuild)
  )

  ipcMain.handle('pull-repository', (event, rebuild?: boolean) =>
    runStageViaRuntime(event, 'repository', rebuild)
  )

  ipcMain.handle('install-dependencies', (event, rebuild?: boolean) =>
    runStageViaRuntime(event, 'dependency', rebuild)
  )

  // ==================== 获取 API 端点 ====================

  ipcMain.handle('get-api-endpoint', async (_event, key: unknown) => {
    if (!isApiEndpointKey(key)) throw new TypeError(`不支持的 API 端点: ${String(key)}`)

    return resolveApiEndpoints()[key]
  })

  // ==================== Runtime 完整初始化流程 ====================

  ipcMain.handle(
    'initialize',
    async (event, targetBranch: string = 'dev', startBackend: boolean = true) => {
      logger.info(`开始初始化 - 目标分支: ${targetBranch}, 启动后端: ${startBackend}`)

      const initService = getInitService()

      const result = await initService.runEnvironmentOperation(() =>
        initService.initialize(progress => {
          sendToSender(event, 'initialization-progress', progress)
        }, startBackend)
      )

      if (result.success) {
        // 保存后端服务实例
        const backendService = initService.getBackendService()

        // 设置状态回调
        backendService.setStatusCallback(status => {
          sendToSender(event, 'backend-status', status)
        })

        logger.info(`初始化成功完成，阶段: ${result.completedStages.join(', ')}`)
      } else {
        logger.error(`初始化失败 - 错误: ${result.error}, 失败阶段: ${result.failedStage}`)
      }

      return result
    }
  )

  // ==================== 仅更新模式 ====================

  ipcMain.handle('check-runtime-binary-update', async () => {
    if (!getInitService().ownsBackend) return { status: 'skipped' }
    const runtime = getInitService().getRuntimeService()
    return runtime.checkRuntimeBinaryUpdate()
  })

  ipcMain.handle('update-runtime-binary', async (event): Promise<RuntimeBinaryAlignResult> => {
    // 校验受管模式与独占操作状态，准备 Runtime 对齐材料并按进度执行更新。
    const init = getInitService()
    if (!init.ownsBackend) return { status: 'failed', error: '当前仅连接外部后端。' }
    const runtime = init.getRuntimeService()
    if (runtime.launchConfig.mode !== 'managed') {
      return { status: 'failed', error: '当前运行模式不支持更新 Runtime。' }
    }
    if (runtimeBinaryUpdating || runtime.isBusy) {
      return { status: 'failed', error: '运行环境操作尚未结束，请稍后再试。' }
    }

    runtimeBinaryUpdating = true
    try {
      const alignment = await prepareRuntimeBinary(
        runtime.launchConfig,
        getLocalApiEndpoint(),
        app.getVersion()
      )
      return await init.runEnvironmentOperation(() =>
        /* 在环境独占操作内更新 Runtime，停止所属后端后再使用已准备的对齐材料。 */ runtime.updateRuntimeBinary(
          progress => sendToSender(event, 'runtime-binary-progress', progress),
          async () => {
            // 先占用 Runtime 操作，再停止残留后端，避免等待退出时又开始 bootstrap。
            const result = await init.getBackendService().stopBackend()
            if (!result.success) {
              throw new Error(result.error || '无法停止后端，请重启程序后重试。')
            }
          },
          alignment
        )
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      logger.error(`更新 Runtime 失败: ${message}`)
      return { status: 'failed', error: message }
    } finally {
      runtimeBinaryUpdating = false
    }
  })

  // ==================== 后端服务管理 ====================

  ipcMain.handle('desktop-startup-wait', () => getInitService().waitForDesktopStartup())
  ipcMain.handle('desktop-startup-status', () => getInitService().getDesktopStartupSnapshot())
  ipcMain.handle('desktop-startup-cancel', () => stopDesktopStartup())

  ipcMain.handle('backend-start', async (event, retry = false) => {
    logger.info('启动后端服务')

    const backend = getBackendService()

    // 设置状态回调
    backend.setStatusCallback(status => {
      sendToSender(event, 'backend-status', status)
    })

    const init = getInitService()
    if (retry) init.resetDesktopStartup()
    const startup = await init.waitForDesktopStartup()
    if (startup && !startup.success) return startup
    if (runtimeBinaryUpdating || init.isEnvironmentBusy) {
      return { success: false, error: '运行环境操作尚未结束，请稍后再试。' }
    }
    const result = await backend.startBackend()

    if (!result.success) {
      logger.error(`后端启动失败: ${result.error}`)
    }

    return result
  })

  ipcMain.handle('backend-stop', async () => {
    logger.info('停止后端服务')
    if (!getInitService().ownsBackend) return { success: false, error: '当前仅连接外部后端。' }
    await stopDesktopStartup()
    return { success: true }
  })

  ipcMain.handle('backend-restart', async (event, reason?: unknown) => {
    logger.info('重启后端服务')

    const backend = getBackendService()

    // 设置状态回调
    backend.setStatusCallback(status => {
      sendToSender(event, 'backend-status', status)
    })

    const result = await getInitService().runEnvironmentOperation(() =>
      backend.restartBackend(undefined, reason === 'recovery' ? 'recovery' : 'manual')
    )

    if (!result.success) {
      logger.error(`后端重启失败: ${result.error}`)
    }

    return result
  })

  ipcMain.handle('backend-status', async () => {
    if (!getInitService().ownsBackend) {
      try {
        const response = await fetch(`${getLocalApiEndpoint()}/api/core/health`, {
          signal: AbortSignal.timeout(3000),
        })
        const health: unknown = response.ok ? await response.json() : null
        return {
          isRunning:
            typeof health === 'object' &&
            health !== null &&
            'ready' in health &&
            health.ready === true,
          runtimeSupervised: false,
        }
      } catch {
        return { isRunning: false, runtimeSupervised: false }
      }
    }
    const backend = getBackendService()
    return backend.getStatus()
  })

  ipcMain.handle('check-runtime-backend-update', async () => {
    if (!getInitService().ownsBackend) return { staged: false }
    return getBackendService().checkRuntimeBackendUpdate()
  })

  // ==================== Runtime 链路的后端更新 ====================

  // managed 更新由 Runtime 编排；development 的源码由开发者自行维护。
  ipcMain.handle(
    'update-backend-via-runtime',
    async (event, targetVersion: unknown): Promise<RuntimeUpdateOutcome> => {
      // 接收目标后端版本，在环境独占操作内执行前端预检和 Runtime 更新并返回结果。
      logger.info(`收到 Runtime 后端更新请求，目标版本: ${String(targetVersion)}`)

      const result = await getInitService().runEnvironmentOperation(() =>
        /* 使用当前后端和启动配置执行目标版本更新，将进度事件转发给请求页面。 */ updateBackendViaRuntime(
          typeof targetVersion === 'string' ? targetVersion : '',
          progress => sendToSender(event, BACKEND_UPDATE_PROGRESS_CHANNEL, progress),
          {
            backend: getBackendService(),
            launchConfig: resolveRuntimeLaunchConfig(getAppRoot()),
            prepareUpgrade: (version, signal) =>
              /* 为目标后端版本调用前端升级准备流程，完成目标依赖读取和后端兼容性预检。 */ prepareCoreUpgrade(
                resolveRuntimeLaunchConfig(getAppRoot()),
                getLocalApiEndpoint(),
                version,
                signal
              ),
          }
        )
      )

      if (!result.success) {
        logger.error(`Runtime 后端更新失败（${result.phase}）: ${result.error}`)
      }
      return result
    }
  )

  ipcMain.handle(
    'retry-backend-update',
    async (event, action: unknown): Promise<RuntimeUpdateOutcome> => {
      if (!isRetryAction(action)) throw new TypeError(`不支持的重试入口: ${String(action)}`)

      logger.info(`重试 Runtime 后端更新: ${action}`)
      const result = await getInitService().runEnvironmentOperation(() =>
        retryBackendUpdate(action, progress =>
          sendToSender(event, BACKEND_UPDATE_PROGRESS_CHANNEL, progress)
        )
      )

      if (!result.success) {
        logger.error(`Runtime 后端更新重试失败（${result.phase}）: ${result.error}`)
      }
      return result
    }
  )

  ipcMain.handle('cancel-backend-update', () => cancelBackendUpdate())

  // ==================== 清理 ====================
}
