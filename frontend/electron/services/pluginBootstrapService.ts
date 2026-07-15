/**
 * Plugin bootstrap service.
 *
 * Installs required system plugin packages and optional declared bootstrap
 * packages into plugins/pypi/site-packages.
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

const logger = getLogger('plugin bootstrap service')

const ENTRY_POINT_GROUPS = ['auto_mas.plugins', 'automas.plugins'] as const
const PYPROJECT_BOOTSTRAP_SECTION = '[tool.auto-mas.plugin-bootstrap]'

interface DeclaredBootstrapPackage {
  name: string
  installSpec: string
  displayLabel: string
  version?: string
  specifier?: string
}

const SYSTEM_BOOTSTRAP_PACKAGES: DeclaredBootstrapPackage[] = [
  {
    name: 'auto-mas-core',
    installSpec: 'auto-mas-core>=5.2.0',
    displayLabel: 'auto-mas-core>=5.2.0',
    specifier: '>=5.2.0',
  },
]

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
    this.uvExe = path.join(appRoot, 'environment', 'python', 'Scripts', 'uv.md.exe')
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
    forceInstall: boolean = false
  ): Promise<PluginBootstrapInstallResult> {
    try {
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: 'Checking plugin bootstrap state...',
        details: {},
      })

      const checkResult = this.checkBootstrapState()
      onProgress?.({
        stage: 'check',
        progress: 100,
        message: 'Plugin bootstrap state check complete',
        details: {
          checkInfo: checkResult,
        },
      })

      if (!forceInstall && !checkResult.needsInstall) {
        const state = this.loadState()
        logger.info(
          'Plugin bootstrap state is unchanged and system packages are present, skipping install'
        )
        return {
          success: true,
          skipped: true,
          installedPackages: state?.installedPackages || [],
          failedPackages: state?.failedPackages || [],
          warnings: state?.warnings || [],
          summary: 'Plugin bootstrap state is unchanged, skipped',
        }
      }

      await this.ensureUvReady()
      this.ensurePluginTargetDir()

      const installedPackages: string[] = []
      const failedPackages: string[] = []
      const warnings: PluginBootstrapWarning[] = []

      const systemResult = await this.installSystemPackages(
        installedPackages,
        failedPackages,
        warnings,
        onProgress,
        selectedMirror
      )
      if (!systemResult.success) {
        return {
          success: false,
          installedPackages,
          failedPackages,
          warnings,
          error: systemResult.error,
          summary: systemResult.error || 'System plugin bootstrap failed',
        }
      }

      const declaredPackages = this.loadDeclaredPackageSpecs()
      await this.installDeclaredPackages(
        declaredPackages,
        installedPackages,
        failedPackages,
        warnings,
        onProgress,
        selectedMirror
      )
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
          ? `Plugin bootstrap complete with ${failedPackages.length} failed package(s): ${failedPackages.join(', ')}`
          : 'Plugin bootstrap complete'

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
      logger.error(`Plugin bootstrap failed: ${errorMsg}`)
      return {
        success: false,
        installedPackages: [],
        failedPackages: [],
        warnings: [],
        error: errorMsg,
        summary: `Plugin bootstrap failed: ${errorMsg}`,
      }
    }
  }

  private checkBootstrapState(): PluginBootstrapCheckResult {
    const declaredPackages = this.loadDeclaredPackageSpecs()
    const allPackages = this.getAllBootstrapPackages(declaredPackages)
    const packages = allPackages.map(item => item.displayLabel)
    const currentHash = this.calculateHash(allPackages)
    const lastState = this.loadState()
    const lastHash = lastState?.hash
    const hasFailedPackages = (lastState?.failedPackages.length || 0) > 0

    return {
      packages,
      currentHash,
      lastHash,
      needsInstall:
        !this.areSystemPackagesInstalled() ||
        hasFailedPackages ||
        lastHash == null ||
        lastHash !== currentHash,
    }
  }

  private getAllBootstrapPackages(
    declaredPackages: DeclaredBootstrapPackage[]
  ): DeclaredBootstrapPackage[] {
    const result: DeclaredBootstrapPackage[] = []
    const seen = new Set<string>()

    for (const item of [...SYSTEM_BOOTSTRAP_PACKAGES, ...declaredPackages]) {
      const key = this.normalizeDistributionName(item.name)
      if (!key || seen.has(key)) {
        continue
      }
      seen.add(key)
      result.push(item)
    }

    return result
  }

  private calculateHash(packages: DeclaredBootstrapPackage[]): string {
    const normalized = packages.map(item => ({
      name: item.name,
      version: item.version || '',
      specifier: item.specifier || '',
      installSpec: item.installSpec,
    }))
    return crypto
      .createHash('sha256')
      .update(JSON.stringify({ packages: normalized }))
      .digest('hex')
  }

  private async installSystemPackages(
    installedPackages: string[],
    failedPackages: string[],
    warnings: PluginBootstrapWarning[],
    onProgress?: PluginBootstrapProgressCallback,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string }> {
    for (let index = 0; index < SYSTEM_BOOTSTRAP_PACKAGES.length; index += 1) {
      const systemPackage = SYSTEM_BOOTSTRAP_PACKAGES[index]
      const packageName = systemPackage.displayLabel

      if (this.isSystemPackageInstalled(systemPackage)) {
        installedPackages.push(packageName)
        logger.info(`System plugin package already installed: ${packageName}`)
        continue
      }

      onProgress?.({
        stage: 'install',
        progress: Math.floor((index / Math.max(1, SYSTEM_BOOTSTRAP_PACKAGES.length)) * 20),
        message: `Installing required system plugin package: ${packageName}`,
        details: {
          currentPackage: packageName,
          failedPackages: [...failedPackages],
          warnings: [...warnings],
        },
      })

      const installResult = await this.installSinglePackage(
        this.withResolvedSystemInstallSpec(systemPackage),
        (operationProgress, mirrorName, mirrorIndex, totalMirrors) => {
          onProgress?.({
            stage: 'install',
            progress: Math.min(25, Math.floor((operationProgress.progress / 100) * 25)),
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
        selectedMirror
      )

      if (!installResult.success) {
        failedPackages.push(packageName)
        const message = installResult.error || 'Unknown error'
        warnings.push({
          packageName,
          kind: 'install-failed',
          message,
        })
        return {
          success: false,
          error: `Required system plugin package failed to install: ${packageName}. ${message}`,
        }
      }

      if (!installResult.hasPluginEntryPoint) {
        const message =
          'Installed successfully, but no auto_mas.plugins / automas.plugins entry point was found'
        failedPackages.push(packageName)
        warnings.push({
          packageName,
          kind: 'missing-entry-point',
          message,
        })
        return {
          success: false,
          error: `Required system plugin package has no plugin entry point: ${packageName}`,
        }
      }

      installedPackages.push(packageName)
      logger.info(`System plugin package installed: ${packageName}`)
    }

    return { success: true }
  }

  private withResolvedSystemInstallSpec(
    systemPackage: DeclaredBootstrapPackage
  ): DeclaredBootstrapPackage {
    if (systemPackage.name !== 'auto-mas-core') {
      return systemPackage
    }

    const localCoreProject = path.join(this.appRoot, 'repo', 'plugins', 'auto_mas_core')
    if (!fs.existsSync(path.join(localCoreProject, 'pyproject.toml'))) {
      return systemPackage
    }

    logger.info(`Using local auto-mas-core project for system bootstrap: ${localCoreProject}`)
    return {
      ...systemPackage,
      installSpec: localCoreProject,
      displayLabel: systemPackage.displayLabel,
    }
  }

  private async installDeclaredPackages(
    declaredPackages: DeclaredBootstrapPackage[],
    installedPackages: string[],
    failedPackages: string[],
    warnings: PluginBootstrapWarning[],
    onProgress?: PluginBootstrapProgressCallback,
    selectedMirror?: string
  ): Promise<void> {
    for (let index = 0; index < declaredPackages.length; index += 1) {
      const declaredPackage = declaredPackages[index]
      const packageName = declaredPackage.displayLabel
      const baseProgress = 25 + Math.floor((index / Math.max(1, declaredPackages.length)) * 70)

      onProgress?.({
        stage: 'install',
        progress: baseProgress,
        message: `Installing bootstrap plugin package: ${packageName}`,
        details: {
          currentPackage: packageName,
          failedPackages: [...failedPackages],
          warnings: [...warnings],
        },
      })

      const installResult = await this.installSinglePackage(
        declaredPackage,
        (operationProgress, mirrorName, mirrorIndex, totalMirrors) => {
          const packageSpan = 70 / Math.max(1, declaredPackages.length)
          const progress = Math.min(
            99,
            Math.floor(25 + index * packageSpan + (operationProgress.progress / 100) * packageSpan)
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
        selectedMirror
      )

      if (!installResult.success) {
        failedPackages.push(packageName)
        warnings.push({
          packageName,
          kind: 'install-failed',
          message: installResult.error || 'Unknown error',
        })
        logger.warn(
          `Plugin bootstrap install failed and will be retried later: package=${packageName}, error=${installResult.error}`
        )
        continue
      }

      if (!installResult.hasPluginEntryPoint) {
        failedPackages.push(packageName)
        const warning: PluginBootstrapWarning = {
          packageName,
          kind: 'missing-entry-point',
          message:
            'Installed successfully, but no auto_mas.plugins / automas.plugins entry point was found',
        }
        warnings.push(warning)
        logger.warn(`Plugin bootstrap package has no plugin entry point: package=${packageName}`)
      } else {
        installedPackages.push(packageName)
        logger.info(`Plugin bootstrap install complete: package=${packageName}`)
      }
    }
  }

  private loadDeclaredPackageSpecs(): DeclaredBootstrapPackage[] {
    if (!fs.existsSync(this.pyprojectPath)) {
      logger.warn(
        `pyproject.toml does not exist, skipping declared plugin bootstrap packages: ${this.pyprojectPath}`
      )
      return []
    }

    try {
      const content = fs.readFileSync(this.pyprojectPath, 'utf-8')
      const sectionBody = this.extractBootstrapSection(content)
      if (sectionBody == null) {
        logger.warn(
          `Missing ${PYPROJECT_BOOTSTRAP_SECTION}, skipping declared plugin bootstrap packages`
        )
        return []
      }
      return this.extractDeclaredPackages(sectionBody)
    } catch (error) {
      logger.warn(`Failed to read pyproject plugin bootstrap packages; using empty list: ${error}`)
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
      const dedupeKey = this.normalizeDistributionName(parsed.name)
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
      const name = this.decodeTomlStringLiteral(item).trim()
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

    logger.warn(`Unrecognized plugin bootstrap package declaration, skipped: ${item}`)
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
      logger.warn(`Plugin bootstrap package object is missing name, skipped: ${rawTable}`)
      return null
    }

    if (version && specifier) {
      logger.warn(
        `Plugin bootstrap package declares both version and specifier; using specifier: ${name}`
      )
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
      logger.warn(`Failed to read plugin bootstrap state file: ${error}`)
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
      logger.warn(`Failed to write plugin bootstrap state file: ${error}`)
    }
  }

  private async ensureUvReady(): Promise<void> {
    if (!fs.existsSync(this.uvExe)) {
      throw new Error('uv.md.exe does not exist; complete environment initialization first')
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
      totalMirrors: number
    ) => void,
    selectedMirror?: string
  ): Promise<{ success: boolean; error?: string; hasPluginEntryPoint?: boolean }> {
    const mirrors = this.mirrorService.getMirrors('pip_mirror')
    const packageLabel = declaredPackage.displayLabel

    const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      try {
        onOpProgress({
          progress: 10,
          description: `Installing ${packageLabel} from ${mirror.name}...`,
        })
        await this.runUvInstall(declaredPackage, mirror, progress => {
          onOpProgress({
            progress,
            description: `Installing ${packageLabel}...`,
          })
        })

        onOpProgress({ progress: 100, description: `Package install complete: ${packageLabel}` })
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

    return {
      success: true,
      hasPluginEntryPoint: this.hasPluginEntryPoint(declaredPackage.name),
    }
  }

  private runUvInstall(
    declaredPackage: DeclaredBootstrapPackage,
    mirror: MirrorSource,
    onProgress?: (progress: number) => void
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
        }
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
            `uv pip install failed, exit code: ${code}\nstderr: ${stderrData || stdoutData || 'unknown error'}`
          )
        )
      })

      proc.on('error', reject)
    })
  }

  private areSystemPackagesInstalled(): boolean {
    return SYSTEM_BOOTSTRAP_PACKAGES.every(item => this.isSystemPackageInstalled(item))
  }

  private isSystemPackageInstalled(systemPackage: DeclaredBootstrapPackage): boolean {
    if (!this.hasPluginEntryPoint(systemPackage.name)) {
      return false
    }

    const minimumVersion = this.parseMinimumVersion(systemPackage.specifier)
    if (minimumVersion == null) {
      return true
    }

    const installedVersion = this.getInstalledDistributionVersion(systemPackage.name)
    if (installedVersion == null) {
      return false
    }

    return this.compareVersions(installedVersion, minimumVersion) >= 0
  }

  private hasPluginEntryPoint(packageName: string): boolean {
    const matchedDistInfos = this.findDistributionInfoDirs(packageName)

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

  private getInstalledDistributionVersion(packageName: string): string | null {
    const distInfo = this.findDistributionInfoDirs(packageName)[0]
    if (distInfo == null) {
      return null
    }

    const metadataPath = path.join(this.pluginTargetDir, distInfo.name, 'METADATA')
    if (fs.existsSync(metadataPath)) {
      const metadata = fs.readFileSync(metadataPath, 'utf-8')
      const versionMatch = metadata.match(/^Version:\s*(.+)$/m)
      if (versionMatch) {
        return versionMatch[1].trim()
      }
    }

    const normalizedPackageName = this.normalizeDistributionName(packageName)
    const normalizedDistName = this.normalizeDistributionName(
      distInfo.name.replace(/\.dist-info$/i, '')
    )
    const prefix = `${normalizedPackageName}_`
    if (normalizedDistName.startsWith(prefix)) {
      return normalizedDistName.slice(prefix.length)
    }

    return null
  }

  private findDistributionInfoDirs(packageName: string): fs.Dirent[] {
    const normalizedPackageName = this.normalizeDistributionName(packageName)
    if (!fs.existsSync(this.pluginTargetDir)) {
      return []
    }

    const entries = fs.readdirSync(this.pluginTargetDir, { withFileTypes: true })
    return entries.filter(entry => {
      if (!entry.isDirectory() || !entry.name.endsWith('.dist-info')) {
        return false
      }
      const distName = this.normalizeDistributionName(entry.name.replace(/\.dist-info$/i, ''))
      return distName === normalizedPackageName || distName.startsWith(`${normalizedPackageName}_`)
    })
  }

  private parseMinimumVersion(specifier?: string): string | null {
    if (!specifier) {
      return null
    }
    const match = specifier.match(/>=\s*([A-Za-z0-9_.!+-]+)/)
    return match?.[1] || null
  }

  private compareVersions(left: string, right: string): number {
    const leftParts = this.versionParts(left)
    const rightParts = this.versionParts(right)
    const length = Math.max(leftParts.length, rightParts.length)

    for (let index = 0; index < length; index += 1) {
      const leftPart = leftParts[index] || 0
      const rightPart = rightParts[index] || 0
      if (leftPart > rightPart) {
        return 1
      }
      if (leftPart < rightPart) {
        return -1
      }
    }

    return 0
  }

  private versionParts(version: string): number[] {
    return version
      .split(/[.+-]/)
      .map(part => Number.parseInt(part, 10))
      .filter(part => Number.isFinite(part))
  }

  private normalizeDistributionName(name: string): string {
    return String(name || '')
      .trim()
      .toLowerCase()
      .replace(/[-.]+/g, '_')
  }
}
