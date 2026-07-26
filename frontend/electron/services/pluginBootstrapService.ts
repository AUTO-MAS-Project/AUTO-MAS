/**
 * Plugin bootstrap service.
 *
 * Installs required system plugin packages and optional declared bootstrap
 * packages into plugins/pypi/site-packages.
 */

import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'

import { MirrorService, MirrorSource } from './mirrorService'
import {
  MirrorRotationService,
  NetworkOperationCallback,
  NetworkOperationProgress,
} from './mirrorRotationService'
import { getLogger } from './logger'
import {
  BundledRuntimeLock,
  BundledRuntimeLockEntry,
  listBundledWheelFiles,
  readBundledRuntimeLockMetadata,
  resolveLockedWheelPaths,
  verifyBundledWheelDigestsAsync,
} from './bundledArtifactValidation'
import { runBoundedProcess } from './boundedProcess'
import { writeJsonFileAtomically } from './atomicJsonFile'
import { requiresBundledRuntimeLock } from './bundledRuntimePolicy'

const logger = getLogger('plugin bootstrap service')

const ENTRY_POINT_GROUPS = ['auto_mas.plugins', 'automas.plugins'] as const
const PYPROJECT_BOOTSTRAP_SECTION = '[tool.auto-mas.plugin-bootstrap]'
const WHEELS_MANIFEST_FILENAME = 'manifest.json'

interface DeclaredBootstrapPackage {
  name: string
  installSpec: string
  displayLabel: string
  version?: string
  specifier?: string
}

interface ExpectedPluginEntryPoint {
  group: (typeof ENTRY_POINT_GROUPS)[number]
  name: string
  value: string
}

const EXPECTED_PLUGIN_ENTRY_POINTS: Record<string, ExpectedPluginEntryPoint> = {
  auto_mas_core: {
    group: 'auto_mas.plugins',
    name: 'auto_mas_core',
    value: 'auto_mas_core.plugin:Plugin',
  },
  automas_plugin_browser: {
    group: 'auto_mas.plugins',
    name: 'browser',
    value: 'automas_plugin_browser.plugin:Plugin',
  },
  automas_plugin_ok_script_adapter: {
    group: 'auto_mas.plugins',
    name: 'ok_script_adapter',
    value: 'ok_script_adapter.plugin:Plugin',
  },
  automas_plugin_okww_adapter: {
    group: 'auto_mas.plugins',
    name: 'okww_adapter',
    value: 'okww_adapter.plugin:Plugin',
  },
  automas_maafw_interface: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_interface',
    value: 'automas_maafw_interface.plugin:Plugin',
  },
  automas_maafw_agent_env: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_agent_env',
    value: 'automas_maafw_agent_env.plugin:Plugin',
  },
  automas_maafw_controller_adb: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_controller_adb',
    value: 'automas_maafw_controller_adb.plugin:Plugin',
  },
  automas_maafw_controller_win32: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_controller_win32',
    value: 'automas_maafw_controller_win32.plugin:Plugin',
  },
  automas_maafw_project_update: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_project_update',
    value: 'automas_maafw_project_update.plugin:Plugin',
  },
  automas_maafw_project_store: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_project_store',
    value: 'automas_maafw_project_store.plugin:Plugin',
  },
  automas_maafw_runtime_pool: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_runtime_pool',
    value: 'automas_maafw_runtime_pool.plugin:Plugin',
  },
  automas_maafw_runner: {
    group: 'auto_mas.plugins',
    name: 'automas_maafw_runner',
    value: 'automas_maafw_runner.plugin:Plugin',
  },
  automas_script_maafw: {
    group: 'auto_mas.plugins',
    name: 'automas_script_maafw',
    value: 'automas_script_maafw.plugin:Plugin',
  },
  automas_script_maafw_managed: {
    group: 'auto_mas.plugins',
    name: 'automas_script_maafw_managed',
    value: 'automas_script_maafw_managed.plugin:Plugin',
  },
  automas_script_maafw_pack_m9a: {
    group: 'auto_mas.plugins',
    name: 'automas_script_maafw_pack_m9a',
    value: 'automas_script_maafw_pack_m9a.plugin:Plugin',
  },
  automas_script_hsr: {
    group: 'auto_mas.plugins',
    name: 'automas_script_hsr',
    value: 'automas_script_hsr.plugin:Plugin',
  },
  automas_hsr_adapter_sra: {
    group: 'auto_mas.plugins',
    name: 'automas_hsr_adapter_sra',
    value: 'automas_hsr_adapter_sra.plugin:Plugin',
  },
  automas_hsr_adapter_m7a: {
    group: 'auto_mas.plugins',
    name: 'automas_hsr_adapter_m7a',
    value: 'automas_hsr_adapter_m7a.plugin:Plugin',
  },
  automas_plugin_mxu_import: {
    group: 'auto_mas.plugins',
    name: 'mxu_import',
    value: 'automas_plugin_mxu_import.plugin:Plugin',
  },
  automas_plugin_maaend_adapter: {
    group: 'auto_mas.plugins',
    name: 'maaend_adapter',
    value: 'maaend_adapter.plugin:Plugin',
  },
  automas_script_maa: {
    group: 'auto_mas.plugins',
    name: 'script_MAA',
    value: 'script_maa.plugin:Plugin',
  },
}

const SYSTEM_BOOTSTRAP_PACKAGES: DeclaredBootstrapPackage[] = [
  {
    name: 'auto-mas-core',
    installSpec: 'auto-mas-core>=6.0.0a1',
    displayLabel: 'auto-mas-core>=6.0.0a1',
    specifier: '>=6.0.0a1',
  },
  {
    name: 'automas-plugin-browser',
    installSpec: 'automas-plugin-browser>=0.1.0',
    displayLabel: 'automas-plugin-browser>=0.1.0',
    specifier: '>=0.1.0',
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
  kind: 'install-failed' | 'missing-entry-point' | 'version-mismatch'
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
  private wheelsDir: string
  private stateFilePath: string
  private pluginTransactionJournalPath: string
  private pyprojectPath: string
  private mirrorService: MirrorService
  private rotationService: MirrorRotationService

  constructor(appRoot: string, mirrorService: MirrorService) {
    this.appRoot = appRoot
    this.uvExe = path.join(appRoot, 'environment', 'python', 'Scripts', 'uv.exe')
    this.pluginsDir = path.join(appRoot, 'plugins')
    this.pluginTargetDir = path.join(appRoot, 'plugins', 'pypi', 'site-packages')
    this.wheelsDir = path.join(appRoot, 'plugins', 'wheels')
    this.stateFilePath = path.join(appRoot, 'environment', '.plugin_bootstrap_state.json')
    this.pluginTransactionJournalPath = path.join(
      appRoot,
      'environment',
      '.plugin-target-transaction.json'
    )
    this.pyprojectPath = path.join(appRoot, 'pyproject.toml')
    this.mirrorService = mirrorService
    this.rotationService = new MirrorRotationService()
  }

  async installPackages(
    onProgress?: PluginBootstrapProgressCallback,
    selectedMirror?: string,
    forceInstall: boolean = false
  ): Promise<PluginBootstrapInstallResult> {
    const activePluginTargetDir = this.pluginTargetDir
    let stagingPluginTargetDir: string | null = null
    try {
      this.recoverPluginTargetTransaction()
      onProgress?.({
        stage: 'check',
        progress: 0,
        message: 'Checking plugin bootstrap state...',
        details: {},
      })

      const declaredPackages = this.loadDeclaredPackageSpecs()
      if (declaredPackages.length === 0) {
        throw new Error(
          `No plugin packages were declared in ${PYPROJECT_BOOTSTRAP_SECTION}; refusing an incomplete bootstrap`
        )
      }
      const checkResult = this.checkBootstrapState(declaredPackages)
      // Validate the bundled wheelhouse structure before accepting a cached bootstrap
      // state: manifest/runtime-lock contract, exact file set and per-wheel byte size.
      // The 127-wheel content digest pass is deliberately deferred until we know an
      // install will actually run — see the note above verifyBundledWheelDigestsAsync
      // below. Hashing 146 MiB here would block every queued ipcMain.handle during
      // cold start even when nothing changed.
      const findLinksDir = this.detectLocalWheelsDir()
      const runtimeLock = findLinksDir ? readBundledRuntimeLockMetadata(findLinksDir) : null
      if (runtimeLock) {
        logger.info(
          `Using complete runtime wheelhouse for bootstrap (contract and wheel sizes verified): ${findLinksDir}`
        )
        this.validateLockedPluginContract(runtimeLock, declaredPackages)
        const lockedTargetEntries = [...runtimeLock.plugin_runtime, ...runtimeLock.plugins]
        if (!this.hasExactLockedTargetDistributions(activePluginTargetDir, lockedTargetEntries)) {
          checkResult.needsInstall = true
          logger.warn(
            'Active plugin target differs from the bundled runtime lock; reinstalling the exact locked set'
          )
        }
      }
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
          'Plugin bootstrap state is unchanged and all declared packages are present, skipping install'
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

      // An install will run, so every wheel that uv may consume must be
      // authenticated first. Streaming digests keep the main thread responsive
      // while the whole wheelhouse is hashed.
      if (findLinksDir) {
        onProgress?.({
          stage: 'check',
          progress: 100,
          message: 'Verifying bundled wheel checksums...',
          details: { checkInfo: checkResult, operationDesc: 'sha256 (streaming)' },
        })
        await verifyBundledWheelDigestsAsync(findLinksDir)
        logger.info(`Bundled wheelhouse content digests verified: ${findLinksDir}`)
      }

      await this.ensureUvReady()
      stagingPluginTargetDir = path.join(
        path.dirname(activePluginTargetDir),
        `.site-packages-stage-${process.pid}-${Date.now()}`
      )
      this.pluginTargetDir = stagingPluginTargetDir
      this.ensurePluginTargetDir()

      const installedPackages: string[] = []
      const failedPackages: string[] = []
      const warnings: PluginBootstrapWarning[] = []

      if (runtimeLock) {
        await this.installLockedPluginRuntime(runtimeLock, onProgress)
        installedPackages.push(...checkResult.packages)
      } else {
        const systemResult = await this.installSystemPackages(
          installedPackages,
          failedPackages,
          warnings,
          onProgress,
          selectedMirror,
          findLinksDir
        )
        if (!systemResult.success) {
          this.saveState({
            hash: checkResult.currentHash,
            packages: [...checkResult.packages],
            installedPackages,
            failedPackages,
            warnings,
            updatedAt: new Date().toISOString(),
          })
          return {
            success: false,
            installedPackages,
            failedPackages,
            warnings,
            error: systemResult.error,
            summary: systemResult.error || 'System plugin bootstrap failed',
          }
        }

        await this.installDeclaredPackages(
          declaredPackages,
          installedPackages,
          failedPackages,
          warnings,
          onProgress,
          selectedMirror,
          findLinksDir
        )
      }

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

      if (failedPackages.length > 0) {
        this.saveState({
          hash: checkResult.currentHash,
          packages: [...checkResult.packages],
          installedPackages,
          failedPackages,
          warnings,
          updatedAt: new Date().toISOString(),
        })
        return {
          success: false,
          installedPackages,
          failedPackages,
          warnings,
          error: summary,
          summary,
        }
      }

      // Mark the transaction pending before swapping. If the process exits
      // between promotion and the final state write, the next startup retries.
      this.saveState({
        hash: checkResult.currentHash,
        packages: [...checkResult.packages],
        installedPackages: [],
        failedPackages: ['plugin-target-transaction-pending'],
        warnings: [],
        updatedAt: new Date().toISOString(),
      })

      this.pluginTargetDir = activePluginTargetDir
      const allPackages = this.getAllBootstrapPackages(declaredPackages)
      this.promotePluginTarget(stagingPluginTargetDir, activePluginTargetDir, () =>
        this.areBootstrapPackagesInstalled(allPackages)
      )
      stagingPluginTargetDir = null

      this.saveState({
        hash: checkResult.currentHash,
        packages: [...checkResult.packages],
        installedPackages,
        failedPackages: [],
        warnings,
        updatedAt: new Date().toISOString(),
      })

      return {
        success: true,
        installedPackages,
        failedPackages: [],
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
    } finally {
      this.pluginTargetDir = activePluginTargetDir
      if (stagingPluginTargetDir && fs.existsSync(stagingPluginTargetDir)) {
        this.cleanupPluginTransactionPath(stagingPluginTargetDir)
      }
    }
  }

  private checkBootstrapState(
    declaredPackages: DeclaredBootstrapPackage[]
  ): PluginBootstrapCheckResult {
    const allPackages = this.getAllBootstrapPackages(declaredPackages)
    const packages = allPackages.map(item => item.displayLabel)
    const currentHash = this.calculateHash(allPackages)
    const lastState = this.loadState()
    const lastHash = lastState?.hash
    const hasFailedPackages = (lastState?.failedPackages.length || 0) > 0
    const allPackagesInstalled = this.areBootstrapPackagesInstalled(allPackages)

    return {
      packages,
      currentHash,
      lastHash,
      needsInstall:
        !allPackagesInstalled || hasFailedPackages || lastHash == null || lastHash !== currentHash,
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
      .update(
        JSON.stringify({
          packages: normalized,
          wheelsManifest: this.readWheelsManifestContent(),
          // This is deliberately a lightweight trigger rather than a cached
          // integrity result. Any normal wheel replacement changes size or
          // mtime, invalidates the existing bootstrap state and causes the
          // streaming SHA-256 pass to run before uv sees the wheelhouse.
          wheelsMetadata: this.readWheelsMetadataFingerprint(),
        })
      )
      .digest('hex')
  }

  private readWheelsMetadataFingerprint(): Array<{
    filename: string
    size: number
    mtimeMs: number
  }> {
    if (!fs.existsSync(this.wheelsDir)) {
      return []
    }

    return listBundledWheelFiles(this.wheelsDir)
      .sort((left, right) => left.localeCompare(right))
      .map(filename => {
        const stat = fs.statSync(path.join(this.wheelsDir, filename))
        return {
          filename,
          size: stat.size,
          mtimeMs: stat.mtimeMs,
        }
      })
  }

  private readWheelsManifestContent(): string {
    const manifestPath = path.join(this.wheelsDir, WHEELS_MANIFEST_FILENAME)
    if (!fs.existsSync(manifestPath)) {
      return ''
    }

    try {
      return fs.readFileSync(manifestPath, 'utf-8')
    } catch (error) {
      logger.warn(`Failed to read bundled wheels manifest: ${error}`)
      return ''
    }
  }

  private async installSystemPackages(
    installedPackages: string[],
    failedPackages: string[],
    warnings: PluginBootstrapWarning[],
    onProgress?: PluginBootstrapProgressCallback,
    selectedMirror?: string,
    findLinksDir?: string
  ): Promise<{ success: boolean; error?: string }> {
    for (let index = 0; index < SYSTEM_BOOTSTRAP_PACKAGES.length; index += 1) {
      const systemPackage = SYSTEM_BOOTSTRAP_PACKAGES[index]
      const packageName = systemPackage.displayLabel

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
        this.withResolvedLocalInstallSpec(systemPackage, findLinksDir),
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
        selectedMirror,
        findLinksDir
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

      if (!this.isBootstrapPackageInstalled(systemPackage)) {
        const installedVersion = this.getInstalledDistributionVersion(systemPackage.name)
        const message = `Installed version ${installedVersion || 'unknown'} does not satisfy ${packageName}`
        failedPackages.push(packageName)
        warnings.push({
          packageName,
          kind: 'version-mismatch',
          message,
        })
        return {
          success: false,
          error: `Required system plugin package version mismatch: ${message}`,
        }
      }

      installedPackages.push(packageName)
      logger.info(`System plugin package installed: ${packageName}`)
    }

    return { success: true }
  }

  private withResolvedLocalInstallSpec(
    declaredPackage: DeclaredBootstrapPackage,
    findLinksDir?: string
  ): DeclaredBootstrapPackage {
    const bundledWheel = this.findBundledWheel(declaredPackage, findLinksDir)
    if (bundledWheel) {
      logger.info(`Using bundled wheel for bootstrap: ${declaredPackage.name} -> ${bundledWheel}`)
      return {
        ...declaredPackage,
        installSpec: bundledWheel,
        displayLabel: declaredPackage.displayLabel,
      }
    }

    const normalized = declaredPackage.name.replace(/-/g, '_')
    const candidates = [normalized, normalized.replace(/^automas_plugin_/, '')]
    const pluginSourceRoots = [
      path.join(this.appRoot, 'plugins'),
      path.join(this.appRoot, 'repo', 'plugins'),
    ]

    for (const sourceRoot of pluginSourceRoots) {
      for (const candidate of candidates) {
        const localProject = path.join(sourceRoot, candidate)
        if (fs.existsSync(path.join(localProject, 'pyproject.toml'))) {
          logger.info(
            `Using local plugin project for bootstrap: ${declaredPackage.name} -> ${localProject}`
          )
          return {
            ...declaredPackage,
            installSpec: localProject,
            displayLabel: declaredPackage.displayLabel,
          }
        }
      }
    }

    return declaredPackage
  }

  private findBundledWheel(
    declaredPackage: DeclaredBootstrapPackage,
    findLinksDir?: string
  ): string | undefined {
    if (!findLinksDir) {
      return undefined
    }

    try {
      const normalizedName = this.normalizeDistributionName(declaredPackage.name)
      const candidates: Array<{ version: string; filename: string }> = []
      for (const entry of fs.readdirSync(findLinksDir, { withFileTypes: true })) {
        if (!entry.isFile() || !entry.name.toLowerCase().endsWith('.whl')) {
          continue
        }
        const parsed = this.parseWheelFilename(entry.name)
        if (
          parsed != null &&
          this.normalizeDistributionName(parsed.distribution) === normalizedName &&
          this.isVersionAllowed(parsed.version, declaredPackage)
        ) {
          candidates.push({ version: parsed.version, filename: entry.name })
        }
      }
      candidates.sort((left, right) => this.compareVersions(right.version, left.version))

      const selected = candidates[0]
      return selected ? path.join(findLinksDir, selected.filename) : undefined
    } catch (error) {
      logger.warn(`Failed to resolve bundled wheel for ${declaredPackage.name}: ${error}`)
      return undefined
    }
  }

  private parseWheelFilename(filename: string): { distribution: string; version: string } | null {
    if (!filename.toLowerCase().endsWith('.whl')) {
      return null
    }

    const parts = filename.slice(0, -4).split('-')
    if (parts.length < 5 || !parts[0] || !parts[1]) {
      return null
    }

    return {
      distribution: parts[0],
      version: parts[1],
    }
  }

  private validateLockedPluginContract(
    runtimeLock: BundledRuntimeLock,
    declaredPackages: DeclaredBootstrapPackage[]
  ): void {
    const expectedDistributionKeys = Object.keys(EXPECTED_PLUGIN_ENTRY_POINTS).sort()
    if (expectedDistributionKeys.length !== 21) {
      throw new Error(
        `Internal plugin entry-point contract must contain 21 items; got ${expectedDistributionKeys.length}`
      )
    }

    const allDeclared = this.getAllBootstrapPackages(declaredPackages)
    const declaredKeys = allDeclared.map(item => this.normalizeDistributionName(item.name)).sort()
    if (
      new Set(declaredKeys).size !== declaredKeys.length ||
      declaredKeys.join('\n') !== expectedDistributionKeys.join('\n')
    ) {
      throw new Error(
        'pyproject bootstrap declarations do not exactly match the 21 locked plugin entry-point distributions'
      )
    }

    const lockedPlugins = new Map(
      runtimeLock.plugins.map(
        item => [this.normalizeDistributionName(item.distribution), item] as const
      )
    )
    for (const declaredPackage of allDeclared) {
      const normalized = this.normalizeDistributionName(declaredPackage.name)
      const lockedPlugin = lockedPlugins.get(normalized)
      const expectedEntryPoint = EXPECTED_PLUGIN_ENTRY_POINTS[normalized]
      if (lockedPlugin == null || expectedEntryPoint == null) {
        throw new Error(`Locked plugin wheel is missing for ${declaredPackage.name}`)
      }
      if (!this.isVersionAllowed(lockedPlugin.version, declaredPackage)) {
        // Lane 13 P0: 错误必须明确给出 distribution / requested / locked 三元，
        // 让 Alpha.4 的 "Locked plugin ... violates ..." 错误再现时能一眼定位
        // 是 pyproject pin 与 wheel/runtime-lock 哪一侧偏离。
        const requestedDisplay =
          declaredPackage.specifier || declaredPackage.version || declaredPackage.installSpec
        throw new Error(
          `Locked plugin version mismatch: ` +
            `distribution="${lockedPlugin.distribution}", ` +
            `requested="${requestedDisplay}" (from pyproject [tool.auto-mas.plugin-bootstrap]), ` +
            `locked="${lockedPlugin.version}" (from plugins/wheels/runtime-lock.json). ` +
            `Offline bootstrap requires pyproject pin, runtime-lock and wheel filename to agree.`
        )
      }
      const entryPoints = lockedPlugin.entry_points ?? []
      if (
        entryPoints.length !== 1 ||
        entryPoints[0].group !== expectedEntryPoint.group ||
        entryPoints[0].name !== expectedEntryPoint.name ||
        entryPoints[0].value !== expectedEntryPoint.value
      ) {
        throw new Error(
          `Locked plugin entry point does not match the release contract: ${declaredPackage.name}`
        )
      }
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

  private async installLockedPluginRuntime(
    runtimeLock: BundledRuntimeLock,
    onProgress?: PluginBootstrapProgressCallback
  ): Promise<void> {
    const venvPython = path.join(this.appRoot, '.venv', 'Scripts', 'python.exe')
    if (!fs.existsSync(venvPython)) {
      throw new Error('Locked plugin bootstrap requires the validated host .venv Python')
    }
    const entries = [...runtimeLock.plugin_runtime, ...runtimeLock.plugins]
    const wheelPaths = resolveLockedWheelPaths(this.wheelsDir, entries)
    if (runtimeLock.plugins.length !== 23 || wheelPaths.length !== entries.length) {
      throw new Error('Locked plugin install plan is incomplete')
    }

    onProgress?.({
      stage: 'install',
      progress: 20,
      message: 'Installing exact locked plugin wheels offline...',
      details: { operationDesc: 'uv pip install --no-index --no-deps' },
    })
    await runBoundedProcess(
      this.uvExe,
      [
        'pip',
        'install',
        '--python',
        venvPython,
        '--target',
        this.pluginTargetDir,
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
        label: 'uv pip install (locked plugin runtime)',
        onStdout: chunk => logger.info(`locked plugin install: ${chunk.toString().trim()}`),
        onStderr: chunk => logger.info(`locked plugin install stderr: ${chunk.toString().trim()}`),
      }
    )

    onProgress?.({
      stage: 'install',
      progress: 80,
      message: 'Validating locked plugin distributions and imports...',
      details: { operationDesc: 'isolated plugin entry-point import validation' },
    })
    const targetDiff = this.describeLockedTargetMismatch(this.pluginTargetDir, entries)
    if (targetDiff !== null) {
      // Lane 13 P0: "部分安装后假成功" 必须给出 actual/expected 明细，便于诊断
      // 是 wheel 漏装、版本不一致还是出现多余 dist-info。
      throw new Error(
        `Plugin target distribution/version set differs from runtime-lock scopes. ` + targetDiff
      )
    }
    await this.validateLockedPluginImports(venvPython, runtimeLock)
  }

  /**
   * Lane 13: 比对当前 plugin target 目录与 runtime-lock 期望集合，
   * 返回 null 表示一致；返回字符串表示差异描述（用于错误信息）。
   */
  private describeLockedTargetMismatch(
    targetDir: string,
    expectedEntries: BundledRuntimeLockEntry[]
  ): string | null {
    const installed = new Map<string, { version: string; distInfo: string }>()
    let readFailedReason: string | null = null
    try {
      for (const entry of fs.readdirSync(targetDir, { withFileTypes: true })) {
        if (!entry.isDirectory() || !entry.name.toLowerCase().endsWith('.dist-info')) continue
        const metadataPath = path.join(targetDir, entry.name, 'METADATA')
        if (!fs.existsSync(metadataPath)) {
          readFailedReason = `dist-info missing METADATA: ${entry.name}`
          break
        }
        const metadata = fs.readFileSync(metadataPath, 'utf-8')
        const name = metadata.match(/^Name:\s*(.+?)\s*$/im)?.[1]
        const version = metadata.match(/^Version:\s*(.+?)\s*$/im)?.[1]
        if (!name || !version) {
          readFailedReason = `dist-info METADATA missing Name/Version: ${entry.name}`
          break
        }
        const normalized = this.normalizeDistributionName(name)
        if (installed.has(normalized)) {
          readFailedReason = `duplicate installed distribution "${normalized}" (dist-info: ${entry.name} vs ${installed.get(normalized)!.distInfo})`
          break
        }
        installed.set(normalized, { version, distInfo: entry.name })
      }
    } catch (error) {
      readFailedReason = `read failure: ${error instanceof Error ? error.message : String(error)}`
    }
    if (readFailedReason !== null) {
      return `Failed to read installed plugin target: ${readFailedReason}`
    }

    const expectedMap = new Map<
      string,
      { distribution: string; version: string; filename: string }
    >()
    for (const item of expectedEntries) {
      const key = this.normalizeDistributionName(item.distribution)
      expectedMap.set(key, {
        distribution: item.distribution,
        version: item.version,
        filename: item.filename,
      })
    }

    const missing: string[] = []
    const versionMismatches: string[] = []
    for (const [key, expected] of expectedMap) {
      const actual = installed.get(key)
      if (actual === undefined) {
        missing.push(`${expected.distribution}==${expected.version} (wheel: ${expected.filename})`)
      } else if (actual.version !== expected.version) {
        versionMismatches.push(
          `${expected.distribution}: expected "${expected.version}" (wheel: ${expected.filename}), actual "${actual.version}" (dist-info: ${actual.distInfo})`
        )
      }
    }
    const extra: string[] = []
    for (const [key, actual] of installed) {
      if (!expectedMap.has(key)) {
        extra.push(`${key}==${actual.version} (dist-info: ${actual.distInfo})`)
      }
    }

    if (missing.length === 0 && versionMismatches.length === 0 && extra.length === 0) {
      return null
    }
    const parts: string[] = []
    if (missing.length > 0) {
      parts.push(`missing [${missing.join('; ')}]`)
    }
    if (versionMismatches.length > 0) {
      parts.push(`version mismatch [${versionMismatches.join('; ')}]`)
    }
    if (extra.length > 0) {
      parts.push(`unexpected [${extra.join('; ')}]`)
    }
    return `expected=${expectedEntries.length} distributions, actual=${installed.size} dist-info; ${parts.join('; ')}.`
  }

  private hasExactLockedTargetDistributions(
    targetDir: string,
    expectedEntries: BundledRuntimeLockEntry[]
  ): boolean {
    try {
      const installed = new Map<string, string>()
      for (const entry of fs.readdirSync(targetDir, { withFileTypes: true })) {
        if (!entry.isDirectory() || !entry.name.toLowerCase().endsWith('.dist-info')) continue
        const metadataPath = path.join(targetDir, entry.name, 'METADATA')
        if (!fs.existsSync(metadataPath)) return false
        const metadata = fs.readFileSync(metadataPath, 'utf-8')
        const name = metadata.match(/^Name:\s*(.+?)\s*$/im)?.[1]
        const version = metadata.match(/^Version:\s*(.+?)\s*$/im)?.[1]
        if (!name || !version) return false
        const normalized = this.normalizeDistributionName(name)
        if (installed.has(normalized)) return false
        installed.set(normalized, version)
      }
      if (installed.size !== expectedEntries.length) return false
      return expectedEntries.every(
        item => installed.get(this.normalizeDistributionName(item.distribution)) === item.version
      )
    } catch (error) {
      logger.warn(`Failed to validate exact locked plugin target: ${error}`)
      return false
    }
  }

  private async validateLockedPluginImports(
    venvPython: string,
    runtimeLock: BundledRuntimeLock
  ): Promise<void> {
    const encodedExpected = Buffer.from(
      JSON.stringify(runtimeLock.expected_plugin_entry_points),
      'utf-8'
    ).toString('base64')
    const validationScript = [
      'import base64, importlib.metadata as metadata, json, sys',
      'target = sys.argv[1]',
      'app_root = sys.argv[2]',
      'expected = json.loads(base64.b64decode(sys.argv[3]))',
      'sys.path[:0] = [target, app_root]',
      'found = {}',
      'for dist in metadata.distributions(path=[target]):',
      '    for ep in dist.entry_points:',
      '        if ep.group in ("auto_mas.plugins", "automas.plugins"):',
      '            key = (ep.group, ep.name)',
      '            assert key not in found, f"duplicate entry point: {key}"',
      '            found[key] = ep',
      'assert len(expected) == 21, f"expected 21 entry points, got {len(expected)}"',
      'for item in expected:',
      '    key = (item["group"], item["name"])',
      '    assert key in found, f"missing entry point: {key}"',
      '    ep = found[key]',
      '    assert ep.value == item["value"], f"entry point value mismatch: {key}"',
      '    ep.load()',
      'assert len(found) == 21, f"unexpected entry points: {sorted(found)}"',
    ].join('\n')
    await runBoundedProcess(
      venvPython,
      ['-I', '-c', validationScript, this.pluginTargetDir, this.appRoot, encodedExpected],
      {
        cwd: this.appRoot,
        env: this.createOfflineEnvironment(),
        timeoutMs: 3 * 60_000,
        label: 'isolated locked plugin entry-point import validation',
      }
    )
  }

  /**
   * Locate the bundled wheelhouse and fail closed on a broken one.
   *
   * Only the manifest/runtime-lock contract, the exact file set and the per-wheel
   * byte sizes are checked here (readdir + statSync + two small JSON parses). The
   * 146 MiB content digest pass is the caller's job and only runs when an install
   * is actually going to happen — see verifyBundledWheelDigestsAsync in
   * installPackages.
   */
  private detectLocalWheelsDir(): string | undefined {
    if (!fs.existsSync(this.wheelsDir)) {
      if (requiresBundledRuntimeLock(this.appRoot)) {
        throw new Error(
          'Bundled integration snapshot is missing plugins/wheels; online fallback is refused'
        )
      }
      return undefined
    }

    const wheelFiles = listBundledWheelFiles(this.wheelsDir)
    const releaseMarkers = [
      WHEELS_MANIFEST_FILENAME,
      'runtime-lock.json',
      'pylock.host.toml',
      'pylock.combined.toml',
    ]
    const hasReleaseMarker = releaseMarkers.some(filename =>
      fs.existsSync(path.join(this.wheelsDir, filename))
    )
    if (wheelFiles.length === 0 && !hasReleaseMarker) {
      if (requiresBundledRuntimeLock(this.appRoot)) {
        throw new Error(
          'Bundled integration snapshot has an empty plugins/wheels directory; online fallback is refused'
        )
      }
      return undefined
    }

    readBundledRuntimeLockMetadata(this.wheelsDir)
    return this.wheelsDir
  }

  private promotePluginTarget(
    stagingTargetDir: string,
    activeTargetDir: string,
    validateActiveTarget: () => boolean
  ): void {
    const backupTargetDir = path.join(
      path.dirname(activeTargetDir),
      `.site-packages-backup-${process.pid}-${Date.now()}`
    )
    const journal = {
      schema_version: 1,
      phase: 'prepared',
      had_active_target: fs.existsSync(activeTargetDir),
      active_path: activeTargetDir,
      staging_path: stagingTargetDir,
      backup_path: backupTargetDir,
    }
    writeJsonFileAtomically(this.pluginTransactionJournalPath, journal)
    let oldTargetMoved = false
    let newTargetMoved = false
    let committed = false

    try {
      if (fs.existsSync(activeTargetDir)) {
        fs.renameSync(activeTargetDir, backupTargetDir)
        oldTargetMoved = true
      }
      fs.renameSync(stagingTargetDir, activeTargetDir)
      newTargetMoved = true

      if (!validateActiveTarget()) {
        throw new Error('Promoted plugin target failed final entry-point/version validation')
      }

      journal.phase = 'committed'
      writeJsonFileAtomically(this.pluginTransactionJournalPath, journal)
      committed = true
      if (oldTargetMoved) {
        this.cleanupPluginTransactionPath(backupTargetDir)
      }
      fs.rmSync(this.pluginTransactionJournalPath, { force: true })
    } catch (error) {
      if (committed) {
        const reason = error instanceof Error ? error.message : String(error)
        throw new Error(
          `Plugin target was validated and committed, but transaction finalization failed; active target and journal were retained: ${reason}`
        )
      }
      const rollbackErrors: string[] = []
      try {
        if (newTargetMoved && fs.existsSync(activeTargetDir)) {
          fs.rmSync(activeTargetDir, { recursive: true, force: true })
        }
        if (oldTargetMoved) {
          if (!fs.existsSync(backupTargetDir)) {
            throw new Error(`backup target is missing: ${backupTargetDir}`)
          }
          fs.renameSync(backupTargetDir, activeTargetDir)
        }
        fs.rmSync(this.pluginTransactionJournalPath, { force: true })
      } catch (rollbackError) {
        rollbackErrors.push(
          rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
        )
      }

      const errorMsg = error instanceof Error ? error.message : String(error)
      if (rollbackErrors.length > 0) {
        throw new Error(
          `Plugin target promotion failed: ${errorMsg}; rollback incomplete (${rollbackErrors.join('; ')}). Recovery data: ${backupTargetDir}`
        )
      }
      throw new Error(`Plugin target promotion failed and was rolled back: ${errorMsg}`)
    }
  }

  private recoverPluginTargetTransaction(): void {
    if (!fs.existsSync(this.pluginTransactionJournalPath)) {
      return
    }
    const journal = JSON.parse(fs.readFileSync(this.pluginTransactionJournalPath, 'utf-8')) as {
      schema_version: number
      phase: string
      had_active_target: boolean
      active_path: string
      staging_path: string
      backup_path: string
    }
    const expectedActivePath = path.join(this.appRoot, 'plugins', 'pypi', 'site-packages')
    const parentDir = path.resolve(path.dirname(expectedActivePath))
    const isTransactionPath = (candidate: string, prefix: string) =>
      path.dirname(path.resolve(candidate)) === parentDir &&
      path.basename(candidate).startsWith(prefix)
    if (
      journal.schema_version !== 1 ||
      !['prepared', 'committed'].includes(journal.phase) ||
      typeof journal.had_active_target !== 'boolean' ||
      path.resolve(journal.active_path) !== path.resolve(expectedActivePath) ||
      !isTransactionPath(journal.staging_path, '.site-packages-stage-') ||
      !isTransactionPath(journal.backup_path, '.site-packages-backup-')
    ) {
      throw new Error('Plugin target transaction journal contains unsafe paths; recovery refused')
    }

    if (journal.phase === 'committed') {
      if (!fs.existsSync(expectedActivePath)) {
        throw new Error('Committed plugin target transaction lost its active target')
      }
      if (fs.existsSync(journal.backup_path)) {
        this.cleanupPluginTransactionPath(journal.backup_path)
      }
    } else if (fs.existsSync(journal.backup_path)) {
      if (fs.existsSync(expectedActivePath)) {
        const interruptedPath = path.join(
          parentDir,
          `.site-packages-interrupted-${process.pid}-${Date.now()}`
        )
        fs.renameSync(expectedActivePath, interruptedPath)
        fs.renameSync(journal.backup_path, expectedActivePath)
        this.cleanupPluginTransactionPath(interruptedPath, true)
      } else {
        fs.renameSync(journal.backup_path, expectedActivePath)
      }
    } else if (!journal.had_active_target && fs.existsSync(expectedActivePath)) {
      fs.rmSync(expectedActivePath, { recursive: true, force: true })
    }
    if (fs.existsSync(journal.staging_path)) {
      this.cleanupPluginTransactionPath(journal.staging_path, true)
    }
    fs.rmSync(this.pluginTransactionJournalPath, { force: true })
    logger.warn(`Recovered an interrupted plugin target transaction (phase=${journal.phase})`)
  }

  private cleanupPluginTransactionPath(targetPath: string, throwOnError: boolean = false): void {
    const expectedActivePath = path.join(this.appRoot, 'plugins', 'pypi', 'site-packages')
    const parentDir = path.resolve(path.dirname(expectedActivePath))
    const basename = path.basename(targetPath)
    const allowedPrefix = [
      '.site-packages-stage-',
      '.site-packages-backup-',
      '.site-packages-interrupted-',
    ].some(prefix => basename.startsWith(prefix))
    if (path.dirname(path.resolve(targetPath)) !== parentDir || !allowedPrefix) {
      throw new Error(`Refusing to clean path outside the plugin transaction scope: ${targetPath}`)
    }
    try {
      fs.rmSync(targetPath, { recursive: true, force: true })
    } catch (error) {
      if (throwOnError) {
        throw error
      }
      logger.warn(
        `Failed to clean plugin transaction path; retained for audit: ${targetPath}, ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  private async installDeclaredPackages(
    declaredPackages: DeclaredBootstrapPackage[],
    installedPackages: string[],
    failedPackages: string[],
    warnings: PluginBootstrapWarning[],
    onProgress?: PluginBootstrapProgressCallback,
    selectedMirror?: string,
    findLinksDir?: string
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
        this.withResolvedLocalInstallSpec(declaredPackage, findLinksDir),
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
        selectedMirror,
        findLinksDir
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
      } else if (!this.isBootstrapPackageInstalled(declaredPackage)) {
        const installedVersion = this.getInstalledDistributionVersion(declaredPackage.name)
        failedPackages.push(packageName)
        const warning: PluginBootstrapWarning = {
          packageName,
          kind: 'version-mismatch',
          message: `Installed version ${installedVersion || 'unknown'} does not satisfy ${packageName}`,
        }
        warnings.push(warning)
        logger.warn(
          `Plugin bootstrap package version mismatch: package=${packageName}, installed=${installedVersion || 'unknown'}`
        )
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
      throw new Error('uv.exe does not exist; complete environment initialization first')
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
    selectedMirror?: string,
    findLinksDir?: string
  ): Promise<{ success: boolean; error?: string; hasPluginEntryPoint?: boolean }> {
    const mirrors = this.mirrorService.getMirrors('pip_mirror')
    const packageLabel = declaredPackage.displayLabel

    const installOperation: NetworkOperationCallback = async (mirror, onOpProgress) => {
      try {
        onOpProgress({
          progress: 10,
          description: `Installing ${packageLabel} from ${mirror.name}...`,
        })
        await this.runUvInstall(
          declaredPackage,
          mirror,
          progress => {
            onOpProgress({
              progress,
              description: `Installing ${packageLabel}...`,
            })
          },
          findLinksDir
        )

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

  private async runUvInstall(
    declaredPackage: DeclaredBootstrapPackage,
    mirror: MirrorSource,
    onProgress?: (progress: number) => void,
    findLinksDir?: string
  ): Promise<void> {
    const args = [
      'pip',
      'install',
      declaredPackage.installSpec,
      '--target',
      this.pluginTargetDir,
      '--upgrade',
    ]
    if (findLinksDir) args.push('--find-links', findLinksDir)
    args.push('--index-url', mirror.url)
    const handleOutput = (prefix: string, chunk: Buffer) => {
      const output = chunk.toString().trim()
      logger.info(`${prefix}: ${output}`)
      if (output.includes('Resolved')) onProgress?.(35)
      else if (output.includes('Prepared') || output.includes('Downloading')) onProgress?.(60)
      else if (output.includes('Installed') || output.includes('installed')) onProgress?.(90)
    }
    await runBoundedProcess(this.uvExe, args, {
      cwd: this.appRoot,
      env: process.env,
      timeoutMs: 15 * 60_000,
      label: `uv pip install ${declaredPackage.displayLabel}`,
      onStdout: chunk => handleOutput('plugin bootstrap stdout', chunk),
      onStderr: chunk => handleOutput('plugin bootstrap stderr', chunk),
    })
  }

  private areSystemPackagesInstalled(): boolean {
    return this.areBootstrapPackagesInstalled(SYSTEM_BOOTSTRAP_PACKAGES)
  }

  private isSystemPackageInstalled(systemPackage: DeclaredBootstrapPackage): boolean {
    return this.isBootstrapPackageInstalled(systemPackage)
  }

  private areBootstrapPackagesInstalled(packages: DeclaredBootstrapPackage[]): boolean {
    return packages.every(item => this.isBootstrapPackageInstalled(item))
  }

  private isBootstrapPackageInstalled(declaredPackage: DeclaredBootstrapPackage): boolean {
    return this.findDistributionInfoDirs(declaredPackage.name).some(distInfo => {
      if (!this.distInfoHasPluginEntryPoint(distInfo, declaredPackage.name)) {
        return false
      }
      const installedVersion = this.readDistributionVersion(declaredPackage.name, distInfo)
      return installedVersion != null && this.isVersionAllowed(installedVersion, declaredPackage)
    })
  }

  private hasPluginEntryPoint(packageName: string): boolean {
    return this.findDistributionInfoDirs(packageName).some(distInfo =>
      this.distInfoHasPluginEntryPoint(distInfo, packageName)
    )
  }

  private distInfoHasPluginEntryPoint(distInfo: fs.Dirent, packageName?: string): boolean {
    const entryPointsPath = path.join(this.pluginTargetDir, distInfo.name, 'entry_points.txt')
    if (!fs.existsSync(entryPointsPath)) {
      return false
    }

    const expected = packageName
      ? EXPECTED_PLUGIN_ENTRY_POINTS[this.normalizeDistributionName(packageName)]
      : undefined
    const lines = fs.readFileSync(entryPointsPath, 'utf-8').split(/\r?\n/)
    let activeGroup = ''
    for (const rawLine of lines) {
      const line = rawLine.trim()
      const sectionMatch = line.match(/^\[([^\]]+)\]$/)
      if (sectionMatch) {
        activeGroup = sectionMatch[1]
        continue
      }
      if (!ENTRY_POINT_GROUPS.includes(activeGroup as (typeof ENTRY_POINT_GROUPS)[number])) {
        continue
      }
      const entryPointMatch = line.match(/^([^=]+?)\s*=\s*(\S.*)$/)
      if (!entryPointMatch || line.startsWith('#')) {
        continue
      }
      if (!expected) {
        return true
      }

      const entryPointName = entryPointMatch[1].trim()
      const entryPointValue = entryPointMatch[2].trim().replace(/^["']|["']$/g, '')
      if (
        activeGroup === expected.group &&
        entryPointName === expected.name &&
        entryPointValue === expected.value
      ) {
        return true
      }
    }

    return false
  }

  private getInstalledDistributionVersion(packageName: string): string | null {
    for (const distInfo of this.findDistributionInfoDirs(packageName)) {
      const version = this.readDistributionVersion(packageName, distInfo)
      if (version != null) {
        return version
      }
    }

    return null
  }

  private readDistributionVersion(packageName: string, distInfo: fs.Dirent): string | null {
    const metadataPath = path.join(this.pluginTargetDir, distInfo.name, 'METADATA')
    if (fs.existsSync(metadataPath)) {
      const metadata = fs.readFileSync(metadataPath, 'utf-8')
      const versionMatch = metadata.match(/^Version:\s*(.+)$/m)
      if (versionMatch) {
        return versionMatch[1].trim()
      }
    }

    // 回退: 从 dist-info 目录名提取 version.
    // dist-info 目录名规范: <distribution>-<version>.dist-info
    //   - <distribution> 可包含连字符 (automas-maafw-runner)
    //   - <version> 通常形如 0.2.0 / 5.4.0b1, 必须保留点号
    // 不能对整个 dist-info 名用 normalizeDistributionName, 否则 version 中的点号
    // 会被替换为下划线 (0.2.0 变成 0_2_0), 导致版本字符串失真.
    // 因此: 从后往前扫, 用规范化包名匹配 name 前缀, 但 version 部分保留原字符.
    const distInfoBasename = distInfo.name.replace(/\.dist-info$/i, '')
    const normalizedPackageName = this.normalizeDistributionName(packageName)
    for (let i = distInfoBasename.length - 1; i > 0; i -= 1) {
      const ch = distInfoBasename[i]
      if (ch !== '-' && ch !== '_') {
        continue
      }
      const candidateName = this.normalizeDistributionName(distInfoBasename.slice(0, i))
      if (candidateName === normalizedPackageName) {
        const versionPart = distInfoBasename.slice(i + 1)
        if (versionPart) {
          return versionPart
        }
      }
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

      const metadataPath = path.join(this.pluginTargetDir, entry.name, 'METADATA')
      if (fs.existsSync(metadataPath)) {
        const metadata = fs.readFileSync(metadataPath, 'utf-8')
        const nameMatch = metadata.match(/^Name:\s*(.+)$/m)
        if (nameMatch) {
          return this.normalizeDistributionName(nameMatch[1].trim()) === normalizedPackageName
        }
      }

      const distInfoBasename = entry.name.replace(/\.dist-info$/i, '')
      for (let i = distInfoBasename.length - 1; i > 0; i -= 1) {
        const separator = distInfoBasename[i]
        if (separator !== '-' && separator !== '_') {
          continue
        }
        const versionPart = distInfoBasename.slice(i + 1)
        if (!/^\d/.test(versionPart)) {
          continue
        }
        const candidateName = this.normalizeDistributionName(distInfoBasename.slice(0, i))
        if (candidateName === normalizedPackageName) {
          return true
        }
      }
      return false
    })
  }

  private parseMinimumVersion(specifier?: string): string | null {
    if (!specifier) {
      return null
    }
    const match = specifier.match(/>=\s*([A-Za-z0-9_.!+-]+)/)
    return match?.[1] || null
  }

  private isVersionAllowed(
    installedVersion: string,
    declaredPackage: DeclaredBootstrapPackage
  ): boolean {
    if (declaredPackage.specifier) {
      return declaredPackage.specifier.split(',').every(rawClause => {
        const clause = rawClause.trim()
        const match = clause.match(/^(===|==|!=|>=|<=|>|<)\s*([^\s]+)$/)
        if (!match || match[2].includes('*')) {
          logger.warn(
            `Unsupported plugin version specifier for local validation: ${declaredPackage.name}${clause}`
          )
          return false
        }

        const comparison = this.compareVersions(installedVersion, match[2])
        switch (match[1]) {
          case '===':
            return installedVersion === match[2]
          case '==':
            return comparison === 0
          case '!=':
            return comparison !== 0
          case '>=':
            return comparison >= 0
          case '<=':
            return comparison <= 0
          case '>':
            return comparison > 0
          case '<':
            return comparison < 0
          default:
            return false
        }
      })
    }

    if (declaredPackage.version) {
      return this.compareVersions(installedVersion, declaredPackage.version) === 0
    }

    return true
  }

  private compareVersions(left: string, right: string): number {
    const leftVersion = this.parseComparableVersion(left)
    const rightVersion = this.parseComparableVersion(right)
    const length = Math.max(leftVersion.release.length, rightVersion.release.length)

    for (let index = 0; index < length; index += 1) {
      const leftPart = leftVersion.release[index] || 0
      const rightPart = rightVersion.release[index] || 0
      if (leftPart > rightPart) {
        return 1
      }
      if (leftPart < rightPart) {
        return -1
      }
    }

    if (leftVersion.precedence !== rightVersion.precedence) {
      return leftVersion.precedence > rightVersion.precedence ? 1 : -1
    }
    if (leftVersion.preNumber !== rightVersion.preNumber) {
      return leftVersion.preNumber > rightVersion.preNumber ? 1 : -1
    }
    if (leftVersion.postNumber !== rightVersion.postNumber) {
      return leftVersion.postNumber > rightVersion.postNumber ? 1 : -1
    }

    return 0
  }

  private parseComparableVersion(version: string): {
    release: number[]
    precedence: number
    preNumber: number
    postNumber: number
  } {
    const normalized = version.trim().toLowerCase().replace(/^v/, '')
    const releaseMatch = normalized.match(/^(\d+(?:\.\d+)*)/)
    const release = releaseMatch
      ? releaseMatch[1].split('.').map(part => Number.parseInt(part, 10))
      : [0]
    const suffix = normalized.slice(releaseMatch?.[0].length || 0).replace(/^[-_.]+/, '')
    const preMatch = suffix.match(/^(a|alpha|b|beta|rc|c|pre|preview)[-_.]?(\d*)/)
    const postMatch = suffix.match(/(?:post|rev|r)[-_.]?(\d+)/)

    let precedence = 3
    if (preMatch) {
      if (preMatch[1] === 'a' || preMatch[1] === 'alpha') {
        precedence = 0
      } else if (preMatch[1] === 'b' || preMatch[1] === 'beta') {
        precedence = 1
      } else {
        precedence = 2
      }
    }

    return {
      release,
      precedence,
      preNumber: preMatch?.[2] ? Number.parseInt(preMatch[2], 10) : 0,
      postNumber: postMatch?.[1] ? Number.parseInt(postMatch[1], 10) : 0,
    }
  }

  private normalizeDistributionName(name: string): string {
    return String(name || '')
      .trim()
      .toLowerCase()
      .replace(/[-.]+/g, '_')
  }
}
