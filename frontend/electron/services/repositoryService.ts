/**
 * 源码拉取服务
 * 重构版本 - 独立实现仓库拉取和部署
 */

import * as fs from 'fs'
import * as path from 'path'
import { spawn } from 'child_process'
import { MirrorService, MirrorSource } from './mirrorService'
import { MirrorRotationService, NetworkOperationCallback, NetworkOperationProgress } from './mirrorRotationService'

// 导入日志服务
import { logService } from './logService'

// 使用日志服务的日志记录器
const logger = {
    error: (message: string, ...args: any[]) => logService.error('仓库服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    warn: (message: string, ...args: any[]) => logService.warn('仓库服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    info: (message: string, ...args: any[]) => logService.info('仓库服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    debug: (message: string, ...args: any[]) => logService.debug('仓库服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`),
    log: (message: string, ...args: any[]) => logService.info('仓库服务', `${message} ${args.length > 0 ? JSON.stringify(args) : ''}`)
}

// ==================== 类型定义 ====================

export interface RepositoryCheckResult {
    exists: boolean
    isGitRepo: boolean
    isHealthy: boolean
    currentBranch?: string
}

export interface RepositoryProgress {
    stage: 'check' | 'pull' | 'deploy'
    progress: number
    message: string
    details?: {
        checkInfo?: RepositoryCheckResult
        currentMirror?: string
        mirrorProgress?: { current: number; total: number }
        operationDesc?: string
    }
}

export type RepositoryProgressCallback = (progress: RepositoryProgress) => void

// ==================== 仓库服务类 ====================

export class RepositoryService {
    private appRoot: string
    private repoPath: string
    private gitExe: string
    private mirrorService: MirrorService
    private rotationService: MirrorRotationService
    private targetBranch: string

    constructor(appRoot: string, mirrorService: MirrorService, targetBranch: string = 'dev') {
        this.appRoot = appRoot
        this.repoPath = path.join(appRoot, 'repo')
        this.gitExe = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
        this.mirrorService = mirrorService
        this.rotationService = new MirrorRotationService()
        this.targetBranch = targetBranch
    }

    /**
     * 源码拉取方法
     */
    async pullRepository(onProgress?: RepositoryProgressCallback, selectedMirror?: string): Promise<{ success: boolean; error?: string }> {
        try {
            // 第一步：环境检查
            onProgress?.({
                stage: 'check',
                progress: 0,
                message: '正在检查本地仓库...',
                details: {}
            })
            const checkResult = await this.checkRepository()
            logger.info('仓库检查结果:', checkResult)

            // 上报检查结果
            onProgress?.({
                stage: 'check',
                progress: 100,
                message: checkResult.exists ? '本地仓库已存在' : '本地仓库不存在',
                details: {
                    checkInfo: checkResult
                }
            })

            // 第二步：拉取仓库
            onProgress?.({
                stage: 'pull',
                progress: 0,
                message: '正在拉取仓库...',
                details: {}
            })
            const pullResult = await this.pullOrCloneRepository(checkResult, (opProgress, mirrorName, mirrorIndex, totalMirrors) => {
                onProgress?.({
                    stage: 'pull',
                    progress: opProgress.progress,
                    message: opProgress.description,
                    details: {
                        currentMirror: mirrorName,
                        mirrorProgress: { current: mirrorIndex + 1, total: totalMirrors },
                        operationDesc: opProgress.description
                    }
                })
            }, selectedMirror)

            if (!pullResult.success) {
                return { success: false, error: pullResult.error }
            }

            // 第三步：部署仓库
            onProgress?.({
                stage: 'deploy',
                progress: 0,
                message: '正在部署仓库...',
                details: {}
            })
            const deployResult = await this.deployRepository((progress, message) => {
                onProgress?.({
                    stage: 'deploy',
                    progress,
                    message,
                    details: {}
                })
            })

            if (deployResult.success) {
                onProgress?.({
                    stage: 'deploy',
                    progress: 100,
                    message: '部署完成',
                    details: {}
                })
            }

            return deployResult
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('源码拉取失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 检查本地仓库状态
     */
    private async checkRepository(): Promise<RepositoryCheckResult> {
        logger.info('=== 检查本地仓库 ===')

        // 检查 repo 文件夹是否存在
        if (!fs.existsSync(this.repoPath)) {
            logger.info('repo 文件夹不存在')
            return { exists: false, isGitRepo: false, isHealthy: false }
        }

        // 检查是否为 Git 仓库
        const gitDir = path.join(this.repoPath, '.git')
        if (!fs.existsSync(gitDir)) {
            logger.info('repo 文件夹存在但不是 Git 仓库')
            // 清理无效的 repo 文件夹
            fs.rmSync(this.repoPath, { recursive: true, force: true })
            return { exists: false, isGitRepo: false, isHealthy: false }
        }

        // 检查 Git 仓库健康状态
        try {
            const isHealthy = await this.checkGitHealth()
            const currentBranch = await this.getCurrentBranch()

            if (isHealthy) {
                logger.info(`✅ 本地仓库健康，当前分支: ${currentBranch}`)
                return { exists: true, isGitRepo: true, isHealthy: true, currentBranch }
            } else {
                logger.warn('⚠️ 本地仓库存在问题，需要清理')
                // 清理有问题的仓库
                fs.rmSync(this.repoPath, { recursive: true, force: true })
                return { exists: false, isGitRepo: false, isHealthy: false }
            }
        } catch (error) {
            logger.error('检查仓库健康状态失败:', error)
            // 清理有问题的仓库
            fs.rmSync(this.repoPath, { recursive: true, force: true })
            return { exists: false, isGitRepo: false, isHealthy: false }
        }
    }

    /**
     * 检查 Git 仓库健康状态
     */
    private checkGitHealth(): Promise<boolean> {
        return new Promise((resolve) => {
            const proc = spawn(this.gitExe, ['status'], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })

            proc.on('close', (code) => {
                resolve(code === 0)
            })

            proc.on('error', () => {
                resolve(false)
            })
        })
    }

    /**
     * 获取当前分支
     */
    private getCurrentBranch(): Promise<string> {
        return new Promise((resolve, reject) => {
            const proc = spawn(this.gitExe, ['branch', '--show-current'], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })

            let output = ''
            proc.stdout?.on('data', (data) => {
                output += data.toString()
            })

            proc.on('close', (code) => {
                if (code === 0) {
                    resolve(output.trim() || 'unknown')
                } else {
                    reject(new Error('获取当前分支失败'))
                }
            })

            proc.on('error', reject)
        })
    }

    /**
     * 拉取或克隆仓库
     */
    private async pullOrCloneRepository(
        checkResult: RepositoryCheckResult,
        onProgress?: (progress: NetworkOperationProgress, mirrorName: string, mirrorIndex: number, totalMirrors: number) => void,
        selectedMirror?: string
    ): Promise<{ success: boolean; error?: string }> {
        const mirrors = this.mirrorService.getMirrors('repo')

        // 定义仓库拉取操作
        const repoOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
            if (checkResult.exists && checkResult.isGitRepo && checkResult.isHealthy) {
                // 本地仓库已存在，执行更新
                return await this.updateExistingRepository(mirror, onOpProgress)
            } else {
                // 本地仓库不存在，执行克隆
                return await this.cloneNewRepository(mirror, onOpProgress)
            }
        }

        // 使用镜像源轮替
        const result = await this.rotationService.execute(mirrors, repoOperation, (rotationProgress) => {
            onProgress?.(
                rotationProgress.operationProgress,
                rotationProgress.currentMirror.name,
                rotationProgress.mirrorIndex,
                rotationProgress.totalMirrors
            )
        }, selectedMirror)

        if (!result.success) {
            return { success: false, error: result.error }
        }

        logger.info(`✅ 仓库拉取完成，使用镜像源: ${result.usedMirror?.name}`)
        return { success: true }
    }

    /**
     * 更新现有仓库
     */
    private async updateExistingRepository(
        mirror: MirrorSource,
        onProgress: (progress: NetworkOperationProgress) => void
    ): Promise<{ success: boolean; error?: string }> {
        logger.info('=== 更新现有仓库 ===')

        try {
            // 1. 确认目标分支是否存在
            onProgress({ progress: 10, description: '检查目标分支...' })
            const branchExists = await this.checkRemoteBranch(mirror.url, this.targetBranch)

            if (!branchExists) {
                return { success: false, error: `目标分支 ${this.targetBranch} 不存在` }
            }

            // 2. 配置远程仓库 URL
            onProgress({ progress: 30, description: '配置远程仓库...' })
            await this.configureRemote(mirror.url)

            // 3. 配置浅克隆
            onProgress({ progress: 50, description: '配置浅克隆...' })
            await this.configureShallowClone()

            // 4. 拉取最新提交
            onProgress({ progress: 70, description: '拉取最新代码...' })
            await this.fetchLatestCommit()

            // 5. 切换到目标分支
            onProgress({ progress: 90, description: '切换分支...' })
            await this.checkoutBranch()

            onProgress({ progress: 100, description: '拉取完成' })
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('更新仓库失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 克隆新仓库
     */
    private async cloneNewRepository(
        mirror: MirrorSource,
        onProgress: (progress: NetworkOperationProgress) => void
    ): Promise<{ success: boolean; error?: string }> {
        logger.info('=== 克隆新仓库 ===')

        try {
            // 1. 确认目标分支是否存在
            onProgress({ progress: 10, description: '检查目标分支...' })
            const branchExists = await this.checkRemoteBranch(mirror.url, this.targetBranch)

            if (!branchExists) {
                return { success: false, error: `目标分支 ${this.targetBranch} 不存在` }
            }

            // 2. 克隆指定分支的最新提交
            onProgress({ progress: 30, description: '克隆仓库...' })
            await this.cloneRepository(mirror.url)

            onProgress({ progress: 100, description: '克隆完成' })
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('克隆仓库失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 检查远程分支是否存在
     */
    private checkRemoteBranch(repoUrl: string, branch: string): Promise<boolean> {
        return new Promise((resolve) => {
            const proc = spawn(this.gitExe, ['ls-remote', '--heads', repoUrl, branch], {
                stdio: 'pipe'
            })

            // 设置 30 秒超时
            const timeout = setTimeout(() => {
                logger.warn('⚠️ 检查远程分支超时，终止进程')
                proc.kill()
                resolve(false)
            }, 30000)

            let output = ''
            proc.stdout?.on('data', (data) => {
                output += data.toString()
            })

            proc.on('close', (code) => {
                clearTimeout(timeout)
                if (code === 0) {
                    const exists = output.includes(`refs/heads/${branch}`)
                    resolve(exists)
                } else {
                    resolve(false)
                }
            })

            proc.on('error', () => {
                clearTimeout(timeout)
                resolve(false)
            })
        })
    }

    /**
     * 配置远程仓库
     */
    private configureRemote(repoUrl: string): Promise<void> {
        return new Promise((resolve, reject) => {
            const proc = spawn(this.gitExe, ['remote', 'set-url', 'origin', repoUrl], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })

            proc.on('close', (code) => {
                if (code === 0) {
                    logger.info('✅ 远程仓库配置完成')
                    resolve()
                } else {
                    reject(new Error('配置远程仓库失败'))
                }
            })

            proc.on('error', reject)
        })
    }

    /**
     * 配置浅克隆
     */
    private async configureShallowClone(): Promise<void> {
        // 清除现有的 fetch 配置
        await new Promise<void>((resolve) => {
            const proc = spawn(this.gitExe, ['config', '--unset-all', 'remote.origin.fetch'], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })
            proc.on('close', () => resolve())
            proc.on('error', () => resolve())
        })

        // 设置只拉取目标分支
        await new Promise<void>((resolve, reject) => {
            const refspec = `+refs/heads/${this.targetBranch}:refs/remotes/origin/${this.targetBranch}`
            const proc = spawn(this.gitExe, ['config', '--add', 'remote.origin.fetch', refspec], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })

            proc.on('close', (code) => {
                if (code === 0) {
                    logger.info('✅ 浅克隆配置完成')
                    resolve()
                } else {
                    reject(new Error('配置浅克隆失败'))
                }
            })

            proc.on('error', reject)
        })
    }

    /**
     * 拉取最新提交
     */
    private fetchLatestCommit(): Promise<void> {
        return new Promise((resolve, reject) => {
            const proc = spawn(this.gitExe, [
                'fetch',
                'origin',
                this.targetBranch,
                '--depth=1',
                '--no-tags'
            ], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })

            // 设置 60 秒超时（fetch 可能需要更长时间）
            const timeout = setTimeout(() => {
                logger.warn('⚠️ 拉取最新提交超时，终止进程')
                proc.kill()
                reject(new Error('拉取最新提交超时'))
            }, 60000)

            proc.stdout?.on('data', (data) => {
                logger.info('fetch:', data.toString().trim())
            })

            proc.on('close', (code) => {
                clearTimeout(timeout)
                if (code === 0) {
                    logger.info('✅ 拉取最新提交完成')
                    resolve()
                } else {
                    reject(new Error('拉取最新提交失败'))
                }
            })

            proc.on('error', (error) => {
                clearTimeout(timeout)
                reject(error)
            })
        })
    }

    /**
     * 切换分支
     */
    private checkoutBranch(): Promise<void> {
        return new Promise((resolve, reject) => {
            const proc = spawn(this.gitExe, ['checkout', '-B', this.targetBranch, `origin/${this.targetBranch}`], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })

            proc.on('close', (code) => {
                if (code === 0) {
                    logger.info('✅ 切换分支完成')
                    resolve()
                } else {
                    reject(new Error('切换分支失败'))
                }
            })

            proc.on('error', reject)
        })
    }

    /**
     * 克隆仓库
     */
    private cloneRepository(repoUrl: string): Promise<void> {
        return new Promise((resolve, reject) => {
            // 确保 repo 目录不存在
            if (fs.existsSync(this.repoPath)) {
                fs.rmSync(this.repoPath, { recursive: true, force: true })
            }

            const proc = spawn(this.gitExe, [
                'clone',
                '--single-branch',
                '--depth=1',
                '--branch',
                this.targetBranch,
                repoUrl,
                this.repoPath
            ], {
                stdio: 'pipe'
            })

            // 设置 120 秒超时（clone 可能需要较长时间）
            const timeout = setTimeout(() => {
                logger.warn('⚠️ 克隆仓库超时，终止进程')
                proc.kill()
                reject(new Error('克隆仓库超时'))
            }, 120000)

            proc.stdout?.on('data', (data) => {
                logger.info('clone:', data.toString().trim())
            })

            proc.on('close', (code) => {
                clearTimeout(timeout)
                if (code === 0) {
                    logger.info('✅ 克隆仓库完成')
                    resolve()
                } else {
                    reject(new Error('克隆仓库失败'))
                }
            })

            proc.on('error', (error) => {
                clearTimeout(timeout)
                reject(error)
            })
        })
    }

    /**
     * 部署仓库
     */
    private async deployRepository(onProgress?: (progress: number, message: string) => void): Promise<{ success: boolean; error?: string }> {
        logger.info('=== 部署仓库 ===')

        try {
            // 1. 优化仓库存储
            onProgress?.(30, '优化仓库存储...')
            logger.info('优化仓库存储...')
            await this.optimizeStorage()

            // 2. 复制到根目录
            onProgress?.(60, '复制文件到根目录...')
            logger.info('复制文件到根目录...')
            await this.copyToRoot()

            onProgress?.(100, '部署完成')
            logger.info('✅ 仓库部署完成')
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error('部署仓库失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 优化仓库存储
     */
    private async optimizeStorage(): Promise<void> {
        // 删除 reflog
        await new Promise<void>((resolve) => {
            const proc = spawn(this.gitExe, ['reflog', 'expire', '--expire=now', '--all'], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })
            proc.on('close', () => {
                logger.info('✅ reflog 清理完成')
                resolve()
            })
            proc.on('error', () => resolve())
        })

        // 垃圾回收
        await new Promise<void>((resolve) => {
            const proc = spawn(this.gitExe, ['gc', '--aggressive', '--prune=now'], {
                cwd: this.repoPath,
                stdio: 'pipe'
            })
            proc.on('close', () => {
                logger.info('✅ 垃圾回收完成')
                resolve()
            })
            proc.on('error', () => resolve())
        })
    }

    /**
     * 复制文件到根目录
     */
    private async copyToRoot(): Promise<void> {
        const itemsToCopy = ['.git', 'app', 'res', 'main.py', 'requirements.txt', 'LICENSE', 'README.md']

        for (const item of itemsToCopy) {
            const srcPath = path.join(this.repoPath, item)
            const dstPath = path.join(this.appRoot, item)

            if (!fs.existsSync(srcPath)) {
                logger.warn(`⚠️ 源文件不存在，跳过: ${item}`)
                continue
            }

            try {
                // 删除目标文件/目录
                if (fs.existsSync(dstPath)) {
                    if (fs.statSync(dstPath).isDirectory()) {
                        fs.rmSync(dstPath, { recursive: true, force: true })
                    } else {
                        fs.unlinkSync(dstPath)
                    }
                }

                // 复制文件/目录
                if (fs.statSync(srcPath).isDirectory()) {
                    this.copyDirectory(srcPath, dstPath)
                } else {
                    fs.copyFileSync(srcPath, dstPath)
                }

                logger.info(`✅ 复制完成: ${item}`)
            } catch (error) {
                logger.error(`❌ 复制失败: ${item}`, error)
                throw error
            }
        }
    }

    /**
     * 递归复制目录
     */
    private copyDirectory(src: string, dest: string): void {
        if (!fs.existsSync(dest)) {
            fs.mkdirSync(dest, { recursive: true })
        }

        const entries = fs.readdirSync(src, { withFileTypes: true })
        for (const entry of entries) {
            const srcPath = path.join(src, entry.name)
            const destPath = path.join(dest, entry.name)

            if (entry.isDirectory()) {
                this.copyDirectory(srcPath, destPath)
            } else {
                fs.copyFileSync(srcPath, destPath)
            }
        }
    }
}
