/**
 * 初始化相关的 IPC 处理器
 * 使用新的 V2 服务
 */

import { ipcMain, BrowserWindow } from 'electron'
import { getAppRoot } from '../services/environmentService'
import { InitializationService, BackendService } from '../services'

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
        backendService = new BackendService(appRoot)
    }

    return backendService
}

/**
 * 注册所有初始化相关的 IPC 处理器
 */
export function registerInitializationHandlers(mainWindow: BrowserWindow) {
    // ==================== 镜像源初始化 ====================

    ipcMain.handle('v2:init-mirrors', async (event) => {
        console.log('=== V2 初始化镜像源 ===')
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        try {
            await mirrorService.initialize()
            console.log('✅ 镜像源初始化成功')
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            console.error('❌ 镜像源初始化失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    })

    // ==================== Python 安装 ====================

    ipcMain.handle('v2:install-python', async (event, selectedMirror?: string) => {
        console.log('=== V2 安装 Python ===')
        if (selectedMirror) {
            console.log(`使用指定镜像源: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { PythonInstaller } = await import('../services/environmentService')
        const installer = new PythonInstaller(appRoot, mirrorService)

        const result = await installer.install((progress) => {
            event.sender.send('v2:python-progress', progress)
        }, selectedMirror)

        console.log(`Python 安装结果: ${result.success ? '成功' : '失败'}`)
        return result
    })

    // ==================== Pip 安装 ====================

    ipcMain.handle('v2:install-pip', async (event, selectedMirror?: string) => {
        console.log('=== V2 安装 Pip ===')
        if (selectedMirror) {
            console.log(`使用指定镜像源: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { PipInstaller } = await import('../services/environmentService')
        const installer = new PipInstaller(appRoot, mirrorService)

        const result = await installer.install((progress) => {
            event.sender.send('v2:pip-progress', progress)
        }, selectedMirror)

        console.log(`Pip 安装结果: ${result.success ? '成功' : '失败'}`)
        return result
    })

    // ==================== Git 安装 ====================

    ipcMain.handle('v2:install-git', async (event, selectedMirror?: string) => {
        console.log('=== V2 安装 Git ===')
        if (selectedMirror) {
            console.log(`使用指定镜像源: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { GitInstaller } = await import('../services/environmentService')
        const installer = new GitInstaller(appRoot, mirrorService)

        const result = await installer.install((progress) => {
            event.sender.send('v2:git-progress', progress)
        }, selectedMirror)

        console.log(`Git 安装结果: ${result.success ? '成功' : '失败'}`)
        return result
    })

    // ==================== 源码拉取 ====================

    ipcMain.handle('v2:pull-repository', async (event, targetBranch: string = 'dev', selectedMirror?: string) => {
        console.log('=== V2 拉取源码 ===')
        if (selectedMirror) {
            console.log(`使用指定镜像源: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService(targetBranch)
        const mirrorService = initService.getMirrorService()

        const { RepositoryService } = await import('../services/repositoryService')
        const repoService = new RepositoryService(appRoot, mirrorService, targetBranch)

        const result = await repoService.pullRepository((progress) => {
            event.sender.send('v2:repository-progress', progress)
        }, selectedMirror)

        console.log(`源码拉取结果: ${result.success ? '成功' : '失败'}`)
        return result
    })

    // ==================== 依赖安装 ====================

    ipcMain.handle('v2:install-dependencies', async (event, selectedMirror?: string) => {
        console.log('=== V2 安装依赖 ===')
        if (selectedMirror) {
            console.log(`使用指定镜像源: ${selectedMirror}`)
        }
        const appRoot = getAppRoot()
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const { DependencyService } = await import('../services/dependencyService')
        const depService = new DependencyService(appRoot, mirrorService)

        const result = await depService.installDependencies((progress) => {
            event.sender.send('v2:dependency-progress', progress)
        }, selectedMirror)

        console.log(`依赖安装结果: ${result.success ? '成功' : '失败'}`)
        return result
    })

    // ==================== 获取镜像源列表 ====================

    ipcMain.handle('v2:get-mirrors', async (event, type: string) => {
        console.log(`=== V2 获取镜像源列表: ${type} ===`)
        const initService = getInitService()
        const mirrorService = initService.getMirrorService()

        const mirrors = mirrorService.getMirrors(type as any)
        return mirrors
    })

    // ==================== 完整初始化流程（保留用于兼容） ====================

    ipcMain.handle('v2:initialize', async (event, targetBranch: string = 'dev', startBackend: boolean = true) => {
        console.log('=== V2 初始化开始 ===')
        console.log(`目标分支: ${targetBranch}`)
        console.log(`启动后端: ${startBackend}`)

        const initService = getInitService(targetBranch)

        const result = await initService.initialize((progress) => {
            // 发送进度到渲染进程
            event.sender.send('v2:initialization-progress', progress)
        }, startBackend)

        if (result.success) {
            // 保存后端服务实例
            backendService = initService.getBackendService()

            // 设置日志回调
            backendService.setLogCallback((log) => {
                event.sender.send('v2:backend-log', log)
            })

            // 设置状态回调
            backendService.setStatusCallback((status) => {
                event.sender.send('v2:backend-status', status)
            })
        }

        console.log('=== V2 初始化完成 ===')
        console.log(`结果: ${result.success ? '成功' : '失败'}`)
        if (!result.success) {
            console.error(`错误: ${result.error}`)
            console.error(`失败阶段: ${result.failedStage}`)
        }
        console.log(`完成阶段: ${result.completedStages.join(', ')}`)

        return result
    })

    // ==================== 仅更新模式 ====================

    ipcMain.handle('v2:update-only', async (event, targetBranch: string = 'dev') => {
        console.log('=== V2 仅更新模式 ===')
        console.log(`目标分支: ${targetBranch}`)

        const initService = getInitService(targetBranch)

        const result = await initService.updateOnly((progress) => {
            event.sender.send('v2:initialization-progress', progress)
        })

        console.log('=== V2 更新完成 ===')
        console.log(`结果: ${result.success ? '成功' : '失败'}`)

        return result
    })

    // ==================== 后端服务管理 ====================

    ipcMain.handle('v2:backend-start', async (event) => {
        console.log('=== V2 启动后端 ===')

        const backend = getBackendService()

        // 设置回调
        backend.setLogCallback((log) => {
            event.sender.send('v2:backend-log', log)
        })

        backend.setStatusCallback((status) => {
            event.sender.send('v2:backend-status', status)
        })

        const result = await backend.startBackend()

        console.log(`后端启动结果: ${result.success ? '成功' : '失败'}`)
        if (!result.success) {
            console.error(`错误: ${result.error}`)
        }

        return result
    })

    ipcMain.handle('v2:backend-stop', async () => {
        console.log('=== V2 停止后端 ===')

        const backend = getBackendService()
        const result = await backend.stopBackend()

        console.log(`后端停止结果: ${result.success ? '成功' : '失败'}`)

        return result
    })

    ipcMain.handle('v2:backend-restart', async (event) => {
        console.log('=== V2 重启后端 ===')

        const backend = getBackendService()

        // 重新设置回调
        backend.setLogCallback((log) => {
            event.sender.send('v2:backend-log', log)
        })

        backend.setStatusCallback((status) => {
            event.sender.send('v2:backend-status', status)
        })

        const result = await backend.restartBackend()

        console.log(`后端重启结果: ${result.success ? '成功' : '失败'}`)

        return result
    })

    ipcMain.handle('v2:backend-status', () => {
        const backend = getBackendService()
        return backend.getStatus()
    })

    // ==================== 清理 ====================

    ipcMain.handle('v2:cleanup', async () => {
        console.log('=== V2 清理资源 ===')

        if (backendService) {
            await backendService.cleanup()
            backendService = null
        }

        initService = null

        console.log('✅ V2 资源清理完成')

        return { success: true }
    })
}

/**
 * 清理所有资源（应用退出时调用）
 */
export async function cleanupInitializationResources() {
    console.log('=== 清理初始化资源 ===')

    if (backendService) {
        await backendService.cleanup()
        backendService = null
    }

    initService = null

    console.log('✅ 初始化资源清理完成')
}
