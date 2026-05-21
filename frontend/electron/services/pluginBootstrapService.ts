/**
 * 插件预装服务
 * 在首次初始化后，将集中声明的推荐插件包安装到 plugins/pypi/site-packages。
 */

import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import { spawn } from 'child_process'

import { MirrorService, MirrorSource } from './mirrorService'
import {
  MirrorRotationService,
  NetworkOperationCallback,
  NetworkOperationProgress,
} from './mirrorRotationService'
import { getLogger } from './logger'

const logger = getLogger('插件预装服务')

const ENTRY_POINT_GROUPS = ['auto_mas.plugins', 'automas.plugins'] as const
const PYPROJECT_BOOTSTRAP_SECTION = '[tool.auto-mas.plugin-bootstrap]'

interface DeclaredBootstrapPackage {
  name: string
  installSpec: string
  displayLabel: string
  version?: string
  specifier?: string
}

export interface PluginBootstrapCheckResult {
  packages: string[]
  currentHash: string
  lastHash?: string
  needsInstall: boolean
}

export interface PluginBootstrapWarning {
  packageName: string
  message: string
  kind: 'install-failed' | 'missing-entry-point'
}

export interface PluginBootstrapState {
  hash: string
  packages: string[]
  installedPackages: string[]
  failedPackages: string[]
  warnings: PluginBootstrapWarning[]
  updatedAt: string
}

export interface PluginBootstrapProgress {
  stage: 'check' | 'install'
  progress: number
  message: string
  details?: {
    checkInfo?: PluginBootstrapCheckResult
    currentMirror?: string
    mirrorProgress?: { current: number; total: number }
    operationDesc?: string
    currentPackage?: string
    failedPackages?: string[]
    warnings?: PluginBootstrapWarning[]
  }
}

export type PluginBootstrapProgressCallback = (progress: PluginBootstrapProgress) => void

export interface PluginBootstrapInstallResult {
  success: boolean
  skipped?: boolean
  installedPackages: string[]
  failedPackages: string[]
  warnings: PluginBootstrapWarning[]
  error?: string
  summary: string
}

export class PluginBootstrapService {
  private appRoot: string
  private uvExe: string
  private pluginsDir: string
  private pluginTargetDir: string
  private stateFilePath: string
  private pyprojectPath: string
  private mirrorService: MirrorService
  private rotationService: MirrorRotationService

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.uvExe = path.join(appRoot, 'environment', 'python', 'Scripts', 'uv.exe')
    this.pluginsDir = path.join(appRoot, 'plugins')
    this.pluginTargetDir = path.join(appRoot, 'plugins', 'pypi', 'site-packages')
    this.stateFilePath = path.join(appRoot, 'environment', '.plugin_bootstrap_state.json')
    this.pyprojectPath = path.join(appRoot, 'pyproject.toml')
    this.mirrorService = mirrorService
    this.rotationService = new MirrorRotationService()
  }

  async installPackages(
    onProgress?: PluginBootstrapProgressCallback,
    selectedMirror?: string,
    forceInstall: boolean = false,
  ): Promise<PluginBootstrapInstallResult> {
    try {
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: '正在检查插件预装状态...',
        details: {},
      })

      const checkResult = this.checkBootstrapState()
      onProgress?.({
        stage: 'check',
        progress: 100,
        message: '插件预装状态检查完成',
        details: {
          checkInfo: checkResult,
        },
      })

      if (!forceInstall && !checkResult.needsInstall) {
        const state = this.loadState()
        logger.info('插件预装声明未变化，跳过本轮预装')
        return {
          success: true,
          skipped: true,
          installedPackages: state?.installedPackages || [],
          failedPackages: state?.failedPackages || [],
          warnings: state?.warnings || [],
          summary: '插件预装声明未变化，已跳过',
        }
      }

      if (checkResult.packages.length === 0) {
        const emptyState: PluginBootstrapState = {
          hash: checkResult.currentHash,
          packages: [],
          installedPackages: [],
          failedPackages: [],
          warnings: [],
          updatedAt: new Date().toISOString(),
        }
        this.saveState(emptyState)
        logger.info('插件预装列表为空，跳过安装')
        return {
          success: true,
          skipped: true,
          installedPackages: [],
          failedPackages: [],
          warnings: [],
          summary: '插件预装列表为空，已跳过',
        }
      }

      await this.ensureUvReady()
      this.ensurePluginTargetDir()

      const installedPackages: string[] = []
      const failedPackages: string[] = []
      const warnings: PluginBootstrapWarning[] = []

      const declaredPackages = this.loadDeclaredPackageSpecs()

      for (let index = 0; index < declaredPackages.length; index += 1) {
        const declaredPackage = declaredPackages[index]
        const packageName = declaredPackage.displayLabel
        const baseProgress = Math.floor((index / declaredPackages.length) * 100)

        onProgress?.({
          stage: 'install',
          progress: baseProgress,
          message: `正在预装插件包: ${packageName}`,
          details: {
            currentPackage: packageName,
            failedPackages: [...failedPackages],
            warnings: [...warnings],
          },
        })

        const installResult = await this.installSinglePackage(
          declaredPackage,
          (operationProgress, mirrorName, mirrorIndex, totalMirrors) => {
            const packageSpan = 100 / declaredPackages.length
            const progress = Math.min(
              99,
              Math.floor(index * packageSpan + (operationProgress.progress / 100) * packageSpan),
            )
            onProgress?.({
              stage: 'install',
              progress,
              message: operationProgress.description,
              details: {
                currentPackage: packageName,
                currentMirror: mirrorName,
                mirrorProgress: { current: mirrorIndex + 1, total: totalMirrors },
                operationDesc: operationProgress.description,
                failedPackages: [...failedPackages],
                warnings: [...warnings],
              },
            })
          },
          selectedMirror,
        )

        if (!installResult.success) {
          failedPackages.push(packageName)
          warnings.push({
            packageName,
            kind: 'install-failed',
            message: installResult.error || '未知错误',
          })
          logger.warn(`插件预装失败，将继续后续流程: package=${packageName}, error=${installResult.error}`)
          continue
        }

        installedPackages.push(packageName)
        if (!installResult.hasPluginEntryPoint) {
          const warning: PluginBootstrapWarning = {
            packageName,
            kind: 'missing-entry-point',
            message: '安装成功，但未发现 auto_mas.plugins / automas.plugins 入口点',
          }
          warnings.push(warning)
          logger.warn(`插件预装完成但未发现插件入口点: package=${packageName}`)
        } else {
          logger.info(`插件预装完成: package=${packageName}`)
        }
      }

      const state: PluginBootstrapState = {
        hash: checkResult.currentHash,
        packages: [...checkResult.packages],
        installedPackages,
        failedPackages,
        warnings,
        updatedAt: new Date().toISOString(),
      }
      this.saveState(state)

      const summary =
        failedPackages.length > 0
          ? `插件预装完成，失败 ${failedPackages.length} 个: ${failedPackages.join(', ')}`
          : '插件预装完成'

      onProgress?.({
        stage: 'install',
        progress: 100,
        message: summary,
        details: {
          failedPackages,
          warnings,
        },
      })

      return {
        success: true,
        installedPackages,
        failedPackages,
        warnings,
        summary,
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`插件预装阶段失败: ${errorMsg}`)
      return {
        success: false,
        installedPackages: [],
        failedPackages: [],
        warnings: [],
        error: errorMsg,
        summary: `插件预装阶段失败: ${errorMsg}`,
      }
    }
  }

  private checkBootstrapState(): PluginBootstrapCheckResult {
    const declaredPackages = this.loadDeclaredPackageSpecs()
    const packages = declaredPackages.map(item => item.displayLabel)
    const currentHash = this.calculateHash(declaredPackages)
    const lastState = this.loadState()
    const lastHash = lastState?.hash

    return {
      packages,
      currentHash,
      lastHash,
      needsInstall: lastHash == null || lastHash !== currentHash,
    }
  }

  private calculateHash(packages: DeclaredBootstrapPackage[]): string {
    const normalized = packages.map(item => ({
      name: item.name,
      version: item.version || '',
      specifier: item.specifier || '',
      installSpec: item.installSpec,
    }))
    return crypto.createHash('sha256').update(JSON.stringify({ packages: normalized })).digest('hex')
  }

  private loadDeclaredPackageSpecs(): DeclaredBootstrapPackage[] {
    if (!fs.existsSync(this.pyprojectPath)) {
      logger.warn(`pyproject.toml 不存在，跳过插件预装声明读取: ${this.pyprojectPath}`)
      return []
    }

    try {
      const content = fs.readFileSync(this.pyprojectPath, 'utf-8')
      const sectionBody = this.extractBootstrapSection(content)
      if (sectionBody == null) {
        return []
      }
      return this.extractDeclaredPackages(sectionBody)
    } catch (error) {
      logger.warn(`读取 pyproject 插件预装声明失败，已按空列表处理: ${error}`)
      return []
    }
  }

  private extractBootstrapSection(content: string): string | null {
    const markerIndex = content.indexOf(PYPROJECT_BOOTSTRAP_SECTION)
    if (markerIndex < 0) {
      return null
    }

    const sectionStart = markerIndex + PYPROJECT_BOOTSTRAP_SECTION.length
    const rest = content.slice(sectionStart)
    const nextSectionMatch = rest.match(/^\s*\[[^\]]+\]\s*$/m)
    const sectionEnd = nextSectionMatch?.index ?? rest.length
    return rest.slice(0, sectionEnd)
  }

  private extractDeclaredPackages(sectionBody: string): DeclaredBootstrapPackage[] {
    const packagesMatch = sectionBody.match(/^\s*packages\s*=\s*\[([\s\S]*?)\]/m)
    if (!packagesMatch) {
      return []
    }

    const arrayBody = packagesMatch[1]
    const items = this.splitTopLevelArrayItems(arrayBody)
    const packages: DeclaredBootstrapPackage[] = []
    const seen = new Set<string>()

    for (const rawItem of items) {
      const parsed = this.parseDeclaredPackageItem(rawItem)
      if (parsed == null) {
        continue
      }
      const dedupeKey = `${parsed.name}@@${parsed.version || ''}@@${parsed.specifier || ''}`
      if (seen.has(dedupeKey)) {
        continue
      }
      seen.add(dedupeKey)
      packages.push(parsed)
    }

    return packages
  }

  private splitTopLevelArrayItems(arrayBody: string): string[] {
    const items: string[] = []
    let current = ''
    let braceDepth = 0
    let bracketDepth = 0
    let inSingleQuote = false
    let inDoubleQuote = false
    let escaping = false

    for (const ch of arrayBody) {
      if (escaping) {
        current += ch
        escaping = false
        continue
      }

      if ((inSingleQuote || inDoubleQuote) && ch === '\\') {
        current += ch
        escaping = true
        continue
      }

      if (!inSingleQuote && ch === '"') {
        inDoubleQuote = !inDoubleQuote
        current += ch
        continue
      }

      if (!inDoubleQuote && ch === "'") {
        inSingleQuote = !inSingleQuote
        current += ch
        continue
      }

      if (!inSingleQuote && !inDoubleQuote) {
        if (ch === '{') {
          braceDepth += 1
        } else if (ch === '}') {
          braceDepth = Math.max(0, braceDepth - 1)
        } else if (ch === '[') {
          bracketDepth += 1
        } else if (ch === ']') {
          bracketDepth = Math.max(0, bracketDepth - 1)
        } else if (ch === ',' && braceDepth === 0 && bracketDepth === 0) {
          const trimmed = current.trim()
          if (trimmed) {
            items.push(trimmed)
          }
          current = ''
          continue
        }
      }

      current += ch
    }

    const trimmed = current.trim()
    if (trimmed) {
      items.push(trimmed)
    }

    return items
  }

  private parseDeclaredPackageItem(rawItem: string): DeclaredBootstrapPackage | null {
    const item = rawItem.trim()
    if (!item) {
      return null
    }

    if (
      (item.startsWith('"') && item.endsWith('"')) ||
      (item.startsWith("'") && item.endsWith("'"))
    ) {
      const value = this.decodeTomlStringLiteral(item)
      const name = value.trim()
      if (!name) {
        return null
      }
      return {
        name,
        installSpec: name,
        displayLabel: name,
      }
    }

    if (item.startsWith('{') && item.endsWith('}')) {
      return this.parseInlineTablePackage(item)
    }

    logger.warn(`无法识别的插件预装声明，已跳过: ${item}`)
    return null
  }

  private parseInlineTablePackage(rawTable: string): DeclaredBootstrapPackage | null {
    const body = rawTable.slice(1, -1).trim()
    if (!body) {
      return null
    }

    const entries = this.splitTopLevelArrayItems(body)
    const fields = new Map<string, string>()

    for (const entry of entries) {
      const eqIndex = entry.indexOf('=')
      if (eqIndex <= 0) {
        continue
      }
      const key = entry.slice(0, eqIndex).trim()
      const rawValue = entry.slice(eqIndex + 1).trim()
      if (!key || !rawValue) {
        continue
      }
      fields.set(key, this.decodeTomlStringLiteral(rawValue))
    }

    const name = (fields.get('name') || '').trim()
    const version = (fields.get('version') || '').trim()
    const specifier = (fields.get('specifier') || '').trim()

    if (!name) {
      logger.warn(`插件预装对象声明缺少 name，已跳过: ${rawTable}`)
      return null
    }

    if (version && specifier) {
      logger.warn(`插件预装对象同时声明 version 和 specifier，将优先使用 specifier: ${name}`)
    }

    const effectiveSpecifier = specifier || (version ? `==${version}` : '')
    const installSpec = effectiveSpecifier ? `${name}${effectiveSpecifier}` : name

    return {
      name,
      version: version || undefined,
      specifier: specifier || undefined,
      installSpec,
      displayLabel: installSpec,
    }
  }

  private decodeTomlStringLiteral(rawValue: string): string {
    const value = rawValue.trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      const inner = value.slice(1, -1)
      return inner
        .replace(/\\n/g, '\n')
        .replace(/\\r/g, '\r')
        .replace(/\\t/g, '\t')
        .replace(/\\"/g, '"')
        .replace(/\\'/g, "'")
        .replace(/\\\\/g, '\\')
        .trim()
    }
    return value
  }

  private loadState(): PluginBootstrapState | null {
    try {
      if (!fs.existsSync(this.stateFilePath)) {
        return null
      }
      return JSON.parse(fs.readFileSync(this.stateFilePath, 'utf-8')) as PluginBootstrapState
    } catch (error) {
      logger.warn(`读取插件预装状态文件失败: ${error}`)
      return null
    }
  }

  private saveState(state: PluginBootstrapState): void {
    try {
      const dir = path.dirname(this.stateFilePath)
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true })
      }
      fs.writeFileSync(this.stateFilePath, JSON.stringify(state, null, 2), 'utf-8')
    } catch (error) {
      logger.warn(`写入插件预装状态文件失败: ${error}`)
    }
  }

  private async ensureUvReady(): Promise<void> {
    if (!fs.existsSync(this.uvExe)) {
      throw new Error('uv.exe 不存在，请先完成环境初始化')
    }
  }

  private ensurePluginTargetDir(): void {
    if (!fs.existsSync(this.pluginsDir)) {
      fs.mkdirSync(this.pluginsDir, { recursive: true })
    }
    if (!fs.existsSync(this.pluginTargetDir)) {
      fs.mkdirSync(this.pluginTargetDir, { recursive: true })
    }
  }

  private async installSinglePackage(
    declaredPackage: DeclaredBootstrapPackage,
    onProgress?: (
      progress: NetworkOperationProgress,
      mirrorName: string,
      mirrorIndex: number,
      totalMirrors: number,
    ) => void,
    selectedMirror?: string,
  ): Promise<{ success: boolean; error?: string; hasPluginEntryPoint?: boolean }> {
    const mirrors = this.mirrorService.getMirrors('pip_mirror')
    const packageLabel = declaredPackage.displayLabel

    const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      try {
        onOpProgress({ progress: 10, description: `正在通过 ${mirror.name} 安装 ${packageLabel}...` })
        await this.runUvInstall(declaredPackage, mirror, progress => {
          onOpProgress({
            progress,
            description: `正在安装 ${packageLabel}...`,
          })
        })

        onOpProgress({ progress: 100, description: `插件包安装完成: ${packageLabel}` })
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
          rotationProgress.totalMirrors,
        )
      },
      selectedMirror,
    )

    if (!result.success) {
      return { success: false, error: result.error }
    }

    return {
      success: true,
      hasPluginEntryPoint: this.hasPluginEntryPoint(declaredPackage.name),
    }
  }

  private runUvInstall(
    declaredPackage: DeclaredBootstrapPackage,
    mirror: MirrorSource,
    onProgress?: (progress: number) => void,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const proc = spawn(
        this.uvExe,
        [
          'pip',
          'install',
          declaredPackage.installSpec,
          '--target',
          this.pluginTargetDir,
          '--upgrade',
          '--index-url',
          mirror.url,
        ],
        {
          cwd: this.appRoot,
          stdio: 'pipe',
        },
      )

      let stderrData = ''
      let stdoutData = ''

      proc.stdout?.on('data', data => {
        const output = data.toString().trim()
        stdoutData += output
        logger.info(`plugin bootstrap stdout: ${output}`)
      })

      proc.stderr?.on('data', data => {
        const output = data.toString().trim()
        stderrData += output
        logger.info(`plugin bootstrap stderr: ${output}`)

        if (output.includes('Resolved')) {
          onProgress?.(35)
        } else if (output.includes('Prepared') || output.includes('Downloading')) {
          onProgress?.(60)
        } else if (output.includes('Installed') || output.includes('installed')) {
          onProgress?.(90)
        }
      })

      proc.on('close', code => {
        if (code === 0) {
          resolve()
          return
        }
        reject(
          new Error(
            `uv pip install 失败，退出码: ${code}\nstderr: ${stderrData || stdoutData || '未知错误'}`,
          ),
        )
      })

      proc.on('error', reject)
    })
  }

  private hasPluginEntryPoint(packageName: string): boolean {
    const normalizedPackageName = this.normalizeDistributionName(packageName)
    if (!fs.existsSync(this.pluginTargetDir)) {
      return false
    }

    const entries = fs.readdirSync(this.pluginTargetDir, { withFileTypes: true })
    const matchedDistInfos = entries.filter(entry => {
      if (!entry.isDirectory() || !entry.name.endsWith('.dist-info')) {
        return false
      }
      const distName = this.normalizeDistributionName(entry.name.replace(/\.dist-info$/i, ''))
      return (
        distName === normalizedPackageName ||
        distName.startsWith(`${normalizedPackageName}-`) ||
        distName.startsWith(`${normalizedPackageName}_`)
      )
    })

    for (const distInfo of matchedDistInfos) {
      const entryPointsPath = path.join(this.pluginTargetDir, distInfo.name, 'entry_points.txt')
      if (!fs.existsSync(entryPointsPath)) {
        continue
      }
      const content = fs.readFileSync(entryPointsPath, 'utf-8')
      if (ENTRY_POINT_GROUPS.some(group => content.includes(`[${group}]`))) {
        return true
      }
    }

    return false
  }

  private normalizeDistributionName(name: string): string {
    return String(name || '')
      .trim()
      .toLowerCase()
      .replace(/[-.]+/g, '_')
  }
}
