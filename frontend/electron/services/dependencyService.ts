/**
 * 依赖安装服务
 * 使用 uv 从 pyproject.toml 或 requirements.txt 安装依赖到 .venv
 */

import * as fs from 'fs'
import * as path from 'path'
import * as crypto from 'crypto'
import { spawn } from 'child_process'
import { MirrorService, MirrorSource } from './mirrorService'
import {
  MirrorRotationService,
  NetworkOperationCallback,
  NetworkOperationProgress,
} from './mirrorRotationService'

import { getLogger } from './logger'
const logger = getLogger('后端依赖安装服务')

// ==================== 类型定义 ====================

type DependencySource = 'pyproject' | 'requirements' | 'missing'

export interface DependencyCheckResult {
  pyprojectExists: boolean
  requirementsExists: boolean
  source: DependencySource
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
  private venvPath: string
  private venvPythonExe: string
  private pyprojectPath: string
  private requirementsPath: string
  private hashFilePath: string
  private mirrorService: MirrorService
  private rotationService: MirrorRotationService

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.uvExe = path.join(appRoot, 'environment', 'python', 'Scripts', 'uv.exe')
    this.pythonExe = path.join(appRoot, 'environment', 'python', 'python.exe')
    this.venvPath = path.join(appRoot, '.venv')
    this.venvPythonExe = path.join(this.venvPath, 'Scripts', 'python.exe')
    this.pyprojectPath = path.join(appRoot, 'pyproject.toml')
    this.requirementsPath = path.join(appRoot, 'requirements.txt')
    this.hashFilePath = path.join(appRoot, 'environment', '.dependency_hash')
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
        details: {},
      })
      const checkResult = await this.checkDependencies()

      onProgress?.({
        stage: 'check',
        progress: 50,
        message: '依赖检查完成',
        details: {
          checkInfo: checkResult,
        },
      })

      if (!forceInstall && !checkResult.needsInstall) {
        logger.info('依赖已是最新版本，跳过安装')
        onProgress?.({
          stage: 'check',
          progress: 100,
          message: '依赖已是最新',
          details: {
            checkInfo: checkResult,
          },
        })
        return { success: true, skipped: true }
      }

      logger.info(`依赖检查结果: ${JSON.stringify(checkResult)}`)

      const installResult = await this.performInstall(
        checkResult,
        (opProgress, mirrorName, mirrorIndex, totalMirrors) => {
          onProgress?.({
            stage: 'install',
            progress: opProgress.progress,
            message: opProgress.description,
            details: {
              currentMirror: mirrorName,
              mirrorProgress: { current: mirrorIndex + 1, total: totalMirrors },
              operationDesc: opProgress.description,
            },
          })
        },
        selectedMirror
      )

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
        details: {},
      })
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`依赖安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  /**
   * 检查依赖状态（基于 pyproject.toml 或 requirements.txt 哈希）
   */
  private async checkDependencies(): Promise<DependencyCheckResult> {
    logger.info('=== 检查依赖状态 ===')

    const pyprojectExists = fs.existsSync(this.pyprojectPath)
    const requirementsExists = fs.existsSync(this.requirementsPath)
    const source: DependencySource = pyprojectExists
      ? 'pyproject'
      : requirementsExists
        ? 'requirements'
        : 'missing'

    if (source === 'missing') {
      logger.info('pyproject.toml 和 requirements.txt 均不存在')
      return { pyprojectExists, requirementsExists, source, needsInstall: false }
    }

    logger.info(`依赖来源: ${source}`)

    const currentHash = this.calculateHash(source)
    logger.info(`当前哈希: ${currentHash.substring(0, 8)}...`)

    const lastHash = this.loadHash()
    logger.info(`上次哈希: ${lastHash ? lastHash.substring(0, 8) + '...' : 'null'}`)

    const venvReady = this.isVenvReady()
    const needsInstall = !venvReady || lastHash === null || currentHash !== lastHash

    return {
      pyprojectExists,
      requirementsExists,
      source,
      needsInstall,
      currentHash,
      lastHash: lastHash || undefined,
    }
  }

  /**
   * 计算依赖声明文件的哈希值
   */
  private calculateHash(source: Exclude<DependencySource, 'missing'>): string {
    const sourcePath = source === 'pyproject' ? this.pyprojectPath : this.requirementsPath
    const content = fs.readFileSync(sourcePath, 'utf-8')
    return crypto.createHash('sha256').update(`${source}\n${content.trim()}`).digest('hex')
  }

  private isVenvReady(): boolean {
    if (!fs.existsSync(this.venvPythonExe)) {
      return false
    }

    if (!this.ensureVenvPythonPathConfig()) {
      return false
    }

    const sitePackagesPath = path.join(this.venvPath, 'Lib', 'site-packages')
    return fs.existsSync(sitePackagesPath) && fs.readdirSync(sitePackagesPath).length > 0
  }

  private ensureVenvPythonPathConfig(): boolean {
    try {
      const sourceDir = path.dirname(this.pythonExe)
      const sourceName = fs.readdirSync(sourceDir).find(name => /^python\d+._pth$/i.test(name))

      if (!sourceName) {
        return true
      }

      const sourcePath = path.join(sourceDir, sourceName)
      const targetPath = path.join(path.dirname(this.venvPythonExe), sourceName)
      const sourceContent = fs.readFileSync(sourcePath, 'utf-8')
      const targetContent = fs.existsSync(targetPath) ? fs.readFileSync(targetPath, 'utf-8') : null

      if (targetContent !== sourceContent) {
        fs.copyFileSync(sourcePath, targetPath)
        logger.info(`已同步虚拟环境 Python 路径配置: ${targetPath}`)
      }

      return true
    } catch (error) {
      logger.warn(`同步虚拟环境 Python 路径配置失败: ${error}`)
      return false
    }
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
    checkResult: DependencyCheckResult,
    onProgress?: (
      progress: NetworkOperationProgress,
      mirrorName: string,
      mirrorIndex: number,
      totalMirrors: number
    ) => void,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    const mirrors = this.mirrorService.getMirrors('pip_mirror')
    const source = checkResult.source

    const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      try {
        onOpProgress({ progress: 20, description: '检查 uv 可用性...' })
        await this.ensureUvReady()

        if (source === 'pyproject') {
          onOpProgress({ progress: 40, description: '正在同步依赖 (uv sync)...' })
          await this.runUvSync(mirror, progress => {
            onOpProgress({ progress, description: '正在同步依赖...' })
          })
        } else if (source === 'requirements') {
          onOpProgress({ progress: 40, description: '正在安装 requirements.txt 依赖...' })
          await this.runRequirementsInstall(mirror, progress => {
            onOpProgress({ progress, description: '正在安装 requirements.txt 依赖...' })
          })
        } else {
          throw new Error('pyproject.toml 和 requirements.txt 均不存在，无法安装后端依赖')
        }

        if (!this.isVenvReady()) {
          throw new Error(`后端虚拟环境创建失败: ${this.venvPath}`)
        }

        onOpProgress({ progress: 100, description: '安装完成' })
        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMsg }
      }
    }

    const result = await this.rotationService.execute(
      mirrors,
      installOperation,
      rotationProgress => {
        onProgress?.(
          rotationProgress.operationProgress,
          rotationProgress.currentMirror.name,
          rotationProgress.mirrorIndex,
          rotationProgress.totalMirrors
        )
      },
      selectedMirror
    )

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

    if (!fs.existsSync(this.pythonExe)) {
      throw new Error(`Python 可执行文件不存在: ${this.pythonExe}`)
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

      const proc = spawn(
        this.uvExe,
        ['sync', '--python', this.pythonExe, '--no-install-project', '--no-dev'],
        {
          cwd: this.appRoot,
          stdio: 'pipe',
          env,
        }
      )

      let stderrData = ''

      proc.stdout?.on('data', data => {
        const output = data.toString().trim()
        logger.info(`uv sync: ${output}`)
      })

      proc.stderr?.on('data', data => {
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

      proc.on('close', code => {
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

  /**
   * 使用 requirements.txt 创建/更新 .venv。
   */
  private async runRequirementsInstall(
    mirror: MirrorSource,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    if (!fs.existsSync(this.venvPythonExe)) {
      onProgress?.(50)
      await this.runUvVenv(mirror)
    } else {
      logger.info(`虚拟环境已存在: ${this.venvPath}`)
      onProgress?.(55)
    }

    await this.runUvPipInstall(mirror, onProgress)
  }

  private runUvVenv(mirror: MirrorSource): Promise<void> {
    return new Promise((resolve, reject) => {
      const env = {
        ...process.env,
        UV_INDEX_URL: mirror.url,
      }

      const proc = spawn(this.uvExe, ['venv', this.venvPath, '--python', this.pythonExe], {
        cwd: this.appRoot,
        stdio: 'pipe',
        env,
      })

      let stderrData = ''

      proc.stdout?.on('data', data => {
        const output = data.toString().trim()
        logger.info(`uv venv: ${output}`)
      })

      proc.stderr?.on('data', data => {
        const output = data.toString().trim()
        stderrData += output
        logger.info(`uv venv stderr: ${output}`)
      })

      proc.on('close', code => {
        logger.info(`uv venv 退出码: ${code}`)

        if (code === 0) {
          logger.info('uv venv 成功')
          resolve()
        } else {
          reject(new Error(`uv venv 失败，退出码: ${code}\nstderr: ${stderrData}`))
        }
      })

      proc.on('error', reject)
    })
  }

  private runUvPipInstall(
    mirror: MirrorSource,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const env = {
        ...process.env,
        UV_INDEX_URL: mirror.url,
      }

      const proc = spawn(
        this.uvExe,
        ['pip', 'install', '--python', this.venvPythonExe, '-r', this.requirementsPath],
        {
          cwd: this.appRoot,
          stdio: 'pipe',
          env,
        }
      )

      let stderrData = ''

      const handleOutput = (prefix: string, data: Buffer) => {
        const output = data.toString().trim()
        logger.info(`${prefix}: ${output}`)

        if (output.includes('Resolved')) {
          onProgress?.(65)
        } else if (output.includes('Prepared') || output.includes('Downloading')) {
          onProgress?.(80)
        } else if (output.includes('Installed') || output.includes('installed')) {
          onProgress?.(95)
        }
      }

      proc.stdout?.on('data', data => {
        handleOutput('uv pip install', data)
      })

      proc.stderr?.on('data', data => {
        stderrData += data.toString().trim()
        handleOutput('uv pip install stderr', data)
      })

      proc.on('close', code => {
        logger.info(`uv pip install 退出码: ${code}`)

        if (code === 0) {
          logger.info('uv pip install 成功')
          resolve()
        } else {
          reject(new Error(`uv pip install 失败，退出码: ${code}\nstderr: ${stderrData}`))
        }
      })

      proc.on('error', reject)
    })
  }
}
