/**
 * 依赖安装服务
 * 重构版本 - 独立实现依赖安装
 */

import * as fs from 'fs'
import * as path from 'path'
import * as crypto from 'crypto'
import { spawn, ChildProcess } from 'child_process'
import { MirrorService, MirrorSource } from './mirrorService'
import {
  MIRROR_SWITCH_ABORTED,
  MirrorRotationService,
  NetworkOperationCallback,
  NetworkOperationProgress,
  PROBE_TIMEOUT_MS,
} from './mirrorRotationService'
import { createPipProgressState, feedPipOutput, pipProgressPercent } from './pipProgress'

import { getLogger } from './logger'
const logger = getLogger('后端依赖安装服务')

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

// ==================== 安装中换源：活动安装跟踪（#499） ====================

// IPC 处理器每次调用都会 new 一个 DependencyService，中止状态只能放在模块级；
// 同一时刻只有一条安装流水（初始化窗口只有一个）
interface ActiveInstallHandle {
  aborted: boolean
  pipProc: ChildProcess | null
  onSettled?: () => void
}

let activeInstall: ActiveInstallHandle | null = null

/**
 * 中止正在进行的依赖安装并等它完全收尾（避免两次 pip 并发）。
 * 返回是否有安装被中止；没有进行中的安装时返回 false。
 * 被中止的安装会以 MIRROR_SWITCH_ABORTED 失败收尾，哈希不会落盘。
 */
export async function abortActiveDependencyInstall(): Promise<boolean> {
  const handle = activeInstall
  if (!handle) return false
  logger.info('收到安装中止请求（换源），停止当前依赖安装')
  handle.aborted = true
  handle.pipProc?.kill()
  await new Promise<void>(resolve => {
    if (activeInstall !== handle) {
      resolve()
      return
    }
    const prev = handle.onSettled
    handle.onSettled = () => {
      prev?.()
      resolve()
    }
  })
  return true
}

// ==================== 依赖安装服务类 ====================

export class DependencyService {
  private appRoot: string
  private pythonExe: string
  private requirementsPath: string
  private hashFilePath: string
  private mirrorService: MirrorService
  private rotationService: MirrorRotationService

  constructor(appRoot: string, mirrorService: MirrorService) {
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
    forceInstall: boolean = false,
    forceReinstall: boolean = false
  ): Promise<{ success: boolean; error?: string; skipped?: boolean }> {
    // 注册活动安装句柄，让「安装中换源」能找到并中止本次安装（#499）；
    // 若有更老的句柄残留（异常路径），先标记中止，避免误杀新安装的 pip
    const handle: ActiveInstallHandle = { aborted: false, pipProc: null }
    if (activeInstall) {
      logger.warn('发现残留的上一安装句柄，标记中止后接管')
      activeInstall.aborted = true
    }
    activeInstall = handle
    try {
      // 第一步：环境检查
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: '正在检查依赖状态...',
        details: {},
      })
      const checkResult = await this.checkDependencies()

      // 上报检查结果
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

      // 检查阶段收到换源中止：不进入安装，直接以中止收尾（#499）
      if (handle.aborted) {
        logger.info('依赖检查阶段被中止，跳过安装')
        return { success: false, error: MIRROR_SWITCH_ABORTED }
      }

      // 第二步：安装依赖
      // 不在这里发送 progress: 0，避免进度条跳回0
      const installResult = await this.performInstall(
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
        selectedMirror,
        handle,
        forceReinstall
      )

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
        details: {},
      })
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`依赖安装失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    } finally {
      if (activeInstall === handle) {
        activeInstall = null
      }
      handle.onSettled?.()
    }
  }

  /**
   * 检查依赖状态
   */
  private async checkDependencies(): Promise<DependencyCheckResult> {
    logger.info('=== 检查依赖状态 ===')

    // 检查 requirements.txt 是否存在
    if (!fs.existsSync(this.requirementsPath)) {
      logger.info('requirements.txt 不存在')
      return { requirementsExists: false, needsInstall: false }
    }

    // 计算当前哈希
    const currentHash = this.calculateHash()
    logger.info(`当前哈希: ${currentHash.substring(0, 8)}...`)

    // 读取上次安装的哈希
    const lastHash = this.loadHash()
    logger.info(`上次哈希: ${lastHash ? lastHash.substring(0, 8) + '...' : 'null'}`)

    // 判断是否需要安装
    const needsInstall = lastHash === null || currentHash !== lastHash

    return {
      requirementsExists: true,
      needsInstall,
      currentHash,
      lastHash: lastHash || undefined,
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
      logger.warn(`读取哈希文件失败: ${error}`)
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
      logger.info('哈希值已保存')
    } catch (error) {
      logger.warn(`保存哈希文件失败: ${error}`)
    }
  }

  /**
   * 执行依赖安装
   */
  private async performInstall(
    onProgress?: (
      progress: NetworkOperationProgress,
      mirrorName: string,
      mirrorIndex: number,
      totalMirrors: number
    ) => void,
    selectedMirror?: string,
    handle?: ActiveInstallHandle,
    forceReinstall: boolean = false
  ): Promise<{ success: boolean; error?: string }> {
    const mirrors = this.mirrorService.getMirrors('pip_mirror')

    // 定义依赖安装操作
    const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      // 换源中止：新安装已在别处发起，本操作不再起 pip（#499）
      if (handle?.aborted) {
        return { success: false, error: MIRROR_SWITCH_ABORTED }
      }
      try {
        // 1. 检查并安装基础工具
        onOpProgress({ progress: 20, description: '检查基础工具...' })
        await this.ensureBasicTools(mirror, handle)

        // 2. 安装依赖
        onOpProgress({ progress: 40, description: '安装依赖包...' })
        await this.installRequirements(
          mirror,
          progress => {
            onOpProgress({ progress, description: '安装依赖包...' })
          },
          handle,
          forceReinstall
        )

        onOpProgress({ progress: 100, description: '安装完成' })
        return { success: true }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMsg }
      }
    }

    // 安装前探测各镜像源延迟，优先使用更快的源（未指定镜像源时生效）
    const probeOperation: NetworkOperationCallback | undefined = selectedMirror
      ? undefined
      : async mirror => {
          const base = mirror.url.endsWith('/') ? mirror.url : mirror.url + '/'
          const response = await fetch(new URL('simple/pip/', base), {
            signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
          })
          await response.body?.cancel().catch(() => {})
          return { success: response.ok }
        }

    // 使用镜像源轮替
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
      selectedMirror,
      probeOperation,
      () => handle?.aborted ?? false
    )

    if (!result.success) {
      return { success: false, error: result.error }
    }

    logger.info(`依赖安装完成，使用镜像源: ${result.usedMirror?.name}`)
    return { success: true }
  }

  /**
   * 确保基础工具已安装（setuptools, wheel）
   */
  private async ensureBasicTools(
    mirror: MirrorSource,
    handle?: ActiveInstallHandle
  ): Promise<void> {
    logger.info('=== 检查基础工具 ===')

    // 检查 setuptools 和 wheel 是否已安装
    const toolsInstalled = await this.checkBasicTools()

    if (toolsInstalled) {
      logger.info('基础工具已安装')
      return
    }

    logger.info('正在安装基础工具...')

    await new Promise<void>((resolve, _reject) => {
      // 换源中止：不再起新的 pip（#499）
      if (handle?.aborted) {
        resolve()
        return
      }
      const hostname = new URL(mirror.url).hostname

      const proc = spawn(
        this.pythonExe,
        [
          '-m',
          'pip',
          'install',
          '--upgrade',
          'setuptools',
          'wheel',
          '-i',
          mirror.url,
          '--trusted-host',
          hostname,
        ],
        {
          cwd: this.appRoot,
          stdio: 'pipe',
        }
      )

      if (handle) handle.pipProc = proc

      proc.stdout?.on('data', data => {
        logger.info(`setuptools/wheel: ${data.toString().trim()}`)
      })

      proc.stderr?.on('data', data => {
        logger.info(`setuptools/wheel error: ${data.toString().trim()}`)
      })

      proc.on('close', code => {
        if (handle && handle.pipProc === proc) handle.pipProc = null
        if (handle?.aborted) {
          // 保持容错 resolve；中止由后续 installRequirements 的拒起/拒绝收口
          resolve()
          return
        }
        if (code === 0) {
          logger.info('基础工具安装完成')
          resolve()
        } else {
          // 即使失败也继续，因为可能已经存在
          logger.warn('⚠️ 基础工具安装失败，但继续')
          resolve()
        }
      })

      proc.on('error', error => {
        logger.warn(`基础工具安装进程错误: ${error}`)
        resolve()
      })
    })
  }

  /**
   * 检查基础工具是否已安装
   */
  private checkBasicTools(): Promise<boolean> {
    return new Promise(resolve => {
      const proc = spawn(this.pythonExe, ['-m', 'pip', 'list'], {
        cwd: this.appRoot,
        stdio: 'pipe',
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
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
  private installRequirements(
    mirror: MirrorSource,
    onProgress?: (progress: number) => void,
    handle?: ActiveInstallHandle,
    forceReinstall: boolean = false
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      // 换源中止：拒起新 pip（#499）
      if (handle?.aborted) {
        reject(new Error(MIRROR_SWITCH_ABORTED))
        return
      }
      const hostname = new URL(mirror.url).hostname

      const args = [
        '-m',
        'pip',
        'install',
        '-r',
        this.requirementsPath,
        '-i',
        mirror.url,
        '--trusted-host',
        hostname,
        '--no-warn-script-location',
      ]
      // 换源重跑：--force-reinstall 重解包已缓存 wheel，修复中止瞬间可能留下的半写 dist
      if (forceReinstall) args.push('--force-reinstall')

      const proc = spawn(this.pythonExe, args, {
        cwd: this.appRoot,
        stdio: 'pipe',
      })
      if (handle) handle.pipProc = proc

      let stdoutData = ''
      let stderrData = ''
      const pipState = createPipProgressState()
      let lastProgress = pipProgressPercent(pipState)

      proc.stdout?.on('data', data => {
        const output = data.toString().trim()
        stdoutData += output
        logger.info(`pip install: ${output}`)

        // #499：按已完成下载的字节数推进 40-90 的进度段，
        // 解析不到字节时 pipProgress 内部回退旧的包数锚点
        feedPipOutput(pipState, data.toString())
        const progress = pipProgressPercent(pipState)
        if (progress !== lastProgress && onProgress) {
          lastProgress = progress
          onProgress(progress)
        }
      })

      proc.stderr?.on('data', data => {
        const output = data.toString().trim()
        stderrData += output
        logger.info(`pip install error: ${output}`)
      })

      proc.on('close', code => {
        if (handle && handle.pipProc === proc) handle.pipProc = null
        logger.info(`pip install 退出码: ${code}`)

        // 被换源中止的 pip 必须先判中止：空 stderr 会走 !hasActualError 假成功，
        // 进而把未装完的哈希落盘（#499）
        if (handle?.aborted) {
          reject(new Error(MIRROR_SWITCH_ABORTED))
          return
        }

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
          logger.info('依赖安装成功')
          resolve()
        } else {
          reject(new Error(`依赖安装失败，退出码: ${code}`))
        }
      })

      proc.on('error', reject)
    })
  }
}
