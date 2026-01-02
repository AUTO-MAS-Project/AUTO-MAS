/**
 * 环境服务 - 统一的环境管理服务
 * 包含工具函数和环境安装功能
 */

import * as path from 'path'
import * as fs from 'fs'
import { app } from 'electron'
import { spawn } from 'child_process'
import AdmZip = require('adm-zip')
import { MirrorService } from './mirrorService'
import { SmartDownloader, ProgressCallback } from './downloadService'
import { MirrorRotationService, NetworkOperationCallback } from './mirrorRotationService'

import { logService } from './logService'

// ==================== 工具函数 ====================

// 获取应用根目录
export function getAppRoot(): string {
  // 在测试环境中，app可能未定义，直接使用当前工作目录
  if (process.env.NODE_ENV === 'development' || !app) {
    return process.cwd()
  }
  return path.dirname(app.getPath('exe'))
}

// 检查环境
export function checkEnvironment(appRoot: string) {
  const environmentPath = path.join(appRoot, 'environment')
  const pythonPath = path.join(environmentPath, 'python')
  const gitPath = path.join(environmentPath, 'git')
  const backendPath = path.join(appRoot, 'backend')

  const pythonExists = fs.existsSync(pythonPath)
  const gitExists = fs.existsSync(gitPath)
  const backendExists = fs.existsSync(backendPath)

  // 检查依赖是否已安装（简单检查是否存在site-packages目录）
  const sitePackagesPath = path.join(pythonPath, 'Lib', 'site-packages')
  const dependenciesInstalled =
    fs.existsSync(sitePackagesPath) && fs.readdirSync(sitePackagesPath).length > 10

  return {
    pythonExists,
    gitExists,
    backendExists,
    dependenciesInstalled,
    isInitialized: pythonExists && gitExists && backendExists && dependenciesInstalled,
  }
}

// ==================== 类型定义 ====================

export interface EnvironmentCheckResult {
  exeExists: boolean
  canRun: boolean
  version?: string
  error?: string
}

export interface InstallProgress {
  stage: 'check' | 'download' | 'install'
  progress: number
  message: string
  details?: {
    checkInfo?: EnvironmentCheckResult
    currentMirror?: string
    mirrorProgress?: { current: number; total: number }
    downloadSpeed?: number
    downloadSize?: number
    operationDesc?: string
  }
}

export type InstallProgressCallback = (progress: InstallProgress) => void

// ==================== 环境安装基类 ====================

abstract class BaseEnvironmentInstaller {
  protected appRoot: string
  protected mirrorService: MirrorService
  protected downloader: SmartDownloader
  protected rotationService: MirrorRotationService
  protected currentOperationId: number = 0

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.mirrorService = mirrorService
    this.downloader = new SmartDownloader()
    this.rotationService = new MirrorRotationService()
  }

  /**
   * 环境安装三步走
   */
  async install(onProgress?: InstallProgressCallback, selectedMirror?: string): Promise<{ success: boolean; error?: string }> {
    try {
      // 第一步：环境检查
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: '正在检查环境...',
        details: {}
      })
      const checkResult = await this.checkEnvironment()

      // 上报检查结果
      onProgress?.({
        stage: 'check',
        progress: 50,
        message: '环境检查完成',
        details: {
          checkInfo: checkResult
        }
      })

      if (checkResult.exeExists && checkResult.canRun) {
        logService.info('环境服务', '✅ 环境已存在且可正常运行，跳过安装')
        onProgress?.({
          stage: 'check',
          progress: 100,
          message: '环境已就绪',
          details: {
            checkInfo: checkResult
          }
        })
        return { success: true }
      }

      logService.info('环境服务', `环境检查结果: ${JSON.stringify(checkResult)}`)

      // 第二步：下载安装包
      onProgress?.({
        stage: 'download',
        progress: 0,
        message: '正在下载安装包...',
        details: {}
      })
      const downloadResult = await this.downloadPackage((progress) => {
        onProgress?.({
          stage: 'download',
          progress: progress.progress,
          message: `下载中... ${progress.progress.toFixed(1)}%`,
          details: {
            downloadSpeed: progress.speed,
            downloadSize: progress.downloadedSize
          }
        })
      }, selectedMirror)

      if (!downloadResult.success) {
        return { success: false, error: downloadResult.error }
      }

      // 第三步：安装环境
      onProgress?.({
        stage: 'install',
        progress: 0,
        message: '正在安装环境...',
        details: {}
      })
      const installResult = await this.installEnvironment((progress, message, details) => {
        onProgress?.({
          stage: 'install',
          progress,
          message,
          details: details || {}
        })
      }, selectedMirror)

      if (installResult.success) {
        onProgress?.({
          stage: 'install',
          progress: 100,
          message: '安装完成',
          details: {}
        })
      }

      return installResult
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logService.error('环境服务', `环境安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  /**
   * 环境检查（抽象方法）
   */
  protected abstract checkEnvironment(): Promise<EnvironmentCheckResult>

  /**
   * 下载安装包（抽象方法）
   */
  protected abstract downloadPackage(onProgress?: ProgressCallback, selectedMirror?: string): Promise<{ success: boolean; error?: string }>

  /**
   * 安装环境（抽象方法）
   */
  protected abstract installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }>
}

// ==================== Python 环境安装器 ====================

export class PythonInstaller extends BaseEnvironmentInstaller {
  private readonly pythonPath: string
  private readonly pythonExe: string

  constructor(appRoot: string, mirrorService: MirrorService) {
    super(appRoot, mirrorService)
    this.pythonPath = path.join(appRoot, 'environment', 'python')
    this.pythonExe = path.join(this.pythonPath, 'python.exe')
  }

  protected async checkEnvironment(): Promise<EnvironmentCheckResult> {
    logService.info('环境服务', '=== 检查 Python 环境 ===')

    // 检查 exe 文件是否存在
    const exeExists = fs.existsSync(this.pythonExe)
    logService.info('环境服务', `Python 可执行文件存在: ${exeExists}`)

    if (!exeExists) {
      return { exeExists: false, canRun: false }
    }

    // 检查能否正常运行
    try {
      const version = await this.getPythonVersion()
      logService.info('环境服务', `Python 版本: ${version}`)
      return { exeExists: true, canRun: true, version }
    } catch (error) {
      logService.error('环境服务', `Python 无法正常运行: ${error}`)
      return { exeExists: true, canRun: false, error: String(error) }
    }
  }

  private getPythonVersion(): Promise<string> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.pythonExe, ['-V'], { stdio: 'pipe' })

      let output = ''
      proc.stdout?.on('data', (data) => {
        output += data.toString()
      })
      proc.stderr?.on('data', (data) => {
        output += data.toString()
      })

      proc.on('close', (code) => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          reject(new Error(`Python 版本检查失败，退出码: ${code}`))
        }
      })

      proc.on('error', reject)
    })
  }

  protected async downloadPackage(onProgress?: ProgressCallback, selectedMirror?: string): Promise<{ success: boolean; error?: string }> {
    logService.info('环境服务', '=== 下载 Python 安装包 ===')

    const mirrors = this.mirrorService.getMirrors('python')
    const tempZipPath = path.join(this.appRoot, 'temp', 'python.zip')

    // 确保临时目录存在
    const tempDir = path.dirname(tempZipPath)
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true })
    }

    // 使用镜像源轮替下载
    const downloadOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      // 为此操作分配一个新的ID
      const operationId = ++this.currentOperationId
      
      onOpProgress({ progress: 0, description: `正在从 ${mirror.name} 下载...` })

      const result = await this.downloader.download(mirror.url, tempZipPath, (progress) => {
        // 检查是否是当前活跃的操作
        if (operationId !== this.currentOperationId) {
          // 这是一个过期的进度回调，忽略它
          return
        }
        
        // 上报下载进度，包含速度和大小信息
        onProgress?.({
          progress: progress.progress,
          speed: progress.speed,
          downloadedSize: progress.downloadedSize,
          totalSize: progress.totalSize
        })
        onOpProgress({
          progress: progress.progress,
          description: `下载中... ${progress.progress.toFixed(1)}%`
        })
      })

      return result
    }

    const result = await this.rotationService.execute(mirrors, downloadOperation, undefined, selectedMirror)

    if (!result.success) {
      return { success: false, error: result.error }
    }

    logService.info('环境服务', `✅ Python 安装包下载完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }

  protected async installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logService.info('环境服务', '=== 安装 Python 环境 ===')

    const tempZipPath = path.join(this.appRoot, 'temp', 'python.zip')

    try {
      // 确保 Python 目录存在
      onProgress?.(10, '创建 Python 目录...')
      if (!fs.existsSync(this.pythonPath)) {
        fs.mkdirSync(this.pythonPath, { recursive: true })
      }

      // 解压 Python
      onProgress?.(30, '正在解压 Python...')
      logService.info('环境服务', '正在解压 Python...')
      const zip = new AdmZip(tempZipPath)
      zip.extractAllTo(this.pythonPath, true)
      logService.info('环境服务', '✅ Python 解压完成')

      // 启用 site-packages 支持
      onProgress?.(70, '配置 Python 环境...')
      const pthFile = path.join(this.pythonPath, 'python312._pth')
      if (fs.existsSync(pthFile)) {
        let content = fs.readFileSync(pthFile, 'utf-8')
        content = content.replace(/^#import site/m, 'import site')
        fs.writeFileSync(pthFile, content, 'utf-8')
        logService.info('环境服务', '✅ 已启用 site-packages 支持')
      }

      // 清理临时文件
      onProgress?.(90, '清理临时文件...')
      if (fs.existsSync(tempZipPath)) {
        fs.unlinkSync(tempZipPath)
      }

      onProgress?.(100, 'Python 安装完成')
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logService.error('环境服务', `Python 安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }
}

// ==================== Pip 安装器 ====================

export class PipInstaller extends BaseEnvironmentInstaller {
  private readonly pythonPath: string
  private readonly pythonExe: string
  private readonly pipExe: string

  constructor(appRoot: string, mirrorService: MirrorService) {
    super(appRoot, mirrorService)
    this.pythonPath = path.join(appRoot, 'environment', 'python')
    this.pythonExe = path.join(this.pythonPath, 'python.exe')
    this.pipExe = path.join(this.pythonPath, 'Scripts', 'pip.exe')
  }

  protected async checkEnvironment(): Promise<EnvironmentCheckResult> {
    logService.info('环境服务', '=== 检查 Pip 环境 ===')

    // 检查 pip.exe 是否存在
    const exeExists = fs.existsSync(this.pipExe)
    logService.info('环境服务', `Pip 可执行文件存在: ${exeExists}`)

    if (!exeExists) {
      return { exeExists: false, canRun: false }
    }

    // 检查能否正常运行
    try {
      const version = await this.getPipVersion()
      logService.info('环境服务', `Pip 版本: ${version}`)
      return { exeExists: true, canRun: true, version }
    } catch (error) {
      logService.error('环境服务', `Pip 无法正常运行: ${error}`)
      return { exeExists: true, canRun: false, error: String(error) }
    }
  }

  private getPipVersion(): Promise<string> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.pythonExe, ['-m', 'pip', '--version'], { stdio: 'pipe' })

      let output = ''
      proc.stdout?.on('data', (data) => {
        output += data.toString()
      })
      proc.stderr?.on('data', (data) => {
        output += data.toString()
      })

      proc.on('close', (code) => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          reject(new Error(`Pip 版本检查失败，退出码: ${code}`))
        }
      })

      proc.on('error', reject)
    })
  }

  protected async downloadPackage(onProgress?: ProgressCallback, selectedMirror?: string): Promise<{ success: boolean; error?: string }> {
    logService.info('环境服务', '=== 下载 get-pip.py ===')

    const mirrors = this.mirrorService.getMirrors('get_pip')
    const getPipPath = path.join(this.pythonPath, 'get-pip.py')

    // 使用镜像源轮替下载
    const downloadOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      // 为此操作分配一个新的ID
      const operationId = ++this.currentOperationId
      
      onOpProgress({ progress: 0, description: `正在从 ${mirror.name} 下载...` })

      const result = await this.downloader.download(mirror.url, getPipPath, (progress) => {
        // 检查是否是当前活跃的操作
        if (operationId !== this.currentOperationId) {
          return
        }
        
        // 上报下载进度，包含速度和大小信息
        onProgress?.({
          progress: progress.progress,
          speed: progress.speed,
          downloadedSize: progress.downloadedSize,
          totalSize: progress.totalSize
        })
        onOpProgress({
          progress: progress.progress,
          description: `下载中... ${progress.progress.toFixed(1)}%`
        })
      })

      return result
    }

    const result = await this.rotationService.execute(mirrors, downloadOperation, undefined, selectedMirror)

    if (!result.success) {
      return { success: false, error: result.error }
    }

    logService.info('环境服务', `✅ get-pip.py 下载完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }

  protected async installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logService.info('环境服务', '=== 安装 Pip ===')

    const getPipPath = path.join(this.pythonPath, 'get-pip.py')
    const mirrors = this.mirrorService.getMirrors('pip_mirror')

    // 定义pip安装操作
    const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      try {
        onOpProgress({ progress: 0, description: `使用 ${mirror.name} 安装 pip...` })

        // 执行 pip 安装，使用指定的镜像源
        await new Promise<void>((resolve, reject) => {
          const hostname = new URL(mirror.url).hostname

          const proc = spawn(this.pythonExe, [
            getPipPath,
            '-i',
            mirror.url,
            '--trusted-host',
            hostname
          ], {
            cwd: this.pythonPath,
            stdio: 'pipe'
          })

          proc.stdout?.on('data', (data) => {
            const output = data.toString().trim()
            logService.info('环境服务', `pip 安装输出: ${output}`)

            // 根据输出更新进度
            if (output.includes('Collecting')) {
              onOpProgress({ progress: 40, description: '正在下载 pip 组件...' })
            } else if (output.includes('Installing')) {
              onOpProgress({ progress: 70, description: '正在安装 pip...' })
            }
          })

          proc.stderr?.on('data', (data) => {
            logService.error('环境服务', `pip 安装错误: ${data.toString().trim()}`)
          })

          proc.on('close', (code) => {
            if (code === 0) {
              logService.info('环境服务', '✅ Pip 安装成功')
              onOpProgress({ progress: 100, description: 'Pip 安装完成' })
              resolve()
            } else {
              reject(new Error(`Pip 安装失败，退出码: ${code}`))
            }
          })

          proc.on('error', reject)
        })

        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMsg }
      }
    }

    // 使用镜像源轮替执行安装
    const result = await this.rotationService.execute(mirrors, installOperation, (rotationProgress) => {
      const totalProgress = rotationProgress.operationProgress.progress
      const message = rotationProgress.operationProgress.description
      const details = {
        currentMirror: rotationProgress.currentMirror.name,
        mirrorProgress: {
          current: rotationProgress.mirrorIndex + 1,
          total: rotationProgress.totalMirrors
        },
        operationDesc: rotationProgress.operationProgress.description
      }
      onProgress?.(totalProgress, message, details)
    }, selectedMirror)

    if (!result.success) {
      return { success: false, error: result.error }
    }

    // 清理临时文件
    logService.info('环境服务', '清理临时文件...')
    if (fs.existsSync(getPipPath)) {
      fs.unlinkSync(getPipPath)
    }

    logService.info('环境服务', `✅ Pip 安装完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }
}

// ==================== Git 安装器 ====================

export class GitInstaller extends BaseEnvironmentInstaller {
  private readonly gitPath: string
  private readonly gitExe: string

  constructor(appRoot: string, mirrorService: MirrorService) {
    super(appRoot, mirrorService)
    this.gitPath = path.join(appRoot, 'environment', 'git')
    this.gitExe = path.join(this.gitPath, 'bin', 'git.exe')
  }

  protected async checkEnvironment(): Promise<EnvironmentCheckResult> {
    logService.info('环境服务', '=== 检查 Git 环境 ===')

    // 检查 git.exe 是否存在
    const exeExists = fs.existsSync(this.gitExe)
    logService.info('环境服务', `Git 可执行文件存在: ${exeExists}`)

    if (!exeExists) {
      return { exeExists: false, canRun: false }
    }

    // 检查能否正常运行
    try {
      const version = await this.getGitVersion()
      logService.info('环境服务', `Git 版本: ${version}`)
      return { exeExists: true, canRun: true, version }
    } catch (error) {
      logService.error('环境服务', `Git 无法正常运行: ${error}`)
      return { exeExists: true, canRun: false, error: String(error) }
    }
  }

  private getGitVersion(): Promise<string> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.gitExe, ['-v'], { stdio: 'pipe' })

      let output = ''
      proc.stdout?.on('data', (data) => {
        output += data.toString()
      })
      proc.stderr?.on('data', (data) => {
        output += data.toString()
      })

      proc.on('close', (code) => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          reject(new Error(`Git 版本检查失败，退出码: ${code}`))
        }
      })

      proc.on('error', reject)
    })
  }

  protected async downloadPackage(onProgress?: ProgressCallback, selectedMirror?: string): Promise<{ success: boolean; error?: string }> {
    logService.info('环境服务', '=== 下载 Git 安装包 ===')

    const mirrors = this.mirrorService.getMirrors('git')
    const tempZipPath = path.join(this.appRoot, 'temp', 'git.zip')

    // 确保临时目录存在
    const tempDir = path.dirname(tempZipPath)
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true })
    }

    // 使用镜像源轮替下载
    const downloadOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      // 为此操作分配一个新的ID
      const operationId = ++this.currentOperationId
      
      onOpProgress({ progress: 0, description: `正在从 ${mirror.name} 下载...` })

      const result = await this.downloader.download(mirror.url, tempZipPath, (progress) => {
        // 检查是否是当前活跃的操作
        if (operationId !== this.currentOperationId) {
          return
        }
        
        // 上报下载进度，包含速度和大小信息
        onProgress?.({
          progress: progress.progress,
          speed: progress.speed,
          downloadedSize: progress.downloadedSize,
          totalSize: progress.totalSize
        })
        onOpProgress({
          progress: progress.progress,
          description: `下载中... ${progress.progress.toFixed(1)}%`
        })
      })

      return result
    }

    const result = await this.rotationService.execute(mirrors, downloadOperation, undefined, selectedMirror)

    if (!result.success) {
      return { success: false, error: result.error }
    }

    logService.info('环境服务', `✅ Git 安装包下载完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }

  protected async installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logService.info('环境服务', '=== 安装 Git 环境 ===')

    const tempZipPath = path.join(this.appRoot, 'temp', 'git.zip')

    try {
      // 创建临时解压目录
      onProgress?.(10, '创建临时目录...')
      const tempExtractPath = path.join(this.appRoot, 'temp', 'git_extract')
      if (!fs.existsSync(tempExtractPath)) {
        fs.mkdirSync(tempExtractPath, { recursive: true })
      }

      // 解压到临时目录
      onProgress?.(30, '正在解压 Git...')
      logService.info('环境服务', '正在解压 Git...')
      const zip = new AdmZip(tempZipPath)
      zip.extractAllTo(tempExtractPath, true)

      // 检查解压后的目录结构
      onProgress?.(50, '检查目录结构...')
      const extractedItems = fs.readdirSync(tempExtractPath)
      let sourceDir = tempExtractPath

      // 如果解压后有 git 子目录，使用该目录
      if (extractedItems.length === 1 && extractedItems[0] === 'git') {
        sourceDir = path.join(tempExtractPath, 'git')
      }

      // 确保目标 Git 目录存在
      if (!fs.existsSync(this.gitPath)) {
        fs.mkdirSync(this.gitPath, { recursive: true })
      }

      // 移动文件到最终目录
      onProgress?.(60, '移动文件到目标目录...')
      const sourceContents = fs.readdirSync(sourceDir)
      const totalItems = sourceContents.length

      for (let i = 0; i < sourceContents.length; i++) {
        const item = sourceContents[i]
        const sourcePath = path.join(sourceDir, item)
        const targetPath = path.join(this.gitPath, item)

        // 如果目标已存在，先删除
        if (fs.existsSync(targetPath)) {
          if (fs.statSync(targetPath).isDirectory()) {
            fs.rmSync(targetPath, { recursive: true, force: true })
          } else {
            fs.unlinkSync(targetPath)
          }
        }

        // 移动文件或目录
        fs.renameSync(sourcePath, targetPath)

        // 更新进度
        const itemProgress = 60 + Math.floor((i + 1) / totalItems * 20)
        onProgress?.(itemProgress, `移动文件 ${i + 1}/${totalItems}...`)
      }

      logService.info('环境服务', '✅ Git 解压完成')

      // 清理临时文件
      onProgress?.(90, '清理临时文件...')
      if (fs.existsSync(tempZipPath)) {
        fs.unlinkSync(tempZipPath)
      }
      if (fs.existsSync(tempExtractPath)) {
        fs.rmSync(tempExtractPath, { recursive: true, force: true })
      }

      onProgress?.(100, 'Git 安装完成')
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logService.error('环境服务', `Git 安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }
}
