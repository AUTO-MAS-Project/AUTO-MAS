/**
 * 初始化相关的 IPC 处理器
 * 使用新的服务
 */

import { ipcMain, BrowserWindow, IpcMainInvokeEvent } from 'electron'
import * as path from 'path'
import { getAppRoot } from '../services/environmentService'
import { InitializationService } from '../services'
import type { BackendService } from '../services/backendService'
import { getLogger } from '../services/logger'
import type { RuntimeBinaryAlignResult } from '../services/runtimeBinaryService'
import type { ApiEndpoints, MirrorConfig } from '../services/mirrorService'
import type { RuntimeLaunchMode } from '../services/runtime'
import { resolveRuntimeLaunchConfig, resolveRuntimeLaunchMode } from '../services/runtime'
import type {
  CriticalFilesCheck,
  InitializationRunStage,
  RuntimeRetryMode,
  RuntimeStageOutcome,
} from '../services/runtimeInitializationService'
import {
  listRuntimeMappableMirrorKeys,
  mapDoctorChecksToCriticalFiles,
} from '../services/runtimeInitializationService'
import type {
  RuntimeUpdateOutcome,
  RuntimeUpdateRetryAction,
} from '../services/runtimeUpdateService'
import {
  cancelBackendUpdate,
  retryBackendUpdate,
  updateBackendViaRuntime,
} from '../services/runtimeUpdateService'

const logger = getLogger('初始化处理器')

// 防止重复注册：强退失败后重建窗口会再走一遍 createWindow
let isRegistered = false
const mirrorTypes = new Set<keyof MirrorConfig>(['python', 'get_pip', 'git', 'repo', 'pip_mirror'])
const apiEndpointKeys = new Set<keyof ApiEndpoints>(['local', 'websocket'])

const isMirrorType = (value: unknown): value is keyof MirrorConfig =>
  typeof value === 'string' && mirrorTypes.has(value as keyof MirrorConfig)

const isApiEndpointKey = (value: unknown): value is keyof ApiEndpoints =>
  typeof value === 'string' && apiEndpointKeys.has(value as keyof ApiEndpoints)

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

/**
 * 主进程与渲染进程共用的后端端点解析。
 *
 * Runtime 就绪后使用 `state:running` 下发的 baseUrl；开发与受管模式的端口由 Runtime 决定。
 */
function resolveApiEndpoints(): ApiEndpoints {
  const runtimeEndpoints = getBackendService().getRuntimeApiEndpoints()
  if (runtimeEndpoints) return runtimeEndpoints

  return getInitService().getMirrorService().getApiEndpoints()
}

export function getLocalApiEndpoint(): string {
  return resolveApiEndpoints().local
}

/**
 * Runtime 链路下的单步执行与重试。
 *
 * 界面上的「重试」与「切换镜像后重试」用的都是下面这几个安装 handler，Runtime 链路下
 * 它们转成对应的下层命令（`environment ensure` / `workspace sync` / `dependencies sync`），
 * 普通重试选了镜像源则整条 `bootstrap` 带 `--mirror` 重跑；显式重建保留重建命令。
 *
 * 逐步进度通道是按步骤分的，渲染进程只看进度数值不看段名，所以这里只转发本段的进度，
 * 否则整条 bootstrap 重跑时 `mirror` / `pip` / `git` 的完成进度会把当前步骤误标成完成。
 *
 * `rebuild` 对应界面上「重建环境」这个按钮：它与「重试」共用本通道，只是要求 Runtime
 * 走重建版本的下层命令。IPC 上只传一个布尔量，主进程里统一按
 * {@link RuntimeRetryMode} 表达；不传或传 false 都退回 `auto`，仍按上一次失败的
 * remediation 决定，不把普通「重试」硬钉成「不重建」。
 */
function toRetryMode(rebuild?: boolean): RuntimeRetryMode {
  return rebuild ? 'rebuild' : 'auto'
}

async function runStageViaRuntime(
  event: IpcMainInvokeEvent,
  stage: InitializationRunStage,
  progressChannel: string,
  selectedMirror?: string,
  rebuild?: boolean
): Promise<RuntimeStageOutcome> {
  const initService = getInitService()
  return initService.retryStageViaRuntime(
    stage,
    progress => {
      if (progress.stage !== stage) return
      sendToSender(event, progressChannel, progress)
    },
    selectedMirror,
    toRetryMode(rebuild)
  )
}

/**
 * 界面开局要问一次的 Runtime 上下文。
 *
 * 三件事各有各的来源，但界面在同一时刻需要它们：走没走 Runtime（决定步骤标签与哪些段
 * 直接置完成）、失败时「打开日志」拿不到 Runtime 日志路径要退回哪个文件、
 * 「换镜像重试」在 Runtime 下该列哪些镜像键。
 */
interface RuntimeInitContext {
  mode: RuntimeLaunchMode
  /** 本程序自己的日志文件，Runtime 没给 `logPath` 时的回退。 */
  fallbackLogPath: string
  /** 各段在 Runtime 链路下映射得到的旧镜像键；空数组表示该段不展示镜像选择。 */
  mirrorKeys: Record<InitializationRunStage, string[]>
}

export function resolveRuntimeInitContext(): RuntimeInitContext {
  return {
    mode: resolveRuntimeLaunchMode(getAppRoot()),
    fallbackLogPath: path.join(getAppRoot(), 'debug', 'frontend.log'),
    mirrorKeys: listRuntimeMappableMirrorKeys(),
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
export function registerInitializationHandlers(_mainWindow: BrowserWindow) {
  if (isRegistered) {
    logger.info('初始化处理器已经注册，跳过重复注册')
    return
  }
  isRegistered = true

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

  ipcMain.handle('install-python', async (event, selectedMirror?: string, rebuild?: boolean) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装Python: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(
      event,
      'python',
      'python-progress',
      selectedMirror,
      rebuild
    )
    return runtimeOutcome
  })

  // ==================== Pip 安装 ====================

  ipcMain.handle('install-pip', async (event, selectedMirror?: string, rebuild?: boolean) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装Pip: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(
      event,
      'pip',
      'pip-progress',
      selectedMirror,
      rebuild
    )
    return runtimeOutcome
  })

  // ==================== Git 安装 ====================

  ipcMain.handle('install-git', async (event, selectedMirror?: string, rebuild?: boolean) => {
    if (selectedMirror) {
      logger.info(`使用指定镜像源安装Git: ${selectedMirror}`)
    }

    const runtimeOutcome = await runStageViaRuntime(
      event,
      'git',
      'git-progress',
      selectedMirror,
      rebuild
    )
    return runtimeOutcome
  })

  // ==================== 源码拉取 ====================

  ipcMain.handle(
    'pull-repository',
    async (event, targetBranch: string = 'dev', selectedMirror?: string, rebuild?: boolean) => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源拉取源码: ${selectedMirror}`)
      }

      // Runtime 链路的目标分支由目标版本推导（`release/<版本>`），targetBranch 不参与。
      const runtimeOutcome = await runStageViaRuntime(
        event,
        'repository',
        'repository-progress',
        selectedMirror,
        rebuild
      )
      return runtimeOutcome
    }
  )

  // ==================== 依赖安装 ====================

  ipcMain.handle(
    'install-dependencies',
    async (event, selectedMirror?: string, rebuild?: boolean) => {
      if (selectedMirror) {
        logger.info(`使用指定镜像源安装依赖: ${selectedMirror}`)
      }

      const runtimeOutcome = await runStageViaRuntime(
        event,
        'dependency',
        'dependency-progress',
        selectedMirror,
        rebuild
      )
      return runtimeOutcome
    }
  )

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

  // ==================== Runtime 完整初始化流程 ====================

  ipcMain.handle(
    'initialize',
    async (event, targetBranch: string = 'dev', startBackend: boolean = true) => {
      logger.info(`开始初始化 - 目标分支: ${targetBranch}, 启动后端: ${startBackend}`)

      const initService = getInitService()

      const result = await initService.initialize(progress => {
        // 发送进度到渲染进程
        sendToSender(event, 'initialization-progress', progress)
      }, startBackend)

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
    const runtime = getInitService().getRuntimeService()
    return runtime.checkRuntimeBinaryUpdate()
  })

  ipcMain.handle('update-runtime-binary', async (event): Promise<RuntimeBinaryAlignResult> => {
    const init = getInitService()
    const runtime = init.getRuntimeService()
    if (runtime.launchConfig.mode !== 'managed') {
      return { status: 'failed', error: '当前运行模式不支持更新 Runtime。' }
    }
    if (runtimeBinaryUpdating || runtime.isBusy) {
      return { status: 'failed', error: '运行环境操作尚未结束，请稍后再试。' }
    }

    runtimeBinaryUpdating = true
    try {
      return await runtime.updateRuntimeBinary(
        progress => sendToSender(event, 'runtime-binary-progress', progress),
        async () => {
          // 先占用 Runtime 操作，再停止残留后端，避免等待退出时又开始 bootstrap。
          for (const backend of new Set([getBackendService(), init.getBackendService()])) {
            const result = await backend.stopBackend()
            if (!result.success) {
              throw new Error(result.error || '无法停止后端，请重启程序后重试。')
            }
          }
        }
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

  ipcMain.handle('backend-start', async event => {
    logger.info('启动后端服务')

    const backend = getBackendService()

    // 设置状态回调
    backend.setStatusCallback(status => {
      sendToSender(event, 'backend-status', status)
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

  ipcMain.handle('backend-restart', async (event, reason?: unknown) => {
    logger.info('重启后端服务')

    const backend = getBackendService()

    // 设置状态回调
    backend.setStatusCallback(status => {
      sendToSender(event, 'backend-status', status)
    })

    const result = await backend.restartBackend(
      undefined,
      reason === 'recovery' ? 'recovery' : 'manual'
    )

    if (!result.success) {
      logger.error(`后端重启失败: ${result.error}`)
    }

    return result
  })

  ipcMain.handle('backend-status', () => {
    const backend = getBackendService()
    return backend.getStatus()
  })

  ipcMain.handle('check-runtime-backend-update', async () => {
    return getBackendService().checkRuntimeBackendUpdate()
  })

  // ==================== Runtime 链路的后端更新 ====================

  // managed 更新由 Runtime 编排；development 的源码由开发者自行维护。
  ipcMain.handle(
    'update-backend-via-runtime',
    async (event, targetVersion: unknown): Promise<RuntimeUpdateOutcome> => {
      logger.info(`收到 Runtime 后端更新请求，目标版本: ${String(targetVersion)}`)

      const result = await updateBackendViaRuntime(
        typeof targetVersion === 'string' ? targetVersion : '',
        progress => sendToSender(event, BACKEND_UPDATE_PROGRESS_CHANNEL, progress),
        {
          backend: getBackendService(),
          launchConfig: resolveRuntimeLaunchConfig(getAppRoot()),
        }
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
      const result = await retryBackendUpdate(action, progress =>
        sendToSender(event, BACKEND_UPDATE_PROGRESS_CHANNEL, progress)
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
