import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'
import * as os from 'os'
import * as crypto from 'crypto'

import { runBoundedProcess } from '../boundedProcess'
import {
  readAndVerifyBundledRuntimeLock,
  type BundledRuntimeLock,
} from '../bundledArtifactValidation'
import { PluginBootstrapService } from '../pluginBootstrapService'
import type { MirrorService } from '../mirrorService'
import { writeCompleteWheelhouse } from './wheelhouseFixture'

vi.mock('../boundedProcess', () => ({
  runBoundedProcess: vi.fn(),
  terminateProcessTree: vi.fn(),
}))

interface DeclaredBootstrapPackage {
  name: string
  installSpec: string
  displayLabel: string
  version?: string
  specifier?: string
}

interface TempWorkspace {
  appRoot: string
  pluginTargetDir: string
  pyprojectPath: string
  tmpDir: string
}

function createTempWorkspace(): TempWorkspace {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-bootstrap-test-'))
  const appRoot = tmpDir
  const pluginTargetDir = path.join(appRoot, 'plugins', 'pypi', 'site-packages')
  fs.mkdirSync(pluginTargetDir, { recursive: true })
  const pyprojectPath = path.join(appRoot, 'pyproject.toml')
  return { appRoot, pluginTargetDir, pyprojectPath, tmpDir }
}

function createDistInfo(
  pluginTargetDir: string,
  distInfoName: string,
  entryPointGroup?: string,
  version?: string,
  entryPointName?: string,
  entryPointValue?: string
): void {
  const distInfoDir = path.join(pluginTargetDir, distInfoName)
  fs.mkdirSync(distInfoDir, { recursive: true })
  if (entryPointGroup) {
    const epName = entryPointName ?? distInfoName.replace(/\.dist-info$/i, '').replace(/[-.]/g, '_')
    const epValue = entryPointValue ?? `${epName}.plugin:Plugin`
    const entryPointsContent = `[${entryPointGroup}]\n${epName} = "${epValue}"\n`
    fs.writeFileSync(path.join(distInfoDir, 'entry_points.txt'), entryPointsContent)
  }
  if (version) {
    const metadataContent = `Metadata-Version: 2.1\nName: ${distInfoName.replace(/\.dist-info$/i, '').replace(/-\d.*$/, '')}\nVersion: ${version}\n`
    fs.writeFileSync(path.join(distInfoDir, 'METADATA'), metadataContent)
  }
}

function writeWheelManifest(wheelsDir: string, filenames: string[]): void {
  const wheels = filenames.map(filename => {
    const content = fs.readFileSync(path.join(wheelsDir, filename))
    return {
      filename,
      size_bytes: content.length,
      sha256: crypto.createHash('sha256').update(content).digest('hex'),
    }
  })
  fs.writeFileSync(path.join(wheelsDir, 'manifest.json'), JSON.stringify({ wheels }))
}

type AnyService = PluginBootstrapService & { [key: string]: any }

function writeLockedPluginTarget(
  pluginTargetDir: string,
  runtimeLock: BundledRuntimeLock,
  omittedDistribution?: string
): void {
  for (const item of [...runtimeLock.plugin_runtime, ...runtimeLock.plugins]) {
    if (item.distribution === omittedDistribution) {
      continue
    }

    const distInfoDir = path.join(
      pluginTargetDir,
      `${item.distribution.replace(/[-.]/g, '_')}-${item.version}.dist-info`
    )
    fs.mkdirSync(distInfoDir, { recursive: true })
    fs.writeFileSync(
      path.join(distInfoDir, 'METADATA'),
      `Metadata-Version: 2.1\nName: ${item.distribution}\nVersion: ${item.version}\n`
    )

    const entryPoints = item.entry_points ?? []
    if (entryPoints.length > 0) {
      const entryPointsContent = entryPoints
        .map(entryPoint => `[${entryPoint.group}]\n${entryPoint.name} = ${entryPoint.value}\n`)
        .join('\n')
      fs.writeFileSync(path.join(distInfoDir, 'entry_points.txt'), entryPointsContent)
    }
  }
}

function saveMatchingBootstrapState(service: AnyService): void {
  const declaredPackages = service.loadDeclaredPackageSpecs()
  const checkResult = service.checkBootstrapState(declaredPackages)
  service.saveState({
    hash: checkResult.currentHash,
    packages: [...checkResult.packages],
    installedPackages: [...checkResult.packages],
    failedPackages: [],
    warnings: [],
    updatedAt: new Date().toISOString(),
  })
}

const INTEGRATION_BOOTSTRAP_PYPROJECT = `[tool.auto-mas.plugin-bootstrap]
packages = [
    "automas_plugin_ok_script_adapter",
    "automas_plugin_okww_adapter",
    { name = "automas-maafw-interface", version = "0.1.1" },
    { name = "automas-maafw-agent-env", version = "0.1.1" },
    { name = "automas-maafw-controller-adb", version = "0.1.0" },
    { name = "automas-maafw-controller-win32", version = "0.1.1" },
    { name = "automas-maafw-project-update", version = "0.1.0" },
    { name = "automas-maafw-project-store", version = "0.1.0" },
    { name = "automas-maafw-runtime-pool", version = "0.1.0" },
    { name = "automas-maafw-runner", version = "0.2.0" },
    { name = "automas-script-maafw", version = "0.1.5" },
    { name = "automas-script-maafw-managed", version = "0.1.0" },
    { name = "automas-script-maafw-pack-m9a", version = "0.1.2" },
    { name = "automas-script-hsr", version = "0.1.0" },
    { name = "automas-hsr-adapter-sra", version = "0.1.0" },
    { name = "automas-hsr-adapter-m7a", version = "0.1.0" },
    { name = "automas-plugin-mxu-import", version = "0.1.0" },
    { name = "automas_plugin_maaend_adapter", version = "0.0.2" },
    { name = "automas_script_maa", version = "0.0.5" },
]
`

describe('PluginBootstrapService - pyproject parsing', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    const fakeMirror = {} as unknown as MirrorService
    service = new PluginBootstrapService(workspace.appRoot, fakeMirror) as AnyService
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('parses current integration pyproject.toml bootstrap packages', () => {
    fs.writeFileSync(workspace.pyprojectPath, INTEGRATION_BOOTSTRAP_PYPROJECT)

    const packages = service.loadDeclaredPackageSpecs() as DeclaredBootstrapPackage[]

    expect(packages).toHaveLength(19)

    const okScript = packages.find(p => p.name === 'automas_plugin_ok_script_adapter')
    expect(okScript).toBeDefined()
    expect(okScript!.installSpec).toBe('automas_plugin_ok_script_adapter')

    const okww = packages.find(p => p.name === 'automas_plugin_okww_adapter')
    expect(okww).toBeDefined()
    expect(okww!.installSpec).toBe('automas_plugin_okww_adapter')

    const hsr = packages.find(p => p.name === 'automas-script-hsr')
    expect(hsr).toBeDefined()
    expect(hsr!.version).toBe('0.1.0')
    expect(hsr!.installSpec).toBe('automas-script-hsr==0.1.0')

    const sra = packages.find(p => p.name === 'automas-hsr-adapter-sra')
    expect(sra).toBeDefined()
    expect(sra!.version).toBe('0.1.0')
    expect(sra!.installSpec).toBe('automas-hsr-adapter-sra==0.1.0')

    const m7a = packages.find(p => p.name === 'automas-hsr-adapter-m7a')
    expect(m7a).toBeDefined()
    expect(m7a!.version).toBe('0.1.0')
    expect(m7a!.installSpec).toBe('automas-hsr-adapter-m7a==0.1.0')

    const mxuImport = packages.find(p => p.name === 'automas-plugin-mxu-import')
    expect(mxuImport?.installSpec).toBe('automas-plugin-mxu-import==0.1.0')

    const maaEnd = packages.find(p => p.name === 'automas_plugin_maaend_adapter')
    expect(maaEnd?.installSpec).toBe('automas_plugin_maaend_adapter==0.0.2')

    const maa = packages.find(p => p.name === 'automas_script_maa')
    expect(maa?.installSpec).toBe('automas_script_maa==0.0.5')

    const m9a = packages.find(p => p.name === 'automas-script-maafw-pack-m9a')
    expect(m9a).toBeDefined()
    expect(m9a!.version).toBe('0.1.2')
    expect(m9a!.installSpec).toBe('automas-script-maafw-pack-m9a==0.1.2')

    const managed = packages.find(p => p.name === 'automas-script-maafw-managed')
    expect(managed).toBeDefined()
    expect(managed!.version).toBe('0.1.0')

    const store = packages.find(p => p.name === 'automas-maafw-project-store')
    expect(store).toBeDefined()
    expect(store!.version).toBe('0.1.0')

    const pool = packages.find(p => p.name === 'automas-maafw-runtime-pool')
    expect(pool).toBeDefined()
    expect(pool!.version).toBe('0.1.0')

    const runner = packages.find(p => p.name === 'automas-maafw-runner')
    expect(runner).toBeDefined()
    expect(runner!.version).toBe('0.2.0')

    const scriptMaafw = packages.find(p => p.name === 'automas-script-maafw')
    expect(scriptMaafw).toBeDefined()
    expect(scriptMaafw!.version).toBe('0.1.5')

    const agentEnv = packages.find(p => p.name === 'automas-maafw-agent-env')
    expect(agentEnv).toBeDefined()
    expect(agentEnv!.version).toBe('0.1.1')

    const interfacePkg = packages.find(p => p.name === 'automas-maafw-interface')
    expect(interfacePkg).toBeDefined()
    expect(interfacePkg!.version).toBe('0.1.1')

    const adb = packages.find(p => p.name === 'automas-maafw-controller-adb')
    expect(adb).toBeDefined()
    expect(adb!.version).toBe('0.1.0')

    const win32 = packages.find(p => p.name === 'automas-maafw-controller-win32')
    expect(win32).toBeDefined()
    expect(win32!.version).toBe('0.1.1')

    const update = packages.find(p => p.name === 'automas-maafw-project-update')
    expect(update).toBeDefined()
    expect(update!.version).toBe('0.1.0')
  })

  it('returns empty list when pyproject.toml missing', () => {
    const packages = service.loadDeclaredPackageSpecs()
    expect(packages).toEqual([])
  })

  it('returns empty list when bootstrap section missing', () => {
    fs.writeFileSync(workspace.pyprojectPath, '[project]\nname = "x"\n')
    const packages = service.loadDeclaredPackageSpecs()
    expect(packages).toEqual([])
  })

  it('deduplicates packages by normalized distribution name', () => {
    fs.writeFileSync(
      workspace.pyprojectPath,
      `[tool.auto-mas.plugin-bootstrap]
packages = [
    "auto-mas-core",
    { name = "auto_mas.core", version = "1.0.0" },
]
`
    )
    const packages = service.loadDeclaredPackageSpecs()
    expect(packages).toHaveLength(1)
    expect(packages[0].name).toBe('auto-mas-core')
  })

  it('supports specifier syntax', () => {
    fs.writeFileSync(
      workspace.pyprojectPath,
      `[tool.auto-mas.plugin-bootstrap]
packages = [
    { name = "foo", specifier = ">=0.0.5-alpha,<0.1.0" },
]
`
    )
    const packages = service.loadDeclaredPackageSpecs() as DeclaredBootstrapPackage[]
    expect(packages).toHaveLength(1)
    expect(packages[0].specifier).toBe('>=0.0.5-alpha,<0.1.0')
    expect(packages[0].installSpec).toBe('foo>=0.0.5-alpha,<0.1.0')
  })

  it('prefers specifier when both version and specifier are declared', () => {
    fs.writeFileSync(
      workspace.pyprojectPath,
      `[tool.auto-mas.plugin-bootstrap]
packages = [
    { name = "foo", version = "1.0.0", specifier = ">=1.0.0,<2.0.0" },
]
`
    )
    const packages = service.loadDeclaredPackageSpecs() as DeclaredBootstrapPackage[]
    expect(packages).toHaveLength(1)
    expect(packages[0].specifier).toBe('>=1.0.0,<2.0.0')
    expect(packages[0].installSpec).toBe('foo>=1.0.0,<2.0.0')
  })

  it('handles inline table with extra whitespace', () => {
    fs.writeFileSync(
      workspace.pyprojectPath,
      `[tool.auto-mas.plugin-bootstrap]
packages = [
    {   name = "bar"  ,  version = "2.0.0"   },
]
`
    )
    const packages = service.loadDeclaredPackageSpecs() as DeclaredBootstrapPackage[]
    expect(packages).toHaveLength(1)
    expect(packages[0].name).toBe('bar')
    expect(packages[0].version).toBe('2.0.0')
    expect(packages[0].installSpec).toBe('bar==2.0.0')
  })

  it('stops at next section marker', () => {
    fs.writeFileSync(
      workspace.pyprojectPath,
      `[tool.auto-mas.plugin-bootstrap]
packages = [
    "first",
]
[other.section]
packages = [
    "should-not-be-included",
]
`
    )
    const packages = service.loadDeclaredPackageSpecs() as DeclaredBootstrapPackage[]
    expect(packages).toHaveLength(1)
    expect(packages[0].name).toBe('first')
  })
})

describe('PluginBootstrapService - version comparison', () => {
  const fakeMirror = {} as unknown as MirrorService
  const service = new PluginBootstrapService('', fakeMirror) as AnyService

  it('compares semver-like versions', () => {
    expect(service.compareVersions('0.1.2', '0.1.1')).toBe(1)
    expect(service.compareVersions('0.1.0', '0.1.0')).toBe(0)
    expect(service.compareVersions('0.0.9', '0.1.0')).toBe(-1)
    expect(service.compareVersions('1.0.0', '0.9.9')).toBe(1)
  })

  it('handles different segment counts', () => {
    expect(service.compareVersions('1.0', '1.0.0')).toBe(0)
    expect(service.compareVersions('1.0.1', '1.0')).toBe(1)
    expect(service.compareVersions('1.0', '1.0.1')).toBe(-1)
  })

  it('parses numeric parts from version strings with separators', () => {
    expect(service.compareVersions('5.4.0b1', '5.4.0a1')).toBe(1)
    expect(service.compareVersions('5.4.0', '5.4.0b1')).toBe(1)
    expect(service.compareVersions('5.4.0', '5.3.0')).toBe(1)
  })

  it('extracts minimum version from >= specifier', () => {
    expect(service.parseMinimumVersion('>=5.2.0')).toBe('5.2.0')
    expect(service.parseMinimumVersion('>= 5.2.0')).toBe('5.2.0')
    expect(service.parseMinimumVersion(undefined)).toBeNull()
    expect(service.parseMinimumVersion('==1.0.0')).toBeNull()
  })

  it('normalizes distribution names', () => {
    expect(service.normalizeDistributionName('auto-mas-core')).toBe('auto_mas_core')
    expect(service.normalizeDistributionName('automas.script.hsr')).toBe('automas_script_hsr')
    expect(service.normalizeDistributionName('  Auto-Mas-Core  ')).toBe('auto_mas_core')
  })
})

describe('PluginBootstrapService - entry point check', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    const fakeMirror = {} as unknown as MirrorService
    service = new PluginBootstrapService(workspace.appRoot, fakeMirror) as AnyService
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('detects auto_mas.plugins entry point', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'automas_script_hsr-0.1.0-py3-none-any.whl.dist-info',
      'auto_mas.plugins',
      '0.1.0',
      'automas_script_hsr',
      'automas_script_hsr.plugin:Plugin'
    )
    expect(service.hasPluginEntryPoint('automas-script-hsr')).toBe(true)
  })

  it('rejects a known distribution whose entry-point name or value is wrong', () => {
    const distInfoDir = path.join(workspace.pluginTargetDir, 'automas_script_hsr-0.1.0.dist-info')
    fs.mkdirSync(distInfoDir, { recursive: true })
    fs.writeFileSync(
      path.join(distInfoDir, 'entry_points.txt'),
      '[auto_mas.plugins]\nautomas_script_hsr = wrong.module:Plugin\n'
    )
    fs.writeFileSync(
      path.join(distInfoDir, 'METADATA'),
      'Metadata-Version: 2.1\nName: automas-script-hsr\nVersion: 0.1.0\n'
    )

    expect(service.hasPluginEntryPoint('automas-script-hsr')).toBe(false)
  })

  it('rejects a legacy group for a distribution with an exact current contract', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'automas_hsr_adapter_sra-0.1.0-py3-none-any.whl.dist-info',
      'automas.plugins',
      '0.1.0',
      'automas_hsr_adapter_sra',
      'automas_hsr_adapter_sra.plugin:Plugin'
    )
    expect(service.hasPluginEntryPoint('automas-hsr-adapter-sra')).toBe(false)
  })

  it('accepts a legacy group for an undeclared third-party distribution', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'third_party_plugin-0.1.0.dist-info',
      'automas.plugins',
      '0.1.0',
      'third_party_plugin',
      'third_party_plugin.plugin:Plugin'
    )
    expect(service.hasPluginEntryPoint('third-party-plugin')).toBe(true)
  })

  it('returns false when entry_points.txt missing', () => {
    const distInfoDir = path.join(workspace.pluginTargetDir, 'foo-1.0.0.dist-info')
    fs.mkdirSync(distInfoDir, { recursive: true })
    expect(service.hasPluginEntryPoint('foo')).toBe(false)
  })

  it('returns false when entry point group mismatch', () => {
    createDistInfo(workspace.pluginTargetDir, 'foo-1.0.0.dist-info', 'some.other.group', '1.0.0')
    expect(service.hasPluginEntryPoint('foo')).toBe(false)
  })

  it('returns false when dist-info missing', () => {
    expect(service.hasPluginEntryPoint('nonexistent-package')).toBe(false)
  })

  it('matches dist-info by normalized name with underscore prefix', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'automas_maafw_runner-0.2.0.dist-info',
      'auto_mas.plugins',
      '0.2.0',
      'automas_maafw_runner',
      'automas_maafw_runner.plugin:Plugin'
    )
    expect(service.hasPluginEntryPoint('automas-maafw-runner')).toBe(true)
  })

  it('does not confuse a related distribution prefix with the requested package', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'automas_script_maafw_managed-0.1.0.dist-info',
      'auto_mas.plugins',
      '0.1.0',
      'automas_script_maafw_managed'
    )

    expect(service.hasPluginEntryPoint('automas-script-maafw')).toBe(false)
    expect(service.getInstalledDistributionVersion('automas-script-maafw')).toBeNull()
  })

  it('extracts version from METADATA file', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'automas-maafw-runner-0.2.0.dist-info',
      'auto_mas.plugins',
      '0.2.0'
    )
    expect(service.getInstalledDistributionVersion('automas-maafw-runner')).toBe('0.2.0')
  })

  it('falls back to dist-info name suffix when METADATA missing', () => {
    const distInfoDir = path.join(workspace.pluginTargetDir, 'automas-maafw-runner-0.2.0.dist-info')
    fs.mkdirSync(distInfoDir, { recursive: true })
    expect(service.getInstalledDistributionVersion('automas-maafw-runner')).toBe('0.2.0')
  })

  it('returns null when version cannot be determined', () => {
    const distInfoDir = path.join(workspace.pluginTargetDir, 'weird.dist-info')
    fs.mkdirSync(distInfoDir, { recursive: true })
    expect(service.getInstalledDistributionVersion('weird')).toBeNull()
  })

  it('reports system package installed when entry point and version satisfy spec', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'auto-mas-core-5.4.0b1.dist-info',
      'auto_mas.plugins',
      '5.4.0b1',
      'auto_mas_core'
    )
    const systemPkg: DeclaredBootstrapPackage = {
      name: 'auto-mas-core',
      installSpec: 'auto-mas-core>=5.2.0',
      displayLabel: 'auto-mas-core>=5.2.0',
      specifier: '>=5.2.0',
    }
    expect(service.isSystemPackageInstalled(systemPkg)).toBe(true)
  })

  it('reports system package not installed when version too low', () => {
    createDistInfo(
      workspace.pluginTargetDir,
      'auto-mas-core-5.1.0.dist-info',
      'auto_mas.plugins',
      '5.1.0',
      'auto_mas_core'
    )
    const systemPkg: DeclaredBootstrapPackage = {
      name: 'auto-mas-core',
      installSpec: 'auto-mas-core>=5.2.0',
      displayLabel: 'auto-mas-core>=5.2.0',
      specifier: '>=5.2.0',
    }
    expect(service.isSystemPackageInstalled(systemPkg)).toBe(false)
  })
})

describe('PluginBootstrapService - local source resolution', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    const fakeMirror = {} as unknown as MirrorService
    service = new PluginBootstrapService(workspace.appRoot, fakeMirror) as AnyService
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('uses local source project when pyproject.toml exists in repo/plugins/<name>/', () => {
    const localProjectDir = path.join(service.appRoot, 'repo', 'plugins', 'automas_plugin_browser')
    fs.mkdirSync(localProjectDir, { recursive: true })
    fs.writeFileSync(
      path.join(localProjectDir, 'pyproject.toml'),
      '[project]\nname = "automas-plugin-browser"\n'
    )

    const declared: DeclaredBootstrapPackage = {
      name: 'automas-plugin-browser',
      installSpec: 'automas-plugin-browser==0.1.0',
      displayLabel: 'automas-plugin-browser==0.1.0',
      version: '0.1.0',
    }
    const resolved = service.withResolvedLocalInstallSpec(declared)

    expect(resolved.installSpec).toBe(localProjectDir)
  })

  it('falls back to PyPI spec when no local project exists', () => {
    const declared: DeclaredBootstrapPackage = {
      name: 'automas-script-hsr',
      installSpec: 'automas-script-hsr==0.1.0',
      displayLabel: 'automas-script-hsr==0.1.0',
      version: '0.1.0',
    }
    const resolved = service.withResolvedLocalInstallSpec(declared)

    expect(resolved.installSpec).toBe('automas-script-hsr==0.1.0')
  })

  it('strips automas_plugin_ prefix when looking for local project', () => {
    const localProjectDir = path.join(service.appRoot, 'repo', 'plugins', 'ok_script_adapter')
    fs.mkdirSync(localProjectDir, { recursive: true })
    fs.writeFileSync(
      path.join(localProjectDir, 'pyproject.toml'),
      '[project]\nname = "automas_plugin_ok_script_adapter"\n'
    )

    const declared: DeclaredBootstrapPackage = {
      name: 'automas_plugin_ok_script_adapter',
      installSpec: 'automas_plugin_ok_script_adapter',
      displayLabel: 'automas_plugin_ok_script_adapter',
    }
    const resolved = service.withResolvedLocalInstallSpec(declared)

    expect(resolved.installSpec).toBe(localProjectDir)
  })

  it('preserves displayLabel when switching to local source', () => {
    const localProjectDir = path.join(service.appRoot, 'repo', 'plugins', 'automas_script_hsr')
    fs.mkdirSync(localProjectDir, { recursive: true })
    fs.writeFileSync(
      path.join(localProjectDir, 'pyproject.toml'),
      '[project]\nname = "automas-script-hsr"\n'
    )

    const declared: DeclaredBootstrapPackage = {
      name: 'automas-script-hsr',
      installSpec: 'automas-script-hsr==0.1.0',
      displayLabel: 'automas-script-hsr==0.1.0',
      version: '0.1.0',
    }
    const resolved = service.withResolvedLocalInstallSpec(declared)

    expect(resolved.installSpec).toBe(localProjectDir)
    expect(resolved.displayLabel).toBe('automas-script-hsr==0.1.0')
  })
})

describe('PluginBootstrapService - local wheels directory', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    const fakeMirror = {} as unknown as MirrorService
    service = new PluginBootstrapService(workspace.appRoot, fakeMirror) as AnyService
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('detectLocalWheelsDir returns undefined when wheels dir missing', () => {
    expect(service.detectLocalWheelsDir()).toBeUndefined()
  })

  it('rejects a missing wheelhouse when an integration snapshot marker exists', () => {
    const marker = path.join(workspace.appRoot, 'res', 'integration-snapshot.json')
    fs.mkdirSync(path.dirname(marker), { recursive: true })
    fs.writeFileSync(marker, '{}')
    expect(() => service.detectLocalWheelsDir()).toThrow('online fallback is refused')
  })

  it('detectLocalWheelsDir returns undefined when wheels dir is empty', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    expect(service.detectLocalWheelsDir()).toBeUndefined()
  })

  it('detectLocalWheelsDir rejects a partial release wheelhouse with only manifest.json', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    fs.writeFileSync(path.join(service.wheelsDir, 'manifest.json'), '{}')
    expect(() => service.detectLocalWheelsDir()).toThrow()
  })

  it('detectLocalWheelsDir returns path when declared .whl files pass integrity checks', () => {
    writeCompleteWheelhouse(service.wheelsDir)
    expect(service.detectLocalWheelsDir()).toBe(service.wheelsDir)
  })

  it('accepts a valid manifest written with a UTF-8 BOM', () => {
    writeCompleteWheelhouse(service.wheelsDir)
    const manifestPath = path.join(service.wheelsDir, 'manifest.json')
    fs.writeFileSync(manifestPath, `\uFEFF${fs.readFileSync(manifestPath, 'utf-8')}`)
    expect(service.detectLocalWheelsDir()).toBe(service.wheelsDir)
  })

  it('detectLocalWheelsDir ignores a directory containing only an sdist', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    fs.writeFileSync(
      path.join(service.wheelsDir, 'automas_maafw_runner-0.2.0.tar.gz'),
      'fake sdist'
    )
    expect(service.detectLocalWheelsDir()).toBeUndefined()
  })

  it('detectLocalWheelsDir is case-insensitive for wheel extensions', () => {
    writeCompleteWheelhouse(service.wheelsDir, { uppercaseFirstWheelExtension: true })
    expect(service.detectLocalWheelsDir()).toBe(service.wheelsDir)
  })

  it('fails closed when wheel files exist without a manifest', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    fs.writeFileSync(path.join(service.wheelsDir, 'foo-1.0.0-py3-none-any.whl'), 'fake wheel')
    expect(() => service.detectLocalWheelsDir()).toThrow('manifest is missing')
  })

  it('fails closed when a wheel hash no longer matches the manifest', () => {
    const { filenames } = writeCompleteWheelhouse(service.wheelsDir)
    const filename = filenames[0]
    fs.writeFileSync(path.join(service.wheelsDir, filename), 'tampered!')
    expect(() => service.detectLocalWheelsDir()).toThrow(/(size|SHA-256) mismatch/)
  })

  it('fails closed when an undeclared wheel is present', () => {
    writeCompleteWheelhouse(service.wheelsDir)
    fs.writeFileSync(path.join(service.wheelsDir, 'bar-1.0.0-py3-none-any.whl'), 'bar')
    expect(() => service.detectLocalWheelsDir()).toThrow('not declared in manifest')
  })

  it('fails closed when a declared wheel is missing', () => {
    const { filenames } = writeCompleteWheelhouse(service.wheelsDir)
    const missing = filenames[0]
    fs.rmSync(path.join(service.wheelsDir, missing))
    expect(() => service.detectLocalWheelsDir()).toThrow('declared by manifest is missing')
  })

  it('rejects a hash-valid plugin seed that has no complete runtime lock', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    const filename = 'foo-1.0.0-py3-none-any.whl'
    fs.writeFileSync(path.join(service.wheelsDir, filename), 'fake wheel')
    writeWheelManifest(service.wheelsDir, [filename])
    expect(() => service.detectLocalWheelsDir()).toThrow('complete 23-distribution')
  })

  it('prefers an exact bundled wheel over a matching repository source', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    const wheelPath = path.join(service.wheelsDir, 'automas_script_hsr-0.1.0-py3-none-any.whl')
    fs.writeFileSync(wheelPath, 'fake wheel')

    const localProjectDir = path.join(service.appRoot, 'repo', 'plugins', 'automas_script_hsr')
    fs.mkdirSync(localProjectDir, { recursive: true })
    fs.writeFileSync(path.join(localProjectDir, 'pyproject.toml'), '[project]\nname = "x"\n')

    const declared: DeclaredBootstrapPackage = {
      name: 'automas-script-hsr',
      installSpec: 'automas-script-hsr==0.1.0',
      displayLabel: 'automas-script-hsr==0.1.0',
      version: '0.1.0',
    }
    const resolved = service.withResolvedLocalInstallSpec(declared, service.wheelsDir)

    expect(resolved.installSpec).toBe(wheelPath)
  })

  it('does not select a bundled wheel that violates the pinned version', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    fs.writeFileSync(
      path.join(service.wheelsDir, 'automas_script_hsr-0.2.0-py3-none-any.whl'),
      'fake wheel'
    )

    const declared: DeclaredBootstrapPackage = {
      name: 'automas-script-hsr',
      installSpec: 'automas-script-hsr==0.1.0',
      displayLabel: 'automas-script-hsr==0.1.0',
      version: '0.1.0',
    }
    const resolved = service.withResolvedLocalInstallSpec(declared, service.wheelsDir)

    expect(resolved.installSpec).toBe('automas-script-hsr==0.1.0')
  })

  it('includes manifest content in the bootstrap hash', () => {
    fs.mkdirSync(service.wheelsDir, { recursive: true })
    const manifestPath = path.join(service.wheelsDir, 'manifest.json')
    const declared: DeclaredBootstrapPackage[] = [
      {
        name: 'automas-script-hsr',
        installSpec: 'automas-script-hsr==0.1.0',
        displayLabel: 'automas-script-hsr==0.1.0',
        version: '0.1.0',
      },
    ]

    fs.writeFileSync(manifestPath, '{"build":1}')
    const firstHash = service.calculateHash(declared)
    fs.writeFileSync(manifestPath, '{"build":2}')
    const secondHash = service.calculateHash(declared)

    expect(secondHash).not.toBe(firstHash)
  })
})

describe('PluginBootstrapService - fail-closed result', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    service = new PluginBootstrapService(
      workspace.appRoot,
      {} as unknown as MirrorService
    ) as AnyService
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('fails when the integration pyproject declares no bootstrap packages', async () => {
    fs.writeFileSync(workspace.pyprojectPath, '[project]\nname = "host"\n')

    const result = await service.installPackages()

    expect(result.success).toBe(false)
    expect(result.error).toContain('refusing an incomplete bootstrap')
  })

  it('fails the stage when any declared package fails', async () => {
    fs.writeFileSync(
      workspace.pyprojectPath,
      '[tool.auto-mas.plugin-bootstrap]\npackages = [{ name = "foo", version = "1.0.0" }]\n'
    )
    fs.mkdirSync(path.dirname(service.uvExe), { recursive: true })
    fs.writeFileSync(service.uvExe, '')
    fs.writeFileSync(path.join(workspace.pluginTargetDir, 'old-target.txt'), 'keep active target')

    vi.spyOn(service, 'installSystemPackages').mockResolvedValue({ success: true })
    vi.spyOn(service, 'installDeclaredPackages').mockImplementation(
      async (
        _packages: DeclaredBootstrapPackage[],
        _installedPackages: string[],
        failedPackages: string[],
        warnings: Array<{ packageName: string; kind: string; message: string }>
      ) => {
        failedPackages.push('foo==1.0.0')
        warnings.push({
          packageName: 'foo==1.0.0',
          kind: 'install-failed',
          message: 'simulated failure',
        })
      }
    )

    const result = await service.installPackages()

    expect(result.success).toBe(false)
    expect(result.failedPackages).toEqual(['foo==1.0.0'])
    expect(result.error).toContain('1 failed package')
    expect(fs.readFileSync(path.join(workspace.pluginTargetDir, 'old-target.txt'), 'utf-8')).toBe(
      'keep active target'
    )
    expect(
      fs
        .readdirSync(path.dirname(workspace.pluginTargetDir))
        .some(name => name.startsWith('.site-packages-stage-'))
    ).toBe(false)
  })

  it('rolls back the active plugin target when final validation fails', () => {
    const stagingTarget = path.join(
      path.dirname(workspace.pluginTargetDir),
      '.site-packages-stage-test'
    )
    fs.writeFileSync(path.join(workspace.pluginTargetDir, 'old-target.txt'), 'old')
    fs.mkdirSync(stagingTarget, { recursive: true })
    fs.writeFileSync(path.join(stagingTarget, 'new-target.txt'), 'new')

    expect(() =>
      service.promotePluginTarget(stagingTarget, workspace.pluginTargetDir, () => false)
    ).toThrow('was rolled back')
    expect(fs.readFileSync(path.join(workspace.pluginTargetDir, 'old-target.txt'), 'utf-8')).toBe(
      'old'
    )
    expect(fs.existsSync(path.join(workspace.pluginTargetDir, 'new-target.txt'))).toBe(false)
  })

  it('promotes a validated plugin target and removes its backup', () => {
    const targetParent = path.dirname(workspace.pluginTargetDir)
    const stagingTarget = path.join(targetParent, '.site-packages-stage-success')
    fs.writeFileSync(path.join(workspace.pluginTargetDir, 'old-target.txt'), 'old')
    fs.mkdirSync(stagingTarget, { recursive: true })
    fs.writeFileSync(path.join(stagingTarget, 'new-target.txt'), 'new')

    service.promotePluginTarget(stagingTarget, workspace.pluginTargetDir, () => true)

    expect(fs.existsSync(path.join(workspace.pluginTargetDir, 'old-target.txt'))).toBe(false)
    expect(fs.readFileSync(path.join(workspace.pluginTargetDir, 'new-target.txt'), 'utf-8')).toBe(
      'new'
    )
    expect(
      fs.readdirSync(targetParent).some(name => name.startsWith('.site-packages-backup-'))
    ).toBe(false)
  })
})

describe('PluginBootstrapService - locked offline install', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    service = new PluginBootstrapService(
      workspace.appRoot,
      {} as unknown as MirrorService
    ) as AnyService
    fs.writeFileSync(workspace.pyprojectPath, INTEGRATION_BOOTSTRAP_PYPROJECT)
    const venvPython = path.join(workspace.appRoot, '.venv', 'Scripts', 'python.exe')
    fs.mkdirSync(path.dirname(venvPython), { recursive: true })
    fs.writeFileSync(venvPython, 'python fixture')
    vi.mocked(runBoundedProcess).mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('uses exact plugin scope wheel paths with --no-index --no-deps', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      pluginRuntime: [{ distribution: 'plugin-only-runtime', version: '1.2.3' }],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    const declared = service.loadDeclaredPackageSpecs()
    expect(() => service.validateLockedPluginContract(runtimeLock, declared)).not.toThrow()

    vi.mocked(runBoundedProcess).mockImplementation(async (_executable, args) => {
      if (args[0] === 'pip') {
        const targetDir = args[args.indexOf('--target') + 1]
        for (const item of [...runtimeLock.plugin_runtime, ...runtimeLock.plugins]) {
          const distInfo = path.join(
            targetDir,
            `${item.distribution.replace(/[-.]/g, '_')}-${item.version}.dist-info`
          )
          fs.mkdirSync(distInfo, { recursive: true })
          fs.writeFileSync(
            path.join(distInfo, 'METADATA'),
            `Metadata-Version: 2.1\nName: ${item.distribution}\nVersion: ${item.version}\n`
          )
        }
      }
      return { stdout: '', stderr: '' }
    })

    await service.installLockedPluginRuntime(runtimeLock)

    const pipCall = vi.mocked(runBoundedProcess).mock.calls.find(call => call[1][0] === 'pip')
    expect(pipCall).toBeDefined()
    expect(pipCall![1]).toContain('--no-index')
    expect(pipCall![1]).toContain('--no-deps')
    expect(pipCall![1]).not.toContain('--upgrade')
    expect(pipCall![1]).not.toContain('--index-url')
    for (const item of [...runtimeLock.plugin_runtime, ...runtimeLock.plugins]) {
      expect(pipCall![1]).toContain(path.join(service.wheelsDir, item.filename))
    }
    const importCall = vi.mocked(runBoundedProcess).mock.calls.find(call => call[1][0] === '-I')
    expect(importCall?.[1]).toContain('-c')
    expect(importCall?.[1][2]).toContain('sys.path[:0] = [target, app_root]')
    expect(importCall?.[1][3]).toBe(workspace.pluginTargetDir)
    expect(importCall?.[1][4]).toBe(workspace.appRoot)
  })

  it('reinstalls a cached target that is missing a locked plugin runtime dependency', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      pluginRuntime: [{ distribution: 'plugin-only-runtime', version: '1.2.3' }],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    writeLockedPluginTarget(
      workspace.pluginTargetDir,
      runtimeLock,
      runtimeLock.plugin_runtime[0].distribution
    )
    saveMatchingBootstrapState(service)
    const ensureUvReady = vi
      .spyOn(service, 'ensureUvReady')
      .mockRejectedValue(new Error('reinstall requested'))

    const result = await service.installPackages()

    expect(result.skipped).not.toBe(true)
    expect(ensureUvReady).toHaveBeenCalledOnce()
    expect(result.error).toContain('reinstall requested')
  }, 30_000)

  it('reinstalls a cached target that contains an extra non-plugin distribution', async () => {
    writeCompleteWheelhouse(service.wheelsDir)
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    writeLockedPluginTarget(workspace.pluginTargetDir, runtimeLock)
    createDistInfo(
      workspace.pluginTargetDir,
      'injected-runtime-9.9.9.dist-info',
      undefined,
      '9.9.9'
    )
    saveMatchingBootstrapState(service)
    const ensureUvReady = vi
      .spyOn(service, 'ensureUvReady')
      .mockRejectedValue(new Error('reinstall requested'))

    const result = await service.installPackages()

    expect(result.skipped).not.toBe(true)
    expect(ensureUvReady).toHaveBeenCalledOnce()
    expect(result.error).toContain('reinstall requested')
  }, 30_000)

  it('skips install when the cached target exactly matches every locked plugin distribution', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      pluginRuntime: [{ distribution: 'plugin-only-runtime', version: '1.2.3' }],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    writeLockedPluginTarget(workspace.pluginTargetDir, runtimeLock)
    saveMatchingBootstrapState(service)
    const ensureUvReady = vi.spyOn(service, 'ensureUvReady')

    const result = await service.installPackages()

    expect(result.success).toBe(true)
    expect(result.skipped).toBe(true)
    expect(ensureUvReady).not.toHaveBeenCalled()
  }, 30_000)

  it('uses wheel metadata to trigger streaming hash verification before install', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      pluginRuntime: [{ distribution: 'plugin-only-runtime', version: '1.2.3' }],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    writeLockedPluginTarget(workspace.pluginTargetDir, runtimeLock)
    saveMatchingBootstrapState(service)

    // 同长度改写一个 wheel：只有全量摘要校验能发现，结构/大小校验放行。
    const tamperedWheel = path.join(service.wheelsDir, runtimeLock.plugins[0].filename)
    const originalLength = fs.readFileSync(tamperedWheel).length
    fs.writeFileSync(tamperedWheel, Buffer.alloc(originalLength, 0x41))
    const changedTime = new Date(Date.now() + 60_000)
    fs.utimesSync(tamperedWheel, changedTime, changedTime)

    // size/mtime 指纹使快路径失效；真正安装前的流式摘要校验必须发现篡改。
    const ensureUvReady = vi.spyOn(service, 'ensureUvReady')
    const result = await service.installPackages()
    expect(result.success).toBe(false)
    expect(result.skipped).not.toBe(true)
    expect(result.error).toContain(
      `Bundled wheel SHA-256 mismatch: ${runtimeLock.plugins[0].filename}`
    )
    expect(ensureUvReady).not.toHaveBeenCalled()
  }, 30_000)

  it('rejects a missing locked entry point instead of falling back to source or PyPI', () => {
    writeCompleteWheelhouse(service.wheelsDir)
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    runtimeLock.plugins[0].entry_points = []

    expect(() =>
      service.validateLockedPluginContract(runtimeLock, service.loadDeclaredPackageSpecs())
    ).toThrow('entry point does not match')
  })

  it('restores the backup plugin target from a prepared crash journal', () => {
    const targetParent = path.dirname(workspace.pluginTargetDir)
    const backupPath = path.join(targetParent, '.site-packages-backup-crash')
    const stagingPath = path.join(targetParent, '.site-packages-stage-crash')
    fs.writeFileSync(path.join(workspace.pluginTargetDir, 'new.txt'), 'new')
    fs.mkdirSync(backupPath)
    fs.writeFileSync(path.join(backupPath, 'old.txt'), 'old')
    fs.mkdirSync(stagingPath)
    fs.mkdirSync(path.dirname(service.pluginTransactionJournalPath), { recursive: true })
    fs.writeFileSync(
      service.pluginTransactionJournalPath,
      JSON.stringify({
        schema_version: 1,
        phase: 'prepared',
        had_active_target: true,
        active_path: workspace.pluginTargetDir,
        staging_path: stagingPath,
        backup_path: backupPath,
      })
    )

    service.recoverPluginTargetTransaction()

    expect(fs.readFileSync(path.join(workspace.pluginTargetDir, 'old.txt'), 'utf-8')).toBe('old')
    expect(fs.existsSync(path.join(workspace.pluginTargetDir, 'new.txt'))).toBe(false)
    expect(fs.existsSync(service.pluginTransactionJournalPath)).toBe(false)
  })
})

describe('PluginBootstrapService - Lane 13: error message diagnostics', () => {
  let workspace: TempWorkspace
  let service: AnyService

  beforeEach(() => {
    workspace = createTempWorkspace()
    service = new PluginBootstrapService(
      workspace.appRoot,
      {} as unknown as MirrorService
    ) as AnyService
  })

  afterEach(() => {
    vi.restoreAllMocks()
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('validateLockedPluginContract error includes distribution / requested / locked', () => {
    // 构造一个 wheelhouse，pyproject 声明的版本与 runtime-lock 不一致
    writeCompleteWheelhouse(service.wheelsDir)
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)

    // pyproject 声明 automas-script-hsr==0.1.0，但 runtime-lock fixture 也是 0.1.0。
    // 修改 pyproject 声明为 9.9.9，使 pin 与 lock 不一致。
    fs.writeFileSync(
      workspace.pyprojectPath,
      `[tool.auto-mas.plugin-bootstrap]
packages = [
    "automas_plugin_ok_script_adapter",
    "automas_plugin_okww_adapter",
    { name = "automas-maafw-interface", version = "0.1.1" },
    { name = "automas-maafw-agent-env", version = "0.1.1" },
    { name = "automas-maafw-controller-adb", version = "0.1.0" },
    { name = "automas-maafw-controller-win32", version = "0.1.1" },
    { name = "automas-maafw-project-update", version = "0.1.0" },
    { name = "automas-maafw-project-store", version = "0.1.0" },
    { name = "automas-maafw-runtime-pool", version = "0.1.0" },
    { name = "automas-maafw-runner", version = "0.2.0" },
    { name = "automas-script-maafw", version = "0.1.5" },
    { name = "automas-script-maafw-managed", version = "0.1.0" },
    { name = "automas-script-maafw-pack-m9a", version = "0.1.2" },
    { name = "automas-script-hsr", version = "9.9.9" },
    { name = "automas-hsr-adapter-sra", version = "0.1.0" },
    { name = "automas-hsr-adapter-m7a", version = "0.1.0" },
    { name = "automas-plugin-mxu-import", version = "0.1.0" },
    { name = "automas_plugin_maaend_adapter", version = "0.0.2" },
    { name = "automas_script_maa", version = "0.0.5" },
]
`
    )
    const declared = service.loadDeclaredPackageSpecs()

    let caughtError: Error | null = null
    try {
      service.validateLockedPluginContract(runtimeLock, declared)
    } catch (error) {
      caughtError = error as Error
    }
    expect(caughtError).not.toBeNull()
    const message = caughtError!.message
    // 必须含 distribution / requested / locked 三元
    expect(message).toContain('distribution=')
    expect(message).toContain('automas-script-hsr')
    expect(message).toContain('requested=')
    expect(message).toContain('9.9.9')
    expect(message).toContain('locked=')
    // runtime-lock fixture 中 automas-script-hsr 版本为 0.1.0
    expect(message).toContain('0.1.0')
    expect(message).toContain('pyproject')
    expect(message).toContain('runtime-lock.json')
  })

  it('installLockedPluginRuntime error includes actual/expected details on partial install', async () => {
    writeCompleteWheelhouse(service.wheelsDir, {
      pluginRuntime: [{ distribution: 'plugin-only-runtime', version: '1.2.3' }],
    })
    const runtimeLock = readAndVerifyBundledRuntimeLock(service.wheelsDir)
    // 模拟 .venv Python 已存在
    fs.mkdirSync(path.join(workspace.appRoot, '.venv', 'Scripts'), { recursive: true })
    fs.writeFileSync(path.join(workspace.appRoot, '.venv', 'Scripts', 'python.exe'), 'fake')

    // mock uv pip install：只写入部分 plugin dist-info，制造"部分安装后假成功"场景
    vi.mocked(runBoundedProcess).mockImplementation(async (_executable, args) => {
      if (args[0] === 'pip') {
        const targetDir = args[args.indexOf('--target') + 1]
        // 故意只装第一个 plugin，跳过其余以触发 actual/expected 差异
        const firstPlugin = runtimeLock.plugins[0]
        const distInfo = path.join(
          targetDir,
          `${firstPlugin.distribution.replace(/[-.]/g, '_')}-${firstPlugin.version}.dist-info`
        )
        fs.mkdirSync(distInfo, { recursive: true })
        fs.writeFileSync(
          path.join(distInfo, 'METADATA'),
          `Metadata-Version: 2.1\nName: ${firstPlugin.distribution}\nVersion: ${firstPlugin.version}\n`
        )
      }
      return { stdout: '', stderr: '' }
    })

    let caughtError: Error | null = null
    try {
      await service.installLockedPluginRuntime(runtimeLock)
    } catch (error) {
      caughtError = error as Error
    }
    expect(caughtError).not.toBeNull()
    const message = caughtError!.message
    expect(message).toContain('Plugin target distribution/version set differs from runtime-lock')
    // 必须包含 expected/actual 数量与具体 missing 列表
    expect(message).toContain('expected=')
    expect(message).toContain('actual=')
    expect(message).toContain('missing')
    // 应当列出缺失的 distribution（runtimeLock.plugins[1..] 的 distribution 之一）
    const secondPlugin = runtimeLock.plugins[1]
    expect(message).toContain(secondPlugin.distribution)
  })
})
