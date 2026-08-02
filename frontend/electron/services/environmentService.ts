/**
 * 环境服务 - 统一的环境管理服务
 * 包含工具函数和环境安装功能
 */

import * as path from 'path'
import * as fs from 'fs'
import { app } from 'electron'
import { spawn } from 'child_process'
import { createHash } from 'crypto'
import AdmZip = require('adm-zip')
import { MirrorService } from './mirrorService'
import { SmartDownloader, DownloadProgress, ProgressCallback } from './downloadService'
import { MirrorRotationService, NetworkOperationCallback } from './mirrorRotationService'
import {
  assertCompleteUvBinarySet,
  createUvChecksumUrls,
  deployUvBinaries,
  isUvVersionExact,
  isUvVersionSupported,
  mergeUvMirrors,
  UV_ARCHIVE_NAME,
  UV_BINARY_NAMES,
  UV_FALLBACK_SHA256,
  UV_FALLBACK_VERSION,
  UV_GITHUB_LATEST_API_URL,
  UV_LATEST_METADATA_URL,
} from './uvDistribution'

import { getLogger } from './logger'
const logger = getLogger('环境服务')
const UV_METADATA_TIMEOUT_MS = 8000
const UV_METADATA_MAX_BYTES = 1024 * 1024
const UV_VERSION_CHECK_TIMEOUT_MS = 10000
const UV_DOWNLOAD_OPTIONS = {
  idleTimeoutMs: 30000,
  overallTimeoutMs: 5 * 60 * 1000,
  maxRedirects: 5,
  maxBytes: 128 * 1024 * 1024,
} as const

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

  // 检查依赖是否已安装（检查 .venv 是否存在且非空）
  const venvPath = path.join(appRoot, '.venv')
  const venvSitePackages = path.join(venvPath, 'Lib', 'site-packages')
  const dependenciesInstalled =
    fs.existsSync(venvSitePackages) && fs.readdirSync(venvSitePackages).length > 10

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

interface UvReleaseCandidate {
  version: string
  sha256: string
}

export type InstallProgressCallback = (progress: InstallProgress) => void

interface UvInstallFlight {
  listeners: Set<InstallProgressCallback>
  selectedMirror?: string
  promise: Promise<{ success: boolean; error?: string }>
}

const uvInstallFlights = new Map<string, UvInstallFlight>()

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
  async install(
    onProgress?: InstallProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    try {
      // 第一步：环境检查
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: '正在检查环境...',
        details: {},
      })
      const checkResult = await this.checkEnvironment()

      // 上报检查结果
      onProgress?.({
        stage: 'check',
        progress: 50,
        message: '环境检查完成',
        details: {
          checkInfo: checkResult,
        },
      })

      if (checkResult.exeExists && checkResult.canRun) {
        logger.info('环境已存在且可正常运行，跳过安装')
        onProgress?.({
          stage: 'check',
          progress: 100,
          message: '环境已就绪',
          details: {
            checkInfo: checkResult,
          },
        })
        return { success: true }
      }

      logger.info(`环境检查结果: ${JSON.stringify(checkResult)}`)

      // 第二步：下载安装包
      onProgress?.({
        stage: 'download',
        progress: 0,
        message: '正在下载安装包...',
        details: {},
      })
      const downloadResult = await this.downloadPackage(progress => {
        onProgress?.({
          stage: 'download',
          progress: progress.progress,
          message: `下载中... ${progress.progress.toFixed(1)}%`,
          details: this.getDownloadProgressDetails(progress),
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
        details: {},
      })
      const installResult = await this.installEnvironment((progress, message, details) => {
        onProgress?.({
          stage: 'install',
          progress,
          message,
          details: details || {},
        })
      }, selectedMirror)

      if (installResult.success) {
        onProgress?.({
          stage: 'install',
          progress: 100,
          message: '安装完成',
          details: {},
        })
      }

      return installResult
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`环境安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  protected getDownloadProgressDetails(progress: DownloadProgress): InstallProgress['details'] {
    return {
      downloadSpeed: progress.speed,
      downloadSize: progress.downloadedSize,
    }
  }

  /**
   * 环境检查（抽象方法）
   */
  protected abstract checkEnvironment(): Promise<EnvironmentCheckResult>

  /**
   * 下载安装包（抽象方法）
   */
  protected abstract downloadPackage(
    onProgress?: ProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }>

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
    logger.info('=== 检查 Python 环境 ===')

    // 检查 exe 文件是否存在
    const exeExists = fs.existsSync(this.pythonExe)
    logger.info(`Python 可执行文件存在: ${exeExists}`)

    if (!exeExists) {
      return { exeExists: false, canRun: false }
    }

    // 检查能否正常运行
    try {
      const version = await this.getPythonVersion()
      logger.info(`Python 版本: ${version}`)
      return { exeExists: true, canRun: true, version }
    } catch (error) {
      logger.error(`Python 无法正常运行: ${error}`)
      return { exeExists: true, canRun: false, error: String(error) }
    }
  }

  private getPythonVersion(): Promise<string> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.pythonExe, ['-V'], { stdio: 'pipe' })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })
      proc.stderr?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          reject(new Error(`Python 版本检查失败，退出码: ${code}`))
        }
      })

      proc.on('error', reject)
    })
  }

  protected async downloadPackage(
    onProgress?: ProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 下载 Python 安装包 ===')

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

      const result = await this.downloader.download(mirror.url, tempZipPath, progress => {
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
          totalSize: progress.totalSize,
        })
        onOpProgress({
          progress: progress.progress,
          description: `下载中... ${progress.progress.toFixed(1)}%`,
        })
      })

      return result
    }

    const result = await this.rotationService.execute(
      mirrors,
      downloadOperation,
      undefined,
      selectedMirror
    )

    if (!result.success) {
      return { success: false, error: result.error }
    }

    logger.info(`Python 安装包下载完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }

  protected async installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    _selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 安装 Python 环境 ===')

    const tempZipPath = path.join(this.appRoot, 'temp', 'python.zip')

    try {
      // 确保 Python 目录存在
      onProgress?.(10, '创建 Python 目录...')
      if (!fs.existsSync(this.pythonPath)) {
        fs.mkdirSync(this.pythonPath, { recursive: true })
      }

      // 解压 Python
      onProgress?.(30, '正在解压 Python...')
      logger.info('正在解压 Python...')
      const zip = new AdmZip(tempZipPath)
      zip.extractAllTo(this.pythonPath, true)
      logger.info('Python 解压完成')

      // 启用 site-packages 支持
      onProgress?.(70, '配置 Python 环境...')
      const pthFile = path.join(this.pythonPath, 'python312._pth')
      if (fs.existsSync(pthFile)) {
        let content = fs.readFileSync(pthFile, 'utf-8')
        content = content.replace(/^#import site/m, 'import site')
        fs.writeFileSync(pthFile, content, 'utf-8')
        logger.info('已启用 site-packages 支持')
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
      logger.error(`Python 安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }
}

// ==================== uv 安装器（替代 Pip） ====================

export class UvInstaller extends BaseEnvironmentInstaller {
  private readonly pythonPath: string
  private readonly uvExe: string
  private uvVersion = UV_FALLBACK_VERSION
  private uvArchiveSha256 = UV_FALLBACK_SHA256
  private currentMirrorName = ''
  private currentMirrorIndex = 0
  private currentMirrorTotal = 0

  private get uvArchivePath(): string {
    return path.join(this.appRoot, 'temp', `uv-${this.uvVersion}-${UV_ARCHIVE_NAME}`)
  }

  constructor(appRoot: string, mirrorService: MirrorService) {
    super(appRoot, mirrorService)
    this.pythonPath = path.join(appRoot, 'environment', 'python')
    this.uvExe = path.join(appRoot, 'environment', 'python', 'Scripts', 'uv.exe')
  }

  override install(
    onProgress?: InstallProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    const installKey = path.resolve(this.appRoot)
    const currentFlight = uvInstallFlights.get(installKey)
    if (currentFlight) {
      if (onProgress) currentFlight.listeners.add(onProgress)
      if (selectedMirror && selectedMirror !== currentFlight.selectedMirror) {
        logger.warn(
          `uv 安装已在进行，忽略后续镜像选择 ${selectedMirror}，继续使用 ${
            currentFlight.selectedMirror || '自动轮换'
          }`
        )
      }
      return currentFlight.promise
    }

    const listeners = new Set<InstallProgressCallback>()
    if (onProgress) listeners.add(onProgress)
    const flight = {} as UvInstallFlight
    const promise = super
      .install(progress => {
        for (const listener of listeners) {
          try {
            listener(progress)
          } catch (error) {
            logger.warn(`转发 uv 安装进度失败: ${error}`)
          }
        }
      }, selectedMirror)
      .finally(() => {
        if (uvInstallFlights.get(installKey) === flight) {
          uvInstallFlights.delete(installKey)
        }
      })

    Object.assign(flight, { listeners, selectedMirror, promise })
    uvInstallFlights.set(installKey, flight)
    return promise
  }

  protected async checkEnvironment(): Promise<EnvironmentCheckResult> {
    logger.info('=== 检查 uv 环境 ===')

    const exeExists = fs.existsSync(this.uvExe)
    logger.info(`uv 可执行文件存在: ${exeExists}`)

    if (!exeExists) {
      return { exeExists: false, canRun: false }
    }

    try {
      const version = await this.getUvVersion()
      logger.info(`uv 版本: ${version}`)
      const canRun = isUvVersionSupported(version)
      return {
        exeExists: true,
        canRun,
        version,
        error: canRun ? undefined : `需要 uv ${UV_FALLBACK_VERSION} 或更高版本，当前为 ${version}`,
      }
    } catch (error) {
      logger.error(`uv 无法正常运行: ${error}`)
      return { exeExists: true, canRun: false, error: String(error) }
    }
  }

  private getUvVersion(executablePath: string = this.uvExe): Promise<string> {
    const resolvedExecutable = path.resolve(executablePath)
    const resolvedInstalledUv = path.resolve(this.uvExe)
    const resolvedTempRoot = `${path.resolve(this.appRoot, 'temp')}${path.sep}`

    if (
      resolvedExecutable !== resolvedInstalledUv &&
      !resolvedExecutable.startsWith(resolvedTempRoot)
    ) {
      return Promise.reject(new Error(`拒绝执行非托管 uv 路径: ${resolvedExecutable}`))
    }

    return new Promise((resolve, reject) => {
      const proc = spawn(resolvedExecutable, ['--version'], { stdio: 'pipe' })

      let output = ''
      let settled = false
      const finish = (error?: Error): void => {
        if (settled) return
        settled = true
        clearTimeout(timeout)
        if (error) {
          reject(error)
        } else {
          resolve(output.trim())
        }
      }
      const timeout = setTimeout(() => {
        proc.kill()
        finish(new Error(`uv 版本检查超过 ${UV_VERSION_CHECK_TIMEOUT_MS / 1000} 秒`))
      }, UV_VERSION_CHECK_TIMEOUT_MS)

      proc.stdout?.on('data', data => {
        output += data.toString()
      })
      proc.stderr?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0) {
          finish()
        } else {
          finish(new Error(`uv 版本检查失败，退出码: ${code}`))
        }
      })

      proc.on('error', error => finish(error))
    })
  }

  protected getDownloadProgressDetails(progress: DownloadProgress): InstallProgress['details'] {
    return {
      ...super.getDownloadProgressDetails(progress),
      currentMirror: this.currentMirrorName,
      mirrorProgress:
        this.currentMirrorTotal > 0
          ? { current: this.currentMirrorIndex, total: this.currentMirrorTotal }
          : undefined,
      operationDesc: this.currentMirrorName
        ? `正在从 ${this.currentMirrorName} 下载 uv ${this.uvVersion}`
        : undefined,
    }
  }

  protected async downloadPackage(
    onProgress?: ProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    const latestRelease = await this.resolveUvLatestRelease()
    const fallbackRelease: UvReleaseCandidate = {
      version: UV_FALLBACK_VERSION,
      sha256: UV_FALLBACK_SHA256,
    }
    const candidates =
      latestRelease &&
      (latestRelease.version !== fallbackRelease.version ||
        latestRelease.sha256 !== fallbackRelease.sha256)
        ? [latestRelease, fallbackRelease]
        : [fallbackRelease]
    const failures: string[] = []

    for (const candidate of candidates) {
      this.uvVersion = candidate.version
      this.uvArchiveSha256 = candidate.sha256

      const result = await this.downloadUvRelease(onProgress, selectedMirror)
      if (result.success) {
        return result
      }

      failures.push(`uv ${candidate.version}: ${result.error || '下载失败'}`)
      if (candidate !== candidates.at(-1)) {
        logger.warn(`uv ${candidate.version} 下载失败，回退到 ${UV_FALLBACK_VERSION}`)
      }
    }

    return {
      success: false,
      error: `uv 最新版和回退版本均下载失败：${failures.join('；')}`,
    }
  }

  private async downloadUvRelease(
    onProgress?: ProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logger.info(`=== 下载 uv ${this.uvVersion} ===`)

    const allMirrors = mergeUvMirrors(this.uvVersion, this.mirrorService.getMirrors('uv'))
    const mirrors = selectedMirror
      ? allMirrors.filter(mirror => mirror.key === selectedMirror || mirror.name === selectedMirror)
      : allMirrors

    if (mirrors.length === 0) {
      return {
        success: false,
        error: selectedMirror
          ? `未找到指定的 uv 下载源: ${selectedMirror}`
          : '没有可用的 uv 下载源',
      }
    }

    this.ensureUvTempDirectory()

    this.currentMirrorTotal = mirrors.length
    const failures: string[] = []

    for (let index = 0; index < mirrors.length; index++) {
      const mirror = mirrors[index]
      this.currentMirrorName = mirror.name
      this.currentMirrorIndex = index + 1

      this.cleanupUvArchive()

      logger.info(`尝试 uv 下载源 [${index + 1}/${mirrors.length}]: ${mirror.name}`)
      onProgress?.({
        progress: 0.1,
        speed: 0,
        downloadedSize: 0,
        totalSize: 0,
      })

      const result = await this.downloader.download(
        mirror.url,
        this.uvArchivePath,
        progress => {
          onProgress?.({
            ...progress,
            progress: Math.min(progress.progress * 0.9, 90),
          })
        },
        UV_DOWNLOAD_OPTIONS
      )

      if (!result.success) {
        const reason = result.error || '下载失败'
        failures.push(`${mirror.name}: ${reason}`)
        logger.warn(`uv 下载源 ${mirror.name} 失败: ${reason}`)
        continue
      }

      try {
        const archiveSize = fs.statSync(this.uvArchivePath).size
        onProgress?.({
          progress: 95,
          speed: 0,
          downloadedSize: archiveSize,
          totalSize: archiveSize,
        })

        const actualSha256 = await this.calculateSha256(this.uvArchivePath)
        if (actualSha256 !== this.uvArchiveSha256) {
          throw new Error(`SHA256 不匹配，实际值: ${actualSha256}`)
        }

        onProgress?.({
          progress: 99,
          speed: 0,
          downloadedSize: archiveSize,
          totalSize: archiveSize,
        })
        logger.info(`uv 下载完成并通过 SHA256 校验，使用来源: ${mirror.name}`)
        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        failures.push(`${mirror.name}: ${errorMsg}`)
        logger.warn(`uv 下载源 ${mirror.name} 校验失败: ${errorMsg}`)
      }
    }

    this.cleanupUvArchive()

    return {
      success: false,
      error: `所有 uv 下载源均失败：${failures.join('；')}`,
    }
  }

  protected async installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    _selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 安装 uv ===')

    const scriptsDir = path.join(this.pythonPath, 'Scripts')
    const stageDir = path.join(
      this.appRoot,
      'temp',
      `uv-stage-${process.pid}-${Date.now().toString(36)}`
    )

    try {
      if (!fs.existsSync(scriptsDir)) {
        fs.mkdirSync(scriptsDir, { recursive: true })
      }
      fs.mkdirSync(stageDir, { recursive: true })

      onProgress?.(20, '正在解压 uv...')
      const zip = new AdmZip(this.uvArchivePath)
      const archiveEntries = zip.getEntries()
      assertCompleteUvBinarySet(
        archiveEntries
          .filter(entry => !entry.isDirectory)
          .map(entry => path.basename(entry.entryName))
      )
      const extractedBinaries: string[] = []

      for (const binaryName of UV_BINARY_NAMES) {
        const entry = archiveEntries.find(
          item =>
            !item.isDirectory &&
            path.basename(item.entryName).toLowerCase() === binaryName.toLowerCase()
        )

        if (!entry) {
          throw new Error(`uv ZIP 中缺少必需文件: ${binaryName}`)
        }

        const stagedPath = path.join(stageDir, binaryName)
        fs.writeFileSync(stagedPath, entry.getData())
        extractedBinaries.push(binaryName)
      }

      const stagedUvExe = path.join(stageDir, 'uv.exe')
      onProgress?.(55, '正在验证 uv 版本...')
      const stagedVersion = await this.getUvVersion(stagedUvExe)
      if (!isUvVersionExact(stagedVersion, this.uvVersion)) {
        throw new Error(`uv 版本不匹配，期望 ${this.uvVersion}，实际 ${stagedVersion}`)
      }

      onProgress?.(75, '正在部署 uv...')
      await deployUvBinaries(stageDir, scriptsDir, extractedBinaries, async () => {
        onProgress?.(90, '验证 uv 安装...')
        const installedVersion = await this.getUvVersion()
        if (!isUvVersionExact(installedVersion, this.uvVersion)) {
          throw new Error(`uv 安装后版本不匹配，期望 ${this.uvVersion}，实际 ${installedVersion}`)
        }
      })

      onProgress?.(100, 'uv 安装完成')
      logger.info(`uv ${this.uvVersion} 安装完成，来源: ${this.currentMirrorName}`)
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`uv 安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    } finally {
      try {
        if (fs.existsSync(stageDir)) {
          fs.rmSync(stageDir, { recursive: true, force: true })
        }
      } catch (error) {
        logger.warn(`清理 uv 暂存目录失败: ${error}`)
      }
      this.cleanupUvArchive()
    }
  }

  private cleanupUvArchive(): void {
    try {
      if (fs.existsSync(this.uvArchivePath)) {
        fs.unlinkSync(this.uvArchivePath)
      }
    } catch (error) {
      logger.warn(`清理 uv 下载归档失败: ${error}`)
    }
  }

  private ensureUvTempDirectory(): void {
    const tempDir = path.dirname(this.uvArchivePath)
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true })
    }
  }

  private async resolveUvLatestRelease(): Promise<UvReleaseCandidate | null> {
    try {
      const metadata = JSON.parse(await this.fetchUvText(UV_LATEST_METADATA_URL)) as {
        tag?: unknown
      }
      const version = this.normalizeUvVersion(metadata.tag)
      if (!isUvVersionSupported(`uv ${version}`)) {
        throw new Error(`版本 ${version} 低于最低要求 ${UV_FALLBACK_VERSION}`)
      }
      const sha256 = await this.resolveUvChecksum(version)

      logger.info(`已从 uv-custom 元数据解析最新 uv: ${version}`)
      return { version, sha256 }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`uv-custom 最新版本元数据不可用: ${errorMsg}`)
    }

    try {
      const release = JSON.parse(await this.fetchUvText(UV_GITHUB_LATEST_API_URL)) as {
        tag_name?: unknown
        assets?: Array<{ name?: unknown; digest?: unknown }>
      }
      const version = this.normalizeUvVersion(release.tag_name)
      if (!isUvVersionSupported(`uv ${version}`)) {
        throw new Error(`版本 ${version} 低于最低要求 ${UV_FALLBACK_VERSION}`)
      }
      const asset = release.assets?.find(item => item.name === UV_ARCHIVE_NAME)
      const digest =
        typeof asset?.digest === 'string'
          ? asset.digest.match(/^sha256:([a-f0-9]{64})$/i)?.[1]?.toLowerCase()
          : undefined
      const sha256 = digest || (await this.resolveUvChecksum(version))

      logger.info(`已从 GitHub API 解析最新 uv: ${version}`)
      return { version, sha256 }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`GitHub 最新版本元数据不可用: ${errorMsg}`)
    }

    logger.warn(`无法解析 uv 最新版本，回退到已验证版本 ${UV_FALLBACK_VERSION}`)
    return null
  }

  private async resolveUvChecksum(version: string): Promise<string> {
    const failures: string[] = []

    for (const url of createUvChecksumUrls(version)) {
      try {
        const checksum = await this.fetchUvText(url)
        const match = checksum.trim().match(/^([a-f0-9]{64})\s+\*?(.+?)\s*$/i)

        if (!match || path.basename(match[2]) !== UV_ARCHIVE_NAME) {
          throw new Error('checksum 格式无效')
        }

        logger.info(`已从官方来源获取 uv ${version} SHA256: ${url}`)
        return match[1].toLowerCase()
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        failures.push(`${url}: ${errorMsg}`)
      }
    }

    throw new Error(`所有 uv 官方 checksum 来源均失败：${failures.join('；')}`)
  }

  private normalizeUvVersion(value: unknown): string {
    if (typeof value !== 'string') {
      throw new Error('版本号不存在')
    }

    const version = value.trim().replace(/^v/, '')
    if (!/^\d+\.\d+\.\d+$/.test(version)) {
      throw new Error(`版本号格式无效: ${value}`)
    }

    return version
  }

  private async fetchUvText(url: string): Promise<string> {
    const response = await fetch(url, {
      headers: {
        Accept: 'application/json, text/plain, */*',
        'User-Agent': 'AUTO-MAS',
      },
      redirect: 'follow',
      signal: AbortSignal.timeout(UV_METADATA_TIMEOUT_MS),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const contentLength = Number(response.headers.get('content-length') || '0')
    if (contentLength > UV_METADATA_MAX_BYTES) {
      throw new Error('响应内容过大')
    }

    const text = await response.text()
    if (Buffer.byteLength(text, 'utf8') > UV_METADATA_MAX_BYTES) {
      throw new Error('响应内容过大')
    }

    return text
  }

  private calculateSha256(filePath: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const hash = createHash('sha256')
      const stream = fs.createReadStream(filePath)

      stream.on('data', chunk => hash.update(chunk))
      stream.on('end', () => resolve(hash.digest('hex')))
      stream.on('error', reject)
    })
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
    logger.info('=== 检查 Git 环境 ===')

    // 检查 git.exe 是否存在
    const exeExists = fs.existsSync(this.gitExe)
    logger.info(`Git 可执行文件存在: ${exeExists}`)

    if (!exeExists) {
      return { exeExists: false, canRun: false }
    }

    // 检查能否正常运行
    try {
      const version = await this.getGitVersion()
      logger.info(`Git 版本: ${version}`)
      return { exeExists: true, canRun: true, version }
    } catch (error) {
      logger.error(`Git 无法正常运行: ${error}`)
      return { exeExists: true, canRun: false, error: String(error) }
    }
  }

  private getGitVersion(): Promise<string> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.gitExe, ['-v'], { stdio: 'pipe' })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })
      proc.stderr?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          reject(new Error(`Git 版本检查失败，退出码: ${code}`))
        }
      })

      proc.on('error', reject)
    })
  }

  protected async downloadPackage(
    onProgress?: ProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 下载 Git 安装包 ===')

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

      const result = await this.downloader.download(mirror.url, tempZipPath, progress => {
        // 检查是否是当前活跃的操作
        if (operationId !== this.currentOperationId) {
          return
        }

        // 上报下载进度，包含速度和大小信息
        onProgress?.({
          progress: progress.progress,
          speed: progress.speed,
          downloadedSize: progress.downloadedSize,
          totalSize: progress.totalSize,
        })
        onOpProgress({
          progress: progress.progress,
          description: `下载中... ${progress.progress.toFixed(1)}%`,
        })
      })

      return result
    }

    const result = await this.rotationService.execute(
      mirrors,
      downloadOperation,
      undefined,
      selectedMirror
    )

    if (!result.success) {
      return { success: false, error: result.error }
    }

    logger.info(`Git 安装包下载完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }

  protected async installEnvironment(
    onProgress?: (progress: number, message: string, details?: any) => void,
    _selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 安装 Git 环境 ===')

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
      logger.info('正在解压 Git...')
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
        const itemProgress = 60 + Math.floor(((i + 1) / totalItems) * 20)
        onProgress?.(itemProgress, `移动文件 ${i + 1}/${totalItems}...`)
      }

      logger.info('Git 解压完成')

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
      logger.error(`Git 安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }
}

/** @deprecated 使用 UvInstaller 代替 */
export const PipInstaller = UvInstaller
