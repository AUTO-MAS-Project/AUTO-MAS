/**
 * 依赖安装服务
 * 使用 uv 从 pyproject.toml 或 requirements.txt 安装依赖到 .venv
 */

import * as fs from 'fs'
import * as path from 'path'
import * as crypto from 'crypto'
import { MirrorService, MirrorSource } from './mirrorService'
import {
  MirrorRotationService,
  NetworkOperationCallback,
  NetworkOperationProgress,
} from './mirrorRotationService'
import {
  BundledRuntimeLock,
  BundledRuntimeLockEntry,
  readAndVerifyBundledRuntimeLock,
  resolveLockedWheelPaths,
} from './bundledArtifactValidation'
import { runBoundedProcess } from './boundedProcess'
import { writeJsonFileAtomically } from './atomicJsonFile'
import { requiresBundledRuntimeLock } from './bundledRuntimePolicy'

import { getLogger } from './logger'
const logger = getLogger('后端依赖安装服务')

const FILESYSTEM_RETRYABLE_ERROR_CODES = new Set(['EACCES', 'EBUSY', 'ENOTEMPTY', 'EPERM'])
const FILESYSTEM_RETRY_ATTEMPTS = 10
const FILESYSTEM_RETRY_DELAY_MS = 100

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
  private wheelsDir: string
  private venvTransactionJournalPath: string
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
    this.wheelsDir = path.join(appRoot, 'plugins', 'wheels')
    this.venvTransactionJournalPath = path.join(
      appRoot,
      'environment',
      '.venv-install-transaction.json'
    )
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
      await this.recoverVenvTransaction()
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

    const runtimeLock = this.readBundledRuntimeLockIfPresent()
    const currentHash = this.calculateHash(source, runtimeLock)
    logger.info(`当前哈希: ${currentHash.substring(0, 8)}...`)

    const lastHash = this.loadHash()
    logger.info(`上次哈希: ${lastHash ? lastHash.substring(0, 8) + '...' : 'null'}`)

    const venvReady = this.isVenvReady(runtimeLock)
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
  private calculateHash(
    source: Exclude<DependencySource, 'missing'>,
    runtimeLock: BundledRuntimeLock | null
  ): string {
    const sourcePath = source === 'pyproject' ? this.pyprojectPath : this.requirementsPath
    const content = fs.readFileSync(sourcePath, 'utf-8')
    const manifestPath = path.join(this.wheelsDir, 'manifest.json')
    const runtimeLockPath = path.join(this.wheelsDir, 'runtime-lock.json')
    const lockedArtifactIdentity = runtimeLock
      ? `${fs.readFileSync(manifestPath, 'utf-8')}\n${fs.readFileSync(runtimeLockPath, 'utf-8')}`
      : 'no-bundled-runtime-lock'
    return crypto
      .createHash('sha256')
      .update(`${source}\n${content.trim()}\n${lockedArtifactIdentity}`)
      .digest('hex')
  }

  private isVenvReady(runtimeLock: BundledRuntimeLock | null = null): boolean {
    if (!fs.existsSync(this.venvPythonExe)) {
      return false
    }

    if (!this.ensureVenvPythonPathConfig()) {
      return false
    }

    const sitePackagesPath = path.join(this.venvPath, 'Lib', 'site-packages')
    if (!fs.existsSync(sitePackagesPath) || fs.readdirSync(sitePackagesPath).length === 0) {
      return false
    }
    return (
      runtimeLock == null ||
      this.hasExactLockedDistributions(sitePackagesPath, runtimeLock.host_runtime)
    )
  }

  private readBundledRuntimeLockIfPresent(): BundledRuntimeLock | null {
    if (!fs.existsSync(this.wheelsDir)) {
      if (requiresBundledRuntimeLock(this.appRoot)) {
        throw new Error('集成快照缺少随包 plugins/wheels，拒绝回退到在线依赖解析')
      }
      return null
    }
    const entries = fs.readdirSync(this.wheelsDir, { withFileTypes: true })
    const hasBundledArtifacts = entries.some(
      entry =>
        entry.isFile() &&
        (entry.name.toLowerCase().endsWith('.whl') ||
          entry.name === 'manifest.json' ||
          entry.name === 'runtime-lock.json')
    )
    if (!hasBundledArtifacts) {
      if (requiresBundledRuntimeLock(this.appRoot)) {
        throw new Error('集成快照的 plugins/wheels 为空或不完整，拒绝回退到在线依赖解析')
      }
      return null
    }
    return readAndVerifyBundledRuntimeLock(this.wheelsDir)
  }

  private normalizeDistributionName(name: string): string {
    return name
      .trim()
      .toLowerCase()
      .replace(/[-_.]+/g, '-')
  }

  private hasExactLockedDistributions(
    sitePackagesPath: string,
    expectedEntries: BundledRuntimeLockEntry[]
  ): boolean {
    try {
      const installed = new Map<string, string>()
      for (const entry of fs.readdirSync(sitePackagesPath, { withFileTypes: true })) {
        if (!entry.isDirectory() || !entry.name.toLowerCase().endsWith('.dist-info')) {
          continue
        }
        const metadataPath = path.join(sitePackagesPath, entry.name, 'METADATA')
        if (!fs.existsSync(metadataPath)) {
          return false
        }
        const metadata = fs.readFileSync(metadataPath, 'utf-8')
        const name = metadata.match(/^Name:\s*(.+?)\s*$/im)?.[1]
        const version = metadata.match(/^Version:\s*(.+?)\s*$/im)?.[1]
        if (!name || !version) {
          return false
        }
        const normalized = this.normalizeDistributionName(name)
        if (installed.has(normalized)) {
          return false
        }
        installed.set(normalized, version)
      }
      if (installed.size !== expectedEntries.length) {
        return false
      }
      return expectedEntries.every(
        item => installed.get(this.normalizeDistributionName(item.distribution)) === item.version
      )
    } catch (error) {
      logger.warn(`校验锁定虚拟环境失败: ${error}`)
      return false
    }
  }

  private ensureVenvPythonPathConfig(venvPath: string = this.venvPath): boolean {
    try {
      const sourceDir = path.dirname(this.pythonExe)
      const sourceName = fs.readdirSync(sourceDir).find(name => /^python\d+._pth$/i.test(name))

      if (!sourceName) {
        return true
      }

      const sourcePath = path.join(sourceDir, sourceName)
      const targetPath = path.join(venvPath, 'Scripts', sourceName)
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
    const runtimeLock = this.readBundledRuntimeLockIfPresent()
    if (runtimeLock != null) {
      try {
        onProgress?.(
          { progress: 20, description: '正在校验随包离线运行时锁...' },
          'bundled wheelhouse',
          0,
          1
        )
        await this.ensureUvReady()
        await this.installLockedHostRuntime(runtimeLock, progress => {
          onProgress?.(
            { progress, description: '正在从随包 wheelhouse 安装锁定宿主依赖...' },
            'bundled wheelhouse',
            0,
            1
          )
        })
        return { success: true }
      } catch (error) {
        return { success: false, error: error instanceof Error ? error.message : String(error) }
      }
    }

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

  private createOfflineEnvironment(): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      UV_NO_INDEX: '1',
      UV_NO_CONFIG: '1',
      UV_OFFLINE: '1',
    }
    for (const key of [
      'UV_INDEX',
      'UV_DEFAULT_INDEX',
      'UV_INDEX_URL',
      'UV_EXTRA_INDEX_URL',
      'PIP_INDEX_URL',
      'PIP_EXTRA_INDEX_URL',
    ]) {
      delete env[key]
    }
    return env
  }

  private async installLockedHostRuntime(
    runtimeLock: BundledRuntimeLock,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    const parentDir = path.dirname(this.venvPath)
    const stagingVenvPath = path.join(parentDir, `.venv-stage-${process.pid}-${Date.now()}`)
    if (fs.existsSync(stagingVenvPath)) {
      throw new Error(`锁定虚拟环境暂存目录已存在: ${stagingVenvPath}`)
    }

    try {
      onProgress?.(35)
      await runBoundedProcess(
        this.uvExe,
        [
          'venv',
          stagingVenvPath,
          '--python',
          this.pythonExe,
          '--no-config',
          '--no-python-downloads',
        ],
        {
          cwd: this.appRoot,
          env: this.createOfflineEnvironment(),
          timeoutMs: 5 * 60_000,
          label: 'uv venv (locked host runtime)',
        }
      )
      if (!this.ensureVenvPythonPathConfig(stagingVenvPath)) {
        throw new Error('锁定虚拟环境 Python 路径配置同步失败')
      }

      const stagingPython = path.join(stagingVenvPath, 'Scripts', 'python.exe')
      const wheelPaths = resolveLockedWheelPaths(this.wheelsDir, runtimeLock.host_runtime)
      if (wheelPaths.length === 0) {
        throw new Error('随包运行时锁没有 host_runtime wheel')
      }
      onProgress?.(55)
      await runBoundedProcess(
        this.uvExe,
        [
          'pip',
          'install',
          '--python',
          stagingPython,
          '--no-index',
          '--no-deps',
          '--no-config',
          '--no-python-downloads',
          ...wheelPaths,
        ],
        {
          cwd: this.appRoot,
          env: this.createOfflineEnvironment(),
          timeoutMs: 15 * 60_000,
          label: 'uv pip install (locked host runtime)',
          onStdout: chunk => logger.info(`locked host install: ${chunk.toString().trim()}`),
          onStderr: chunk => logger.info(`locked host install stderr: ${chunk.toString().trim()}`),
        }
      )

      onProgress?.(85)
      await this.validateLockedVenv(stagingVenvPath, runtimeLock)
      await this.promoteLockedVenv(stagingVenvPath, runtimeLock)
      onProgress?.(100)
    } finally {
      if (fs.existsSync(stagingVenvPath)) {
        try {
          await this.cleanupVenvTransactionPath(stagingVenvPath)
        } catch (cleanupError) {
          logger.warn(
            `锁定虚拟环境安装失败后，暂存目录清理仍受 Windows 文件锁阻塞；保留供下次恢复: ${cleanupError}`
          )
        }
      }
    }
  }

  private async validateLockedVenv(
    venvPath: string,
    runtimeLock: BundledRuntimeLock
  ): Promise<void> {
    const sitePackagesPath = path.join(venvPath, 'Lib', 'site-packages')
    if (!this.hasExactLockedDistributions(sitePackagesPath, runtimeLock.host_runtime)) {
      throw new Error('锁定虚拟环境的 distribution/version 集合与 host_runtime 不一致')
    }
    const pythonPath = path.join(venvPath, 'Scripts', 'python.exe')
    if (!fs.existsSync(pythonPath)) {
      throw new Error(`锁定虚拟环境 Python 不存在: ${pythonPath}`)
    }
    const expected = runtimeLock.host_runtime.map(item => ({
      name: item.distribution,
      version: item.version,
    }))
    const encodedExpected = Buffer.from(JSON.stringify(expected), 'utf-8').toString('base64')
    const validationScript = [
      'import base64, importlib.metadata as metadata, json, sys',
      'expected = {item["name"].lower().replace("_", "-").replace(".", "-"): item["version"] for item in json.loads(base64.b64decode(sys.argv[1]))}',
      'actual = {dist.metadata["Name"].lower().replace("_", "-").replace(".", "-"): dist.version for dist in metadata.distributions()}',
      'missing = {name: version for name, version in expected.items() if actual.get(name) != version}',
      'assert not missing, f"locked host metadata mismatch: {missing}"',
    ].join('; ')
    await runBoundedProcess(pythonPath, ['-I', '-c', validationScript, encodedExpected], {
      cwd: this.appRoot,
      env: this.createOfflineEnvironment(),
      timeoutMs: 2 * 60_000,
      label: 'locked host runtime validation',
    })
  }

  private async promoteLockedVenv(
    stagingVenvPath: string,
    runtimeLock: BundledRuntimeLock
  ): Promise<void> {
    const backupPath = path.join(
      path.dirname(this.venvPath),
      `.venv-backup-${process.pid}-${Date.now()}`
    )
    const journal = {
      schema_version: 1,
      phase: 'prepared',
      had_active_target: fs.existsSync(this.venvPath),
      active_path: this.venvPath,
      staging_path: stagingVenvPath,
      backup_path: backupPath,
    }
    writeJsonFileAtomically(this.venvTransactionJournalPath, journal)

    let oldMoved = false
    let newMoved = false
    let committed = false
    try {
      if (fs.existsSync(this.venvPath)) {
        await this.renameVenvTransactionPath(this.venvPath, backupPath)
        oldMoved = true
      }
      await this.renameVenvTransactionPath(stagingVenvPath, this.venvPath)
      newMoved = true
      await this.validateLockedVenv(this.venvPath, runtimeLock)
      journal.phase = 'committed'
      writeJsonFileAtomically(this.venvTransactionJournalPath, journal)
      committed = true
      if (oldMoved) {
        try {
          await this.cleanupVenvTransactionPath(backupPath)
        } catch (cleanupError) {
          logger.warn(`新虚拟环境已提交，但旧备份清理失败并保留供审计: ${cleanupError}`)
        }
      }
      fs.rmSync(this.venvTransactionJournalPath, { force: true })
    } catch (error) {
      if (committed) {
        const reason = error instanceof Error ? error.message : String(error)
        throw new Error(
          `新虚拟环境已验证并提交，但事务收尾失败；active 环境与 journal 均已保留: ${reason}`
        )
      }
      const rollbackErrors: string[] = []
      try {
        if (newMoved && fs.existsSync(this.venvPath)) {
          await this.removeVenvTransactionPath(this.venvPath, true)
        }
        if (oldMoved && fs.existsSync(backupPath)) {
          await this.renameVenvTransactionPath(backupPath, this.venvPath)
        }
        fs.rmSync(this.venvTransactionJournalPath, { force: true })
      } catch (rollbackError) {
        rollbackErrors.push(
          rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
        )
      }
      const reason = error instanceof Error ? error.message : String(error)
      if (rollbackErrors.length > 0) {
        throw new Error(
          `锁定虚拟环境切换失败且回滚不完整: ${reason}; ${rollbackErrors.join('; ')}; backup=${backupPath}`
        )
      }
      throw new Error(`锁定虚拟环境切换失败，旧环境已恢复: ${reason}`)
    }
  }

  private async recoverVenvTransaction(): Promise<void> {
    if (!fs.existsSync(this.venvTransactionJournalPath)) {
      return
    }
    const journal = JSON.parse(fs.readFileSync(this.venvTransactionJournalPath, 'utf-8')) as {
      schema_version: number
      phase: string
      had_active_target: boolean
      active_path: string
      staging_path: string
      backup_path: string
    }
    const parentDir = path.resolve(path.dirname(this.venvPath))
    const isTransactionPath = (candidate: string, prefix: string) =>
      path.dirname(path.resolve(candidate)) === parentDir &&
      path.basename(candidate).startsWith(prefix)
    if (
      journal.schema_version !== 1 ||
      !['prepared', 'committed'].includes(journal.phase) ||
      typeof journal.had_active_target !== 'boolean' ||
      path.resolve(journal.active_path) !== path.resolve(this.venvPath) ||
      !isTransactionPath(journal.staging_path, '.venv-stage-') ||
      !isTransactionPath(journal.backup_path, '.venv-backup-')
    ) {
      throw new Error('虚拟环境事务日志包含不安全路径，拒绝自动恢复')
    }

    if (journal.phase === 'committed') {
      if (!fs.existsSync(this.venvPath)) {
        throw new Error('已提交的虚拟环境事务缺少 active 环境')
      }
      if (fs.existsSync(journal.backup_path)) {
        try {
          await this.cleanupVenvTransactionPath(journal.backup_path)
        } catch (cleanupError) {
          logger.warn(`恢复已提交事务时无法清理旧虚拟环境备份: ${cleanupError}`)
        }
      }
    } else if (fs.existsSync(journal.backup_path)) {
      if (fs.existsSync(this.venvPath)) {
        const interruptedPath = path.join(
          parentDir,
          `.venv-interrupted-${process.pid}-${Date.now()}`
        )
        await this.renameVenvTransactionPath(this.venvPath, interruptedPath)
        await this.renameVenvTransactionPath(journal.backup_path, this.venvPath)
        await this.cleanupVenvTransactionPath(interruptedPath)
      } else {
        await this.renameVenvTransactionPath(journal.backup_path, this.venvPath)
      }
    } else if (!journal.had_active_target && fs.existsSync(this.venvPath)) {
      await this.removeVenvTransactionPath(this.venvPath, true)
    }
    if (fs.existsSync(journal.staging_path)) {
      await this.cleanupVenvTransactionPath(journal.staging_path)
    }
    fs.rmSync(this.venvTransactionJournalPath, { force: true })
    logger.warn(`已恢复未完成的虚拟环境事务 (phase=${journal.phase})`)
  }

  private async cleanupVenvTransactionPath(targetPath: string): Promise<void> {
    const parentDir = path.resolve(path.dirname(this.venvPath))
    if (
      path.dirname(path.resolve(targetPath)) !== parentDir ||
      path.resolve(targetPath) === path.resolve(this.venvPath)
    ) {
      throw new Error(`拒绝清理虚拟环境事务范围外路径: ${targetPath}`)
    }
    await this.removeVenvTransactionPath(targetPath, false)
  }

  private async renameVenvTransactionPath(sourcePath: string, targetPath: string): Promise<void> {
    await this.runFilesystemMutationWithRetry(() => fs.promises.rename(sourcePath, targetPath))
  }

  private async removeVenvTransactionPath(
    targetPath: string,
    allowActivePath: boolean
  ): Promise<void> {
    if (!allowActivePath && path.resolve(targetPath) === path.resolve(this.venvPath)) {
      throw new Error(`拒绝清理当前 active 虚拟环境: ${targetPath}`)
    }
    await this.runFilesystemMutationWithRetry(() =>
      fs.promises.rm(targetPath, { recursive: true, force: true })
    )
  }

  private async runFilesystemMutationWithRetry(operation: () => Promise<void>): Promise<void> {
    for (let attempt = 1; attempt <= FILESYSTEM_RETRY_ATTEMPTS; attempt += 1) {
      try {
        await operation()
        return
      } catch (error) {
        const code = error instanceof Error ? (error as NodeJS.ErrnoException).code : undefined
        if (
          !code ||
          !FILESYSTEM_RETRYABLE_ERROR_CODES.has(code) ||
          attempt >= FILESYSTEM_RETRY_ATTEMPTS
        ) {
          throw error
        }
        await this.waitForFilesystemRetry(attempt)
      }
    }
  }

  private async waitForFilesystemRetry(attempt: number): Promise<void> {
    await new Promise(resolve => setTimeout(resolve, FILESYSTEM_RETRY_DELAY_MS * attempt))
  }

  /**
   * 执行 uv sync 从 pyproject.toml 安装依赖
   * 通过 UV_INDEX_URL 环境变量传递镜像源
   */
  private async runUvSync(
    mirror: MirrorSource,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    const handleOutput = (chunk: Buffer) => {
      const output = chunk.toString().trim()
      logger.info(`uv sync: ${output}`)
      if (output.includes('Resolved')) onProgress?.(60)
      else if (output.includes('Prepared') || output.includes('Downloading')) onProgress?.(75)
      else if (output.includes('Installed') || output.includes('installed')) onProgress?.(95)
    }
    await runBoundedProcess(
      this.uvExe,
      ['sync', '--python', this.pythonExe, '--no-install-project', '--no-dev', '--no-sources'],
      {
        cwd: this.appRoot,
        env: { ...process.env, UV_INDEX_URL: mirror.url },
        timeoutMs: 20 * 60_000,
        label: 'uv sync',
        onStdout: handleOutput,
        onStderr: handleOutput,
      }
    )
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

  private async runUvVenv(mirror: MirrorSource): Promise<void> {
    await runBoundedProcess(
      this.uvExe,
      ['venv', this.venvPath, '--python', this.pythonExe, '--no-python-downloads'],
      {
        cwd: this.appRoot,
        env: { ...process.env, UV_INDEX_URL: mirror.url },
        timeoutMs: 5 * 60_000,
        label: 'uv venv',
        onStdout: chunk => logger.info(`uv venv: ${chunk.toString().trim()}`),
        onStderr: chunk => logger.info(`uv venv stderr: ${chunk.toString().trim()}`),
      }
    )
  }

  private async runUvPipInstall(
    mirror: MirrorSource,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    const handleOutput = (prefix: string, data: Buffer) => {
      const output = data.toString().trim()
      logger.info(`${prefix}: ${output}`)
      if (output.includes('Resolved')) onProgress?.(65)
      else if (output.includes('Prepared') || output.includes('Downloading')) onProgress?.(80)
      else if (output.includes('Installed') || output.includes('installed')) onProgress?.(95)
    }
    await runBoundedProcess(
      this.uvExe,
      ['pip', 'install', '--python', this.venvPythonExe, '-r', this.requirementsPath],
      {
        cwd: this.appRoot,
        env: { ...process.env, UV_INDEX_URL: mirror.url },
        timeoutMs: 20 * 60_000,
        label: 'uv pip install requirements',
        onStdout: chunk => handleOutput('uv pip install', chunk),
        onStderr: chunk => handleOutput('uv pip install stderr', chunk),
      }
    )
  }
}
