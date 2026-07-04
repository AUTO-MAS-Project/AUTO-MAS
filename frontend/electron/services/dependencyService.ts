/**
 * 依赖安装服务
 * 使用 uv sync 从 pyproject.toml 安装依赖到 .venv
 */

import * as fs from 'fs'
import * as path from 'path'
import * as crypto from 'crypto'
import { spawn } from 'child_process'
import { MirrorService, MirrorSource } from './mirrorService'
import { MirrorRotationService, NetworkOperationCallback, NetworkOperationProgress } from './mirrorRotationService'

import { getLogger } from './logger'
const logger = getLogger('后端依赖安装服务')

// ==================== 类型定义 ====================

export interface DependencyCheckResult {
    pyprojectExists: boolean
    needsInstall: boolean
    currentHash?: string
    lastHash?: string
}

export interface DependencyProgress {
    stage: 'check' | 'install'
    progress: number
    message: string
    details?: {
        checkInfo?: DependencyCheckResult
        currentMirror?: string
        mirrorProgress?: { current: number; total: number }
        operationDesc?: string
    }
}

export type DependencyProgressCallback = (progress: DependencyProgress) => void

// ==================== 依赖安装服务类 ====================

export class DependencyService {
    private appRoot: string
    private uvExe: string
    private pythonExe: string
    private pyprojectPath: string
    private hashFilePath: string
    private mirrorService: MirrorService
    private rotationService: MirrorRotationService

    constructor(appRoot: string, mirrorService: MirrorService) {
        this.appRoot = appRoot
        this.uvExe = path.join(appRoot, 'environment', 'python', 'Scripts', 'uv.exe')
        this.pythonExe = path.join(appRoot, 'environment', 'python', 'python.exe')
        this.pyprojectPath = path.join(appRoot, 'pyproject.toml')
        this.hashFilePath = path.join(appRoot, 'environment', '.pyproject_hash')
        this.mirrorService = mirrorService
        this.rotationService = new MirrorRotationService()
    }

    /**
     * 依赖安装方法
     */
    async installDependencies(
        onProgress?: DependencyProgressCallback,
        selectedMirror?: string,
        forceInstall: boolean = false
    ): Promise<{ success: boolean; error?: string; skipped?: boolean }> {
        try {
            onProgress?.({
                stage: 'check',
                progress: 0,
                message: '正在检查依赖状态...',
                details: {}
            })
            const checkResult = await this.checkDependencies()

            onProgress?.({
                stage: 'check',
                progress: 50,
                message: '依赖检查完成',
                details: {
                    checkInfo: checkResult
                }
            })

            if (!forceInstall && !checkResult.needsInstall) {
                logger.info('依赖已是最新版本，跳过安装')
                onProgress?.({
                    stage: 'check',
                    progress: 100,
                    message: '依赖已是最新',
                    details: {
                        checkInfo: checkResult
                    }
                })
                return { success: true, skipped: true }
            }

            logger.info(`依赖检查结果: ${JSON.stringify(checkResult)}`)

            const installResult = await this.performInstall((opProgress, mirrorName, mirrorIndex, totalMirrors) => {
                onProgress?.({
                    stage: 'install',
                    progress: opProgress.progress,
                    message: opProgress.description,
                    details: {
                        currentMirror: mirrorName,
                        mirrorProgress: { current: mirrorIndex + 1, total: totalMirrors },
                        operationDesc: opProgress.description
                    }
                })
            }, selectedMirror)

            if (!installResult.success) {
                return { success: false, error: installResult.error }
            }

            if (checkResult.currentHash) {
                this.saveHash(checkResult.currentHash)
            }

            onProgress?.({
                stage: 'install',
                progress: 100,
                message: '依赖安装完成',
                details: {}
            })
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`依赖安装失败: ${errorMsg}`)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 检查依赖状态（基于 pyproject.toml 哈希）
     */
    private async checkDependencies(): Promise<DependencyCheckResult> {
        logger.info('=== 检查依赖状态 ===')

        if (!fs.existsSync(this.pyprojectPath)) {
            logger.info('pyproject.toml 不存在')
            return { pyprojectExists: false, needsInstall: false }
        }

        const currentHash = this.calculateHash()
        logger.info(`当前哈希: ${currentHash.substring(0, 8)}...`)

        const lastHash = this.loadHash()
        logger.info(`上次哈希: ${lastHash ? lastHash.substring(0, 8) + '...' : 'null'}`)

        const venvExists = fs.existsSync(path.join(this.appRoot, '.venv'))
        const needsInstall = !venvExists || lastHash === null || currentHash !== lastHash

        return {
            pyprojectExists: true,
            needsInstall,
            currentHash,
            lastHash: lastHash || undefined
        }
    }

    /**
     * 计算 pyproject.toml 的哈希值
     */
    private calculateHash(): string {
        const content = fs.readFileSync(this.pyprojectPath, 'utf-8')
        return crypto.createHash('sha256').update(content.trim()).digest('hex')
    }

    private loadHash(): string | null {
        try {
            if (!fs.existsSync(this.hashFilePath)) {
                return null
            }
            return fs.readFileSync(this.hashFilePath, 'utf-8').trim()
        } catch (error) {
            logger.warn(`读取哈希文件失败: ${error}`)
            return null
        }
    }

    private saveHash(hash: string): void {
        try {
            const dir = path.dirname(this.hashFilePath)
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true })
            }
            fs.writeFileSync(this.hashFilePath, hash, 'utf-8')
            logger.info('哈希值已保存')
        } catch (error) {
            logger.warn(`保存哈希文件失败: ${error}`)
        }
    }

    /**
     * 执行依赖安装（uv sync）
     */
    private async performInstall(
        onProgress?: (progress: NetworkOperationProgress, mirrorName: string, mirrorIndex: number, totalMirrors: number) => void,
        selectedMirror?: string
    ): Promise<{ success: boolean; error?: string }> {
        const mirrors = this.mirrorService.getMirrors('pip_mirror')

        const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
            try {
                onOpProgress({ progress: 20, description: '检查 uv 可用性...' })
                await this.ensureUvReady()

                onOpProgress({ progress: 40, description: '正在同步依赖 (uv sync)...' })
                await this.runUvSync(mirror, (progress) => {
                    onOpProgress({ progress, description: '正在同步依赖...' })
                })

                onOpProgress({ progress: 100, description: '安装完成' })
                return { success: true }
            } catch (error) {
                const errorMsg = error instanceof Error ? error.message : String(error)
                return { success: false, error: errorMsg }
            }
        }

        const result = await this.rotationService.execute(mirrors, installOperation, (rotationProgress) => {
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

        logger.info(`依赖安装完成，使用镜像源: ${result.usedMirror?.name}`)
        return { success: true }
    }

    private async ensureUvReady(): Promise<void> {
        if (!fs.existsSync(this.uvExe)) {
            throw new Error('uv.exe 不存在，请先完成环境初始化')
        }
    }

    /**
     * 执行 uv sync 从 pyproject.toml 安装依赖
     * 通过 UV_INDEX_URL 环境变量传递镜像源
     */
    private runUvSync(mirror: MirrorSource, onProgress?: (progress: number) => void): Promise<void> {
        return new Promise((resolve, reject) => {
            const env = {
                ...process.env,
                UV_INDEX_URL: mirror.url,
            }

            const proc = spawn(this.uvExe, [
                'sync',
                '--python', this.pythonExe,
                '--no-install-project',
            ], {
                cwd: this.appRoot,
                stdio: 'pipe',
                env,
            })

            let stdoutData = ''
            let stderrData = ''

            proc.stdout?.on('data', (data) => {
                const output = data.toString().trim()
                stdoutData += output
                logger.info(`uv sync: ${output}`)
            })

            proc.stderr?.on('data', (data) => {
                const output = data.toString().trim()
                stderrData += output
                logger.info(`uv sync stderr: ${output}`)

                if (output.includes('Resolved')) {
                    onProgress?.(60)
                } else if (output.includes('Prepared') || output.includes('Downloading')) {
                    onProgress?.(75)
                } else if (output.includes('Installed') || output.includes('installed')) {
                    onProgress?.(95)
                }
            })

            proc.on('close', (code) => {
                logger.info(`uv sync 退出码: ${code}`)

                if (code === 0) {
                    logger.info('uv sync 成功')
                    resolve()
                } else {
                    reject(new Error(`uv sync 失败，退出码: ${code}\nstderr: ${stderrData}`))
                }
            })

            proc.on('error', reject)
        })
    }
}
