/**
 * 初始化相关的 IPC 处理器
 * 使用新的服务
 */

import { ipcMain, BrowserWindow } from 'electron'
import { getAppRoot } from '../services/environmentService'
import { InitializationService, BackendService } from '../services'
import { getLogger } from '../services/logger'

const logger = getLogger('初始化处理器')

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
 * 获取后端服务实例
 */
function getBackendService(): BackendService {
    if (!backendService) {
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()
        backendService = new BackendService(appRoot, mirrorService)
    }

    return backendService
}

/**
 * 注册所有初始化相关的 IPC 处理器
 */
export function registerInitializationHandlers(mainWindow: BrowserWindow) {
    // ==================== 镜像源初始化 ====================

    ipcMain.handle('init-mirrors', async (event) => {
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        try {
            await mirrorService.initialize()
            logger.info('初始化处理器', '镜像源初始化成功')
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('初始化处理器', `镜像源初始化失败: ${errorMsg}`)
            return { success: false, error: errorMsg }
        }
    })

    // ==================== Python 安装 ====================

    ipcMain.handle('install-python', async (event, selectedMirror?: string) => {
        if (selectedMirror) {
            logger.info('初始化处理器', `使用指定镜像源安装Python: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { PythonInstaller } = await import('../services/environmentService')
        const installer = new PythonInstaller(appRoot, mirrorService)

        const result = await installer.install((progress) => {
            event.sender.send('python-progress', progress)
        }, selectedMirror)

        if (!result.success) {
            logger.error('初始化处理器', `Python安装失败: ${result.error}`)
        }

        return result
    })

    // ==================== Pip 安装 ====================

    ipcMain.handle('install-pip', async (event, selectedMirror?: string) => {
        if (selectedMirror) {
            logger.info('初始化处理器', `使用指定镜像源安装Pip: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { PipInstaller } = await import('../services/environmentService')
        const installer = new PipInstaller(appRoot, mirrorService)

        const result = await installer.install((progress) => {
            event.sender.send('pip-progress', progress)
        }, selectedMirror)

        if (!result.success) {
            logger.error('初始化处理器', `Pip安装失败: ${result.error}`)
        }

        return result
    })

    // ==================== Git 安装 ====================

    ipcMain.handle('install-git', async (event, selectedMirror?: string) => {
        if (selectedMirror) {
            logger.info('初始化处理器', `使用指定镜像源安装Git: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { GitInstaller } = await import('../services/environmentService')
        const installer = new GitInstaller(appRoot, mirrorService)

        const result = await installer.install((progress) => {
            event.sender.send('git-progress', progress)
        }, selectedMirror)

        if (!result.success) {
            logger.error('初始化处理器', `Git安装失败: ${result.error}`)
        }

        return result
    })

    // ==================== 源码拉取 ====================

    ipcMain.handle('pull-repository', async (event, targetBranch: string = 'dev', selectedMirror?: string) => {
        if (selectedMirror) {
            logger.info('初始化处理器', `使用指定镜像源拉取源码: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService(targetBranch)
        const mirrorService = initService.getMirrorService()

        const { RepositoryService } = await import('../services/repositoryService')
        const repoService = new RepositoryService(appRoot, mirrorService, targetBranch)

        const result = await repoService.pullRepository((progress) => {
            event.sender.send('repository-progress', progress)
        }, selectedMirror)

        if (!result.success) {
            logger.error('初始化处理器', `源码拉取失败: ${result.error}`)
        }

        return result
    })

    // ==================== 依赖安装 ====================

    ipcMain.handle('install-dependencies', async (event, selectedMirror?: string) => {
        if (selectedMirror) {
            logger.info('初始化处理器', `使用指定镜像源安装依赖: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { DependencyService } = await import('../services/dependencyService')
        const depService = new DependencyService(appRoot, mirrorService)

        const result = await depService.installDependencies((progress) => {
            event.sender.send('dependency-progress', progress)
        }, selectedMirror)

        if (!result.success) {
            logger.error('初始化处理器', `依赖安装失败: ${result.error}`)
        }

        return result
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

    ipcMain.handle('get-api-endpoints', async (event) => {
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        return mirrorService.getApiEndpoints()
    })

    // ==================== 完整初始化流程（保留用于兼容） ====================

    ipcMain.handle('initialize', async (event, targetBranch: string = 'dev', startBackend: boolean = true) => {
        logger.info('初始化处理器', `开始初始化 - 目标分支: ${targetBranch}, 启动后端: ${startBackend}`)

        const initService = getInitService(targetBranch)

        const result = await initService.initialize((progress) => {
            // 发送进度到渲染进程
            event.sender.send('initialization-progress', progress)
        }, startBackend)

        if (result.success) {
            // 保存后端服务实例
            backendService = initService.getBackendService()

            // 设置状态回调
            backendService.setStatusCallback((status) => {
                event.sender.send('backend-status', status)
            })

            logger.info('初始化处理器', `初始化成功完成，阶段: ${result.completedStages.join(', ')}`)
        } else {
            logger.error('初始化处理器', `初始化失败 - 错误: ${result.error}, 失败阶段: ${result.failedStage}`)
        }

        return result
    })

    // ==================== 仅更新模式 ====================

    ipcMain.handle('update-only', async (event, targetBranch: string = 'dev') => {
        logger.info('初始化处理器', `开始更新模式 - 目标分支: ${targetBranch}`)

        const initService = getInitService(targetBranch)

        const result = await initService.updateOnly((progress) => {
            event.sender.send('initialization-progress', progress)
        })

        if (!result.success) {
            logger.error('初始化处理器', `更新失败: ${result.error}`)
        }

        return result
    })

    // ==================== 后端服务管理 ====================

    ipcMain.handle('backend-start', async (event) => {
        logger.info('初始化处理器', '启动后端服务')

        const backend = getBackendService()

        // 设置状态回调
        backend.setStatusCallback((status) => {
            event.sender.send('backend-status', status)
        })

        const result = await backend.startBackend()

        if (!result.success) {
            logger.error('初始化处理器', `后端启动失败: ${result.error}`)
        }

        return result
    })

    ipcMain.handle('backend-stop', async () => {
        logger.info('初始化处理器', '停止后端服务')

        const backend = getBackendService()
        const result = await backend.stopBackend()

        if (!result.success) {
            logger.error('初始化处理器', `后端停止失败: ${result.error}`)
        }

        return result
    })

    ipcMain.handle('backend-restart', async (event) => {
        logger.info('初始化处理器', '重启后端服务')

        const backend = getBackendService()

        // 设置状态回调
        backend.setStatusCallback((status) => {
            event.sender.send('backend-status', status)
        })

        const result = await backend.restartBackend()

        if (!result.success) {
            logger.error('初始化处理器', `后端重启失败: ${result.error}`)
        }

        return result
    })

    ipcMain.handle('backend-status', () => {
        const backend = getBackendService()
        return backend.getStatus()
    })

    // ==================== 清理 ====================

    ipcMain.handle('cleanup', async () => {
        logger.info('初始化处理器', '清理初始化资源')

        if (backendService) {
            await backendService.cleanup()
            backendService = null
        }

        initService = null

        logger.info('初始化处理器', '资源清理完成')

        return { success: true }
    })
}

/**
 * 清理所有资源（应用退出时调用）
 */
export async function cleanupInitializationResources() {
    logger.info('初始化处理器', '清理初始化资源')

    if (backendService) {
        await backendService.cleanup()
        backendService = null
    }

    initService = null

    logger.info('初始化处理器', '初始化资源清理完成')
}
