/**
 * 源码拉取服务
 * 重构版本 - 独立实现仓库拉取和部署
 */

import * as fs from 'fs'
import * as path from 'path'
import { spawn } from 'child_process'
import { MirrorService, MirrorSource } from './mirrorService'
import {
  MirrorRotationService,
  NetworkOperationCallback,
  NetworkOperationProgress,
} from './mirrorRotationService'

// 导入日志服务
import { getLogger } from './logger'
import {
  assertBundledSnapshotMarker,
  BundledSnapshotMarker,
  readJsonFileWithOptionalBom,
  resolveContainedPath,
  verifyBundledSnapshotWheelhouseContract,
} from './bundledArtifactValidation'
const logger = getLogger('仓库服务')

const BUNDLED_SNAPSHOT_RELATIVE_PATH = path.join('resources', 'integration-snapshot')
const BUNDLED_SNAPSHOT_MARKER = 'manifest.json'
const RUNTIME_TRANSACTION_JOURNAL = '.runtime-deploy-transaction.json'
const RUNTIME_DEPLOY_ITEMS = [
  'app',
  'res',
  'scripts',
  'plugins/auto_mas_core',
  'plugins/browser',
  'plugins/wheels',
  'plugins/ok_script_adapter',
  'plugins/okww_adapter',
  'main.py',
  'pyproject.toml',
  'requirements.txt',
  'LICENSE',
  'README.md',
] as const
const RUNTIME_DIRECTORY_ITEMS = new Set<string>([
  'app',
  'res',
  'scripts',
  'plugins/auto_mas_core',
  'plugins/browser',
  'plugins/wheels',
  'plugins/ok_script_adapter',
  'plugins/okww_adapter',
])

interface RuntimeDeploymentSwap {
  item: string
  hadBackup: boolean
}

interface RuntimeDeploymentJournal {
  schema_version: 1
  staging_directory: string
  backup_directory: string
  swaps: RuntimeDeploymentSwap[]
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
  private transactionJournalPath: string

  constructor(appRoot: string, mirrorService: MirrorService, targetBranch: string = 'dev') {
    this.appRoot = appRoot
    this.repoPath = path.join(appRoot, 'repo')
    this.gitExe = path.join(appRoot, 'environment', 'git', 'bin', 'git.exe')
    this.mirrorService = mirrorService
    this.rotationService = new MirrorRotationService()
    this.targetBranch = targetBranch
    this.transactionJournalPath = path.join(appRoot, 'environment', RUNTIME_TRANSACTION_JOURNAL)
  }

  /**
   * 源码拉取方法
   */
  async pullRepository(
    onProgress?: RepositoryProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    try {
      this.recoverInterruptedDeployment()
      const bundledSnapshotPath = this.resolveBundledSnapshotPath()
      if (bundledSnapshotPath) {
        return await this.deployBundledSnapshot(bundledSnapshotPath, onProgress)
      }

      // 第一步：环境检查
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: '正在检查本地仓库...',
        details: {},
      })
      const checkResult = await this.checkRepository()
      logger.info(`仓库检查结果: ${JSON.stringify(checkResult)}`)

      // 上报检查结果
      onProgress?.({
        stage: 'check',
        progress: 100,
        message: checkResult.exists ? '本地仓库已存在' : '本地仓库不存在',
        details: {
          checkInfo: checkResult,
        },
      })

      // 第二步：拉取仓库
      onProgress?.({
        stage: 'pull',
        progress: 0,
        message: '正在拉取仓库...',
        details: {},
      })
      const pullResult = await this.pullOrCloneRepository(
        checkResult,
        (opProgress, mirrorName, mirrorIndex, totalMirrors) => {
          onProgress?.({
            stage: 'pull',
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

      if (!pullResult.success) {
        return { success: false, error: pullResult.error }
      }

      // 第三步：部署仓库
      onProgress?.({
        stage: 'deploy',
        progress: 0,
        message: '正在部署仓库...',
        details: {},
      })
      const deployResult = await this.deployRepository((progress, message) => {
        onProgress?.({
          stage: 'deploy',
          progress,
          message,
          details: {},
        })
      })

      if (deployResult.success) {
        onProgress?.({
          stage: 'deploy',
          progress: 100,
          message: '部署完成',
          details: {},
        })
      }

      return deployResult
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`源码拉取失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  private resolveBundledSnapshotPath(): string | null {
    const snapshotPath = path.join(this.appRoot, BUNDLED_SNAPSHOT_RELATIVE_PATH)
    if (!fs.existsSync(snapshotPath)) {
      return null
    }

    const requiredFiles = [BUNDLED_SNAPSHOT_MARKER, ...RUNTIME_DEPLOY_ITEMS]
    const missingFiles = requiredFiles.filter(item => !fs.existsSync(path.join(snapshotPath, item)))
    if (missingFiles.length > 0) {
      throw new Error(
        `Bundled integration snapshot is incomplete: missing ${missingFiles.join(', ')}`
      )
    }

    const markerPath = path.join(snapshotPath, BUNDLED_SNAPSHOT_MARKER)
    let marker: BundledSnapshotMarker
    try {
      marker = readJsonFileWithOptionalBom<BundledSnapshotMarker>(markerPath)
    } catch (error) {
      throw new Error(`Bundled integration snapshot marker is invalid: ${error}`)
    }
    assertBundledSnapshotMarker(marker)
    if (
      marker.wheelhouse_contract?.manifest_schema_version !== 3 ||
      marker.wheelhouse_contract?.runtime_lock_schema_version !== 1 ||
      !Number.isSafeInteger(marker.wheelhouse_contract?.wheel_count) ||
      marker.wheelhouse_contract?.plugin_distribution_count !== 23 ||
      marker.wheelhouse_contract?.plugin_entry_point_count !== 21 ||
      typeof marker.wheelhouse_contract?.core_distribution_version !== 'string' ||
      !marker.wheelhouse_contract.core_distribution_version.trim() ||
      typeof marker.wheelhouse_contract?.manifest_sha256 !== 'string' ||
      !/^[0-9a-f]{64}$/i.test(marker.wheelhouse_contract.manifest_sha256) ||
      typeof marker.wheelhouse_contract?.runtime_lock_sha256 !== 'string' ||
      !/^[0-9a-f]{64}$/i.test(marker.wheelhouse_contract.runtime_lock_sha256)
    ) {
      throw new Error('Bundled integration snapshot marker has an unsupported schema')
    }

    const markerMissingPaths: string[] = []
    for (const requiredPath of marker.required_paths) {
      const resolvedPath = resolveContainedPath(snapshotPath, requiredPath)
      if (!fs.existsSync(resolvedPath)) {
        markerMissingPaths.push(requiredPath)
      }
    }
    if (markerMissingPaths.length > 0) {
      throw new Error(
        `Bundled integration snapshot marker paths are missing: ${markerMissingPaths.join(', ')}`
      )
    }

    const wrongTypes = requiredFiles.filter(item => {
      const candidate = path.join(snapshotPath, item)
      if (!fs.existsSync(candidate)) {
        return false
      }
      const shouldBeDirectory = RUNTIME_DIRECTORY_ITEMS.has(item)
      return shouldBeDirectory
        ? !fs.statSync(candidate).isDirectory()
        : !fs.statSync(candidate).isFile()
    })
    if (wrongTypes.length > 0) {
      throw new Error(
        `Bundled integration snapshot contains paths with the wrong type: ${wrongTypes.join(', ')}`
      )
    }

    const snapshotVersionPath = path.join(snapshotPath, 'res', 'version.json')
    let snapshotVersion: { version?: unknown; version_info?: unknown }
    try {
      snapshotVersion = readJsonFileWithOptionalBom(snapshotVersionPath)
    } catch (error) {
      throw new Error(`Bundled integration snapshot version file is invalid: ${error}`)
    }
    if (
      snapshotVersion.version !== marker.version ||
      snapshotVersion.version_info == null ||
      typeof snapshotVersion.version_info !== 'object' ||
      !Object.prototype.hasOwnProperty.call(snapshotVersion.version_info, marker.version)
    ) {
      throw new Error('Bundled integration snapshot marker version does not match res/version.json')
    }

    const wheelManifestPath = resolveContainedPath(snapshotPath, marker.wheel_manifest)
    const expectedWheelManifestPath = path.join(snapshotPath, 'plugins', 'wheels', 'manifest.json')
    if (wheelManifestPath !== expectedWheelManifestPath) {
      throw new Error(
        'Bundled integration snapshot wheel_manifest must reference plugins/wheels/manifest.json'
      )
    }
    verifyBundledSnapshotWheelhouseContract(
      path.dirname(wheelManifestPath),
      marker.wheelhouse_contract
    )

    return snapshotPath
  }

  private async deployBundledSnapshot(
    snapshotPath: string,
    onProgress?: RepositoryProgressCallback
  ): Promise<{ success: boolean; error?: string }> {
    logger.info(`使用随包集成快照，跳过远程仓库操作: ${snapshotPath}`)

    onProgress?.({
      stage: 'check',
      progress: 100,
      message: '已检测到随包集成快照',
      details: {
        checkInfo: {
          exists: true,
          isGitRepo: false,
          isHealthy: true,
          currentBranch: 'bundled-integration-snapshot',
        },
      },
    })
    onProgress?.({
      stage: 'pull',
      progress: 100,
      message: '使用随包集成快照，已跳过网络拉取',
      details: {},
    })
    onProgress?.({
      stage: 'deploy',
      progress: 0,
      message: '正在部署随包集成快照...',
      details: {},
    })

    await this.copyToRoot(snapshotPath, false)

    onProgress?.({
      stage: 'deploy',
      progress: 100,
      message: '随包集成快照部署完成',
      details: {},
    })
    return { success: true }
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
        logger.info(`本地仓库健康，当前分支: ${currentBranch}`)
        return { exists: true, isGitRepo: true, isHealthy: true, currentBranch }
      } else {
        logger.warn('本地仓库存在问题，需要清理')
        // 清理有问题的仓库
        fs.rmSync(this.repoPath, { recursive: true, force: true })
        return { exists: false, isGitRepo: false, isHealthy: false }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`检查仓库健康状态失败: ${errorMsg}`)
      // 清理有问题的仓库
      fs.rmSync(this.repoPath, { recursive: true, force: true })
      return { exists: false, isGitRepo: false, isHealthy: false }
    }
  }

  /**
   * 检查 Git 仓库健康状态
   */
  private checkGitHealth(): Promise<boolean> {
    return new Promise(resolve => {
      const proc = spawn(this.gitExe, ['status'], {
        cwd: this.repoPath,
        stdio: 'pipe',
      })

      proc.on('close', code => {
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
        stdio: 'pipe',
      })

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
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
    onProgress?: (
      progress: NetworkOperationProgress,
      mirrorName: string,
      mirrorIndex: number,
      totalMirrors: number
    ) => void,
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
    const result = await this.rotationService.execute(
      mirrors,
      repoOperation,
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

    logger.info(`仓库拉取完成，使用镜像源: ${result.usedMirror?.name}`)
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
      logger.error(`更新仓库失败: ${errorMsg}`)
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
      logger.error(`克隆仓库失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  /**
   * 检查远程分支是否存在
   */
  private checkRemoteBranch(repoUrl: string, branch: string): Promise<boolean> {
    return new Promise(resolve => {
      const proc = spawn(this.gitExe, ['ls-remote', '--heads', repoUrl, branch], {
        stdio: 'pipe',
      })

      // 设置 30 秒超时
      const timeout = setTimeout(() => {
        logger.warn('检查远程分支超时，终止进程')
        proc.kill()
        resolve(false)
      }, 30000)

      let output = ''
      proc.stdout?.on('data', data => {
        output += data.toString()
      })

      proc.on('close', code => {
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
        stdio: 'pipe',
      })

      proc.on('close', code => {
        if (code === 0) {
          logger.info('远程仓库配置完成')
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
    await new Promise<void>(resolve => {
      const proc = spawn(this.gitExe, ['config', '--unset-all', 'remote.origin.fetch'], {
        cwd: this.repoPath,
        stdio: 'pipe',
      })
      proc.on('close', () => resolve())
      proc.on('error', () => resolve())
    })

    // 设置只拉取目标分支
    await new Promise<void>((resolve, reject) => {
      const refspec = `+refs/heads/${this.targetBranch}:refs/remotes/origin/${this.targetBranch}`
      const proc = spawn(this.gitExe, ['config', '--add', 'remote.origin.fetch', refspec], {
        cwd: this.repoPath,
        stdio: 'pipe',
      })

      proc.on('close', code => {
        if (code === 0) {
          logger.info('浅克隆配置完成')
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
      const proc = spawn(
        this.gitExe,
        ['fetch', 'origin', this.targetBranch, '--depth=1', '--no-tags'],
        {
          cwd: this.repoPath,
          stdio: 'pipe',
        }
      )

      // 设置 60 秒超时（fetch 可能需要更长时间）
      const timeout = setTimeout(() => {
        logger.warn('拉取最新提交超时，终止进程')
        proc.kill()
        reject(new Error('拉取最新提交超时'))
      }, 60000)

      proc.stdout?.on('data', data => {
        logger.info(`fetch: ${data.toString().trim()}`)
      })

      proc.on('close', code => {
        clearTimeout(timeout)
        if (code === 0) {
          logger.info('拉取最新提交完成')
          resolve()
        } else {
          reject(new Error('拉取最新提交失败'))
        }
      })

      proc.on('error', error => {
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
      const proc = spawn(
        this.gitExe,
        ['checkout', '-B', this.targetBranch, `origin/${this.targetBranch}`],
        {
          cwd: this.repoPath,
          stdio: 'pipe',
        }
      )

      proc.on('close', code => {
        if (code === 0) {
          logger.info('切换分支完成')
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

      const proc = spawn(
        this.gitExe,
        [
          'clone',
          '--single-branch',
          '--depth=1',
          '--branch',
          this.targetBranch,
          repoUrl,
          this.repoPath,
        ],
        {
          stdio: 'pipe',
        }
      )

      // 设置 120 秒超时（clone 可能需要较长时间）
      const timeout = setTimeout(() => {
        logger.warn('克隆仓库超时，终止进程')
        proc.kill()
        reject(new Error('克隆仓库超时'))
      }, 120000)

      proc.stdout?.on('data', data => {
        logger.info(`clone: ${data.toString().trim()}`)
      })

      proc.on('close', code => {
        clearTimeout(timeout)
        if (code === 0) {
          logger.info('克隆仓库完成')
          resolve()
        } else {
          reject(new Error('克隆仓库失败'))
        }
      })

      proc.on('error', error => {
        clearTimeout(timeout)
        reject(error)
      })
    })
  }

  /**
   * 部署仓库
   */
  private async deployRepository(
    onProgress?: (progress: number, message: string) => void
  ): Promise<{ success: boolean; error?: string }> {
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
      logger.info('仓库部署完成')
      return { success: true }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`部署仓库失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  /**
   * 优化仓库存储
   */
  private async optimizeStorage(): Promise<void> {
    // 删除 reflog
    await new Promise<void>(resolve => {
      const proc = spawn(this.gitExe, ['reflog', 'expire', '--expire=now', '--all'], {
        cwd: this.repoPath,
        stdio: 'pipe',
      })
      proc.on('close', () => {
        logger.info('reflog 清理完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })

    // 垃圾回收
    await new Promise<void>(resolve => {
      const proc = spawn(this.gitExe, ['gc', '--aggressive', '--prune=now'], {
        cwd: this.repoPath,
        stdio: 'pipe',
      })
      proc.on('close', () => {
        logger.info('垃圾回收完成')
        resolve()
      })
      proc.on('error', () => resolve())
    })
  }

  /**
   * 复制文件到根目录
   */
  private async copyToRoot(
    sourceRoot: string = this.repoPath,
    includeGitMetadata: boolean = true
  ): Promise<void> {
    const itemsToCopy = includeGitMetadata
      ? ['.git', ...RUNTIME_DEPLOY_ITEMS]
      : [...RUNTIME_DEPLOY_ITEMS]
    const transactionId = `${process.pid}-${Date.now()}`
    const stagingRoot = path.join(this.appRoot, `.runtime-stage-${transactionId}`)
    const backupRoot = path.join(this.appRoot, `.runtime-backup-${transactionId}`)
    const stagedItems: string[] = []
    let journalWritten = false

    try {
      fs.mkdirSync(stagingRoot, { recursive: true })
      fs.mkdirSync(backupRoot, { recursive: true })

      // First build a complete same-volume staging tree. No active runtime path
      // is touched until every source item has been copied successfully.
      for (const item of itemsToCopy) {
        const sourcePath = path.join(sourceRoot, item)
        const stagedPath = path.join(stagingRoot, item)
        if (!fs.existsSync(sourcePath)) {
          throw new Error(`Runtime deployment source item is missing: ${item}`)
        }

        fs.mkdirSync(path.dirname(stagedPath), { recursive: true })
        if (fs.statSync(sourcePath).isDirectory()) {
          this.copyDirectory(sourcePath, stagedPath)
        } else if (item === 'pyproject.toml') {
          this.copyPyprojectToml(sourcePath, stagedPath)
        } else {
          fs.copyFileSync(sourcePath, stagedPath)
        }
        stagedItems.push(item)
        logger.info(`暂存完成: ${item}`)
      }

      const journal: RuntimeDeploymentJournal = {
        schema_version: 1,
        staging_directory: path.basename(stagingRoot),
        backup_directory: path.basename(backupRoot),
        swaps: stagedItems.map(item => ({
          item,
          hadBackup: fs.existsSync(path.join(this.appRoot, item)),
        })),
      }
      this.writeDeploymentJournal(journal)
      journalWritten = true

      // Rename is atomic on the same volume. Keep the old path in backup until
      // every top-level item has been promoted.
      for (const item of stagedItems) {
        const stagedPath = path.join(stagingRoot, item)
        const destinationPath = path.join(this.appRoot, item)
        const backupPath = path.join(backupRoot, item)
        const hadBackup = fs.existsSync(destinationPath)

        if (hadBackup) {
          fs.mkdirSync(path.dirname(backupPath), { recursive: true })
          this.movePath(destinationPath, backupPath)
        }

        fs.mkdirSync(path.dirname(destinationPath), { recursive: true })
        this.movePath(stagedPath, destinationPath)
        logger.info(`部署完成: ${item}`)
      }

      // Removing the journal is the commit point. If the process exits before
      // this point, the next startup restores the old runtime from backup.
      this.clearDeploymentJournal()
      journalWritten = false
      this.cleanupTransactionPath(backupRoot)
      this.cleanupTransactionPath(stagingRoot)
    } catch (error) {
      const rollbackErrors: string[] = []
      if (journalWritten) {
        try {
          this.recoverInterruptedDeployment()
          journalWritten = false
        } catch (rollbackError) {
          rollbackErrors.push(
            rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
          )
        }
      } else {
        // Staging failed before active paths were touched.
        this.cleanupTransactionPath(backupRoot)
        this.cleanupTransactionPath(stagingRoot)
      }

      const errorMsg = error instanceof Error ? error.message : String(error)
      if (rollbackErrors.length > 0) {
        throw new Error(
          `Runtime deployment failed: ${errorMsg}; rollback incomplete (${rollbackErrors.join('; ')}). Recovery data: ${backupRoot}`
        )
      }
      throw new Error(`Runtime deployment failed and was rolled back: ${errorMsg}`)
    }
  }

  private movePath(sourcePath: string, destinationPath: string): void {
    fs.renameSync(sourcePath, destinationPath)
  }

  private cleanupTransactionPath(targetPath: string): void {
    try {
      fs.rmSync(targetPath, { recursive: true, force: true })
    } catch (error) {
      logger.warn(
        `无法清理部署事务临时目录，保留供人工审计: ${targetPath}, ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  private writeDeploymentJournal(journal: RuntimeDeploymentJournal): void {
    const journalDirectory = path.dirname(this.transactionJournalPath)
    fs.mkdirSync(journalDirectory, { recursive: true })
    if (fs.existsSync(this.transactionJournalPath)) {
      throw new Error('Another runtime deployment transaction is already active')
    }

    const temporaryJournalPath = `${this.transactionJournalPath}.tmp-${process.pid}-${Date.now()}`
    fs.writeFileSync(temporaryJournalPath, JSON.stringify(journal, null, 2), 'utf-8')
    fs.renameSync(temporaryJournalPath, this.transactionJournalPath)
  }

  private clearDeploymentJournal(): void {
    fs.rmSync(this.transactionJournalPath, { force: true })
  }

  private recoverInterruptedDeployment(): void {
    if (!fs.existsSync(this.transactionJournalPath)) {
      return
    }

    let journal: RuntimeDeploymentJournal
    try {
      journal = readJsonFileWithOptionalBom<RuntimeDeploymentJournal>(this.transactionJournalPath)
    } catch (error) {
      throw new Error(`Runtime deployment recovery journal is invalid: ${error}`)
    }

    const allowedItems = new Set<string>(['.git', ...RUNTIME_DEPLOY_ITEMS])
    if (
      journal.schema_version !== 1 ||
      !this.isTransactionDirectoryName(journal.staging_directory, '.runtime-stage-') ||
      !this.isTransactionDirectoryName(journal.backup_directory, '.runtime-backup-') ||
      !Array.isArray(journal.swaps) ||
      journal.swaps.length === 0 ||
      journal.swaps.some(
        swap =>
          swap == null ||
          typeof swap.item !== 'string' ||
          !allowedItems.has(swap.item) ||
          typeof swap.hadBackup !== 'boolean'
      )
    ) {
      throw new Error('Runtime deployment recovery journal has an unsupported schema')
    }

    const duplicateItems = journal.swaps.filter(
      (swap, index, swaps) => swaps.findIndex(candidate => candidate.item === swap.item) !== index
    )
    if (duplicateItems.length > 0) {
      throw new Error('Runtime deployment recovery journal contains duplicate items')
    }

    const stagingRoot = path.join(this.appRoot, journal.staging_directory)
    const backupRoot = path.join(this.appRoot, journal.backup_directory)
    const recoveryErrors: string[] = []

    for (const swap of [...journal.swaps].reverse()) {
      const destinationPath = path.join(this.appRoot, swap.item)
      const backupPath = path.join(backupRoot, swap.item)
      const stagedPath = path.join(stagingRoot, swap.item)

      try {
        if (swap.hadBackup) {
          if (fs.existsSync(backupPath)) {
            if (fs.existsSync(destinationPath)) {
              fs.rmSync(destinationPath, { recursive: true, force: true })
            }
            fs.mkdirSync(path.dirname(destinationPath), { recursive: true })
            this.movePath(backupPath, destinationPath)
          } else if (!fs.existsSync(stagedPath) || !fs.existsSync(destinationPath)) {
            throw new Error('original backup is missing after promotion started')
          }
        } else if (fs.existsSync(destinationPath) && !fs.existsSync(stagedPath)) {
          // The original path did not exist, so a destination with no staged
          // counterpart is the uncommitted promoted path.
          fs.rmSync(destinationPath, { recursive: true, force: true })
        }
      } catch (error) {
        recoveryErrors.push(
          `${swap.item}: ${error instanceof Error ? error.message : String(error)}`
        )
      }
    }

    if (recoveryErrors.length > 0) {
      throw new Error(
        `Interrupted runtime deployment recovery is incomplete (${recoveryErrors.join('; ')}). Recovery data: ${backupRoot}`
      )
    }

    this.clearDeploymentJournal()
    this.cleanupTransactionPath(backupRoot)
    this.cleanupTransactionPath(stagingRoot)
    logger.warn('Recovered an interrupted runtime deployment before continuing')
  }

  private isTransactionDirectoryName(value: unknown, prefix: string): value is string {
    return (
      typeof value === 'string' &&
      value.startsWith(prefix) &&
      value.length > prefix.length &&
      path.basename(value) === value
    )
  }

  /**
   * 复制 pyproject.toml，剥离开发期专用 section（运行时 uv sync 不需要）
   */
  private copyPyprojectToml(src: string, dest: string): void {
    const content = fs.readFileSync(src, 'utf-8')
    const stripped = this.stripTomlSections(content, [
      '[dependency-groups]',
      '[tool.uv.workspace]',
      '[tool.uv.sources]',
    ])
    fs.writeFileSync(dest, stripped, 'utf-8')
    logger.info('复制完成: pyproject.toml（已剥离开发期 section）')
  }

  /**
   * 从 TOML 文本中移除指定 section（含其所有行直到下一个 header）
   */
  private stripTomlSections(text: string, headers: string[]): string {
    const lines = text.split('\n')
    const headerSet = new Set(headers)

    const isHeader = (line: string): boolean => {
      const s = line.trim()
      return s.startsWith('[') && s.endsWith(']') && !s.startsWith('[[')
    }

    const skipFrom: number[] = []
    for (let i = 0; i < lines.length; i++) {
      if (headerSet.has(lines[i].trim())) {
        skipFrom.push(i)
      }
    }

    if (skipFrom.length === 0) return text

    const skip = new Set<number>()
    for (const start of skipFrom) {
      let end = lines.length
      for (let i = start + 1; i < lines.length; i++) {
        if (isHeader(lines[i])) {
          end = i
          break
        }
      }
      for (let i = start; i < end; i++) {
        skip.add(i)
      }
    }

    const result = lines.filter((_, i) => !skip.has(i))
    // 清理连续空行
    return result.join('\n').replace(/\n{3,}/g, '\n\n')
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
