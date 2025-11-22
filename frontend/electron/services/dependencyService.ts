/**
 * 依赖安装服务 V2
 * 重构版本 - 独立实现依赖安装
 */

import * as fs from 'fs'
import * as path from 'path'
import * as crypto from 'crypto'
import { spawn } from 'child_process'
import { MirrorServiceV2, MirrorSource } from './mirrorService'
import { MirrorRotationService, NetworkOperationCallback, NetworkOperationProgress } from './mirrorRotationService'

// ==================== 类型定义 ====================

export interface DependencyCheckResult {
    requirementsExists: boolean
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
    private pythonExe: string
    private requirementsPath: string
    private hashFilePath: string
    private mirrorService: MirrorServiceV2
    private rotationService: MirrorRotationService

    constructor(appRoot: string, mirrorService: MirrorServiceV2) {
        this.appRoot = appRoot
        this.pythonExe = path.join(appRoot, 'environment', 'python', 'python.exe')
        this.requirementsPath = path.join(appRoot, 'requirements.txt')
        this.hashFilePath = path.join(appRoot, 'environment', '.requirements_hash')
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
            // 第一步：环境检查
            onProgress?.({
                stage: 'check',
                progress: 0,
                message: '正在检查依赖状态...',
                details: {}
            })
            const checkResult = await this.checkDependencies()

            // 上报检查结果
            onProgress?.({
                stage: 'check',
                progress: 50,
                message: '依赖检查完成',
                details: {
                    checkInfo: checkResult
                }
            })

            if (!forceInstall && !checkResult.needsInstall) {
                console.log('✅ 依赖已是最新版本，跳过安装')
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

            console.log('依赖检查结果:', checkResult)

            // 第二步：安装依赖
            // 不在这里发送 progress: 0，避免进度条跳回0
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

            // 保存当前哈希值
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
            console.error('依赖安装失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 检查依赖状态
     */
    private async checkDependencies(): Promise<DependencyCheckResult> {
        console.log('=== 检查依赖状态 ===')

        // 检查 requirements.txt 是否存在
        if (!fs.existsSync(this.requirementsPath)) {
            console.log('requirements.txt 不存在')
            return { requirementsExists: false, needsInstall: false }
        }

        // 计算当前哈希
        const currentHash = this.calculateHash()
        console.log(`当前哈希: ${currentHash.substring(0, 8)}...`)

        // 读取上次安装的哈希
        const lastHash = this.loadHash()
        console.log(`上次哈希: ${lastHash ? lastHash.substring(0, 8) + '...' : 'null'}`)

        // 判断是否需要安装
        const needsInstall = lastHash === null || currentHash !== lastHash

        return {
            requirementsExists: true,
            needsInstall,
            currentHash,
            lastHash: lastHash || undefined
        }
    }

    /**
     * 计算 requirements.txt 的哈希值
     */
    private calculateHash(): string {
        const content = fs.readFileSync(this.requirementsPath, 'utf-8')
        return crypto.createHash('sha256').update(content.trim()).digest('hex')
    }

    /**
     * 加载上次安装的哈希值
     */
    private loadHash(): string | null {
        try {
            if (!fs.existsSync(this.hashFilePath)) {
                return null
            }
            return fs.readFileSync(this.hashFilePath, 'utf-8').trim()
        } catch (error) {
            console.warn('读取哈希文件失败:', error)
            return null
        }
    }

    /**
     * 保存哈希值
     */
    private saveHash(hash: string): void {
        try {
            const dir = path.dirname(this.hashFilePath)
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true })
            }
            fs.writeFileSync(this.hashFilePath, hash, 'utf-8')
            console.log('✅ 哈希值已保存')
        } catch (error) {
            console.warn('保存哈希文件失败:', error)
        }
    }

    /**
     * 执行依赖安装
     */
    private async performInstall(
        onProgress?: (progress: NetworkOperationProgress, mirrorName: string, mirrorIndex: number, totalMirrors: number) => void,
        selectedMirror?: string
    ): Promise<{ success: boolean; error?: string }> {
        const mirrors = this.mirrorService.getMirrors('pip_mirror')

        // 定义依赖安装操作
        const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
            try {
                // 1. 检查并安装基础工具
                onOpProgress({ progress: 20, description: '检查基础工具...' })
                await this.ensureBasicTools(mirror)

                // 2. 安装依赖
                onOpProgress({ progress: 40, description: '安装依赖包...' })
                await this.installRequirements(mirror, (progress) => {
                    onOpProgress({ progress, description: '安装依赖包...' })
                })

                onOpProgress({ progress: 100, description: '安装完成' })
                return { success: true }
            } catch (error) {
                const errorMsg = error instanceof Error ? error.message : String(error)
                return { success: false, error: errorMsg }
            }
        }

        // 使用镜像源轮替
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

        console.log(`✅ 依赖安装完成，使用镜像源: ${result.usedMirror?.name}`)
        return { success: true }
    }

    /**
     * 确保基础工具已安装（setuptools, wheel）
     */
    private async ensureBasicTools(mirror: MirrorSource): Promise<void> {
        console.log('=== 检查基础工具 ===')

        // 检查 setuptools 和 wheel 是否已安装
        const toolsInstalled = await this.checkBasicTools()

        if (toolsInstalled) {
            console.log('✅ 基础工具已安装')
            return
        }

        console.log('正在安装基础工具...')

        await new Promise<void>((resolve, reject) => {
            const hostname = new URL(mirror.url).hostname

            const proc = spawn(this.pythonExe, [
                '-m',
                'pip',
                'install',
                '--upgrade',
                'setuptools',
                'wheel',
                '-i',
                mirror.url,
                '--trusted-host',
                hostname
            ], {
                cwd: this.appRoot,
                stdio: 'pipe'
            })

            proc.stdout?.on('data', (data) => {
                console.log('setuptools/wheel:', data.toString().trim())
            })

            proc.stderr?.on('data', (data) => {
                console.log('setuptools/wheel error:', data.toString().trim())
            })

            proc.on('close', (code) => {
                if (code === 0) {
                    console.log('✅ 基础工具安装完成')
                    resolve()
                } else {
                    // 即使失败也继续，因为可能已经存在
                    console.log('⚠️ 基础工具安装失败，但继续')
                    resolve()
                }
            })

            proc.on('error', (error) => {
                console.warn('基础工具安装进程错误:', error)
                resolve()
            })
        })
    }

    /**
     * 检查基础工具是否已安装
     */
    private checkBasicTools(): Promise<boolean> {
        return new Promise((resolve) => {
            const proc = spawn(this.pythonExe, ['-m', 'pip', 'list'], {
                cwd: this.appRoot,
                stdio: 'pipe'
            })

            let output = ''
            proc.stdout?.on('data', (data) => {
                output += data.toString()
            })

            proc.on('close', (code) => {
                if (code === 0) {
                    const hasSetuptools = output.includes('setuptools')
                    const hasWheel = output.includes('wheel')
                    resolve(hasSetuptools && hasWheel)
                } else {
                    resolve(false)
                }
            })

            proc.on('error', () => {
                resolve(false)
            })
        })
    }

    /**
     * 安装 requirements.txt 中的依赖
     */
    private installRequirements(mirror: MirrorSource, onProgress?: (progress: number) => void): Promise<void> {
        return new Promise((resolve, reject) => {
            const hostname = new URL(mirror.url).hostname

            const proc = spawn(this.pythonExe, [
                '-m',
                'pip',
                'install',
                '-r',
                this.requirementsPath,
                '-i',
                mirror.url,
                '--trusted-host',
                hostname,
                '--no-warn-script-location'
            ], {
                cwd: this.appRoot,
                stdio: 'pipe'
            })

            let stdoutData = ''
            let stderrData = ''
            let totalPackages = 0
            let installedPackages = 0

            proc.stdout?.on('data', (data) => {
                const output = data.toString().trim()
                stdoutData += output
                console.log('pip install:', output)

                // 解析pip输出，统计安装进度
                // 匹配 "Collecting xxx" 来统计总包数
                const collectingMatches = output.match(/Collecting\s+\S+/g)
                if (collectingMatches) {
                    totalPackages += collectingMatches.length
                }

                // 匹配 "Installing collected packages:" 或 "Successfully installed" 来统计已安装包数
                const installingMatch = output.match(/Installing collected packages:/)
                if (installingMatch) {
                    // 开始安装阶段
                    installedPackages = Math.floor(totalPackages * 0.8) // 假设收集完成后进度到80%
                    if (onProgress) {
                        const progress = 40 + (installedPackages / Math.max(totalPackages, 1)) * 50 // 40% - 90%
                        onProgress(Math.min(progress, 90))
                    }
                }

                const successMatch = output.match(/Successfully installed/)
                if (successMatch) {
                    installedPackages = totalPackages
                    if (onProgress) {
                        onProgress(95) // 安装完成，进度到95%
                    }
                }
            })

            proc.stderr?.on('data', (data) => {
                const output = data.toString().trim()
                stderrData += output
                console.log('pip install error:', output)
            })

            proc.on('close', (code) => {
                console.log(`pip install 退出码: ${code}`)

                // 检查是否有实际错误
                const hasActualError =
                    stderrData.toLowerCase().includes('error:') ||
                    stderrData.toLowerCase().includes('failed') ||
                    stderrData.toLowerCase().includes('could not find')

                // 检查是否成功安装
                const hasSuccess =
                    stdoutData.toLowerCase().includes('successfully installed') ||
                    stdoutData.toLowerCase().includes('requirement already satisfied')

                if (code === 0 || hasSuccess || !hasActualError) {
                    console.log('✅ 依赖安装成功')
                    resolve()
                } else {
                    reject(new Error(`依赖安装失败，退出码: ${code}`))
                }
            })

            proc.on('error', reject)
        })
    }
}
