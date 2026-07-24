import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'

export interface BundledPluginEntryPoint {
  group: string
  name: string
  value: string
}

export type BundledRuntimeWheelScope = 'host_runtime' | 'plugin_runtime' | 'plugin'

export interface BundledRuntimeLockEntry {
  distribution: string
  version: string
  scope: BundledRuntimeWheelScope
  filename: string
  size_bytes: number
  sha256: string
  entry_points?: BundledPluginEntryPoint[]
}

export interface BundledRuntimeLock {
  schema_version: number
  target: {
    implementation: string
    python_version: string
    platform: string
    architecture: string
    uv_platform: string
  }
  install_contract: {
    resolver_allowed: boolean
    index_allowed: boolean
    required_arguments: string[]
    forbidden_arguments: string[]
    host_target: string
    plugin_target: string
    protected_host_distributions: string[]
  }
  host_runtime: BundledRuntimeLockEntry[]
  plugin_runtime: BundledRuntimeLockEntry[]
  plugins: BundledRuntimeLockEntry[]
  expected_plugin_entry_points: BundledPluginEntryPoint[]
}

export interface BundledSnapshotWheelhouseContract {
  manifest_schema_version: number
  runtime_lock_schema_version: number
  wheel_count: number
  plugin_distribution_count: number
  plugin_entry_point_count: number
  core_distribution_version: string
  manifest_sha256: string
  runtime_lock_sha256: string
}

export interface BundledSnapshotMarker {
  schema_version: number
  snapshot_id: string
  version: string
  deployment_mode: string
  required_paths: string[]
  wheel_manifest: string
  wheelhouse_contract: BundledSnapshotWheelhouseContract
}

interface BundledWheelManifestItem {
  distribution?: string
  version?: string
  scopes?: string[]
  entry_points?: BundledPluginEntryPoint[]
  filename: string
  size_bytes: number
  sha256: string
}

interface BundledWheelManifest {
  schema_version?: number
  artifact_scope?: string
  expected_plugin_distribution_count?: number
  expected_plugin_entry_point_count?: number
  runtime_lock?: {
    filename: string
    size_bytes: number
    sha256: string
  }
  wheels: BundledWheelManifestItem[]
}

function normalizeDistributionName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[-_.]+/g, '-')
}

function sha256File(filePath: string): string {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')
}

function assertSafeWheelRecord(
  item: Pick<BundledRuntimeLockEntry, 'filename' | 'size_bytes' | 'sha256'>,
  source: string
): void {
  if (
    item == null ||
    typeof item.filename !== 'string' ||
    path.basename(item.filename) !== item.filename ||
    !item.filename.toLowerCase().endsWith('.whl') ||
    !Number.isSafeInteger(item.size_bytes) ||
    item.size_bytes < 0 ||
    typeof item.sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/i.test(item.sha256)
  ) {
    throw new Error(`${source} contains an invalid wheel entry: ${JSON.stringify(item)}`)
  }
}

function entryPointKey(entryPoint: BundledPluginEntryPoint): string {
  return `${entryPoint.group}\u0000${entryPoint.name}\u0000${entryPoint.value}`
}

function validatePluginEntryPoints(value: unknown, source: string): BundledPluginEntryPoint[] {
  if (!Array.isArray(value)) {
    throw new Error(`${source} must be an array`)
  }
  const result: BundledPluginEntryPoint[] = []
  const groupAndName = new Set<string>()
  for (const item of value) {
    if (
      item == null ||
      typeof item !== 'object' ||
      typeof (item as BundledPluginEntryPoint).group !== 'string' ||
      typeof (item as BundledPluginEntryPoint).name !== 'string' ||
      typeof (item as BundledPluginEntryPoint).value !== 'string' ||
      !['auto_mas.plugins', 'automas.plugins'].includes((item as BundledPluginEntryPoint).group) ||
      !(item as BundledPluginEntryPoint).name ||
      !(item as BundledPluginEntryPoint).value
    ) {
      throw new Error(`${source} contains an invalid plugin entry point`)
    }
    const entryPoint = item as BundledPluginEntryPoint
    const key = `${entryPoint.group}\u0000${entryPoint.name}`
    if (groupAndName.has(key)) {
      throw new Error(
        `${source} contains a duplicate plugin entry point: ${entryPoint.group}/${entryPoint.name}`
      )
    }
    groupAndName.add(key)
    result.push(entryPoint)
  }
  return result
}

export function readJsonFileWithOptionalBom<T>(filePath: string): T {
  const text = fs.readFileSync(filePath, 'utf-8').replace(/^\uFEFF/, '')
  return JSON.parse(text) as T
}

export function assertBundledSnapshotMarker(
  value: unknown,
  expectedVersion?: string
): asserts value is BundledSnapshotMarker {
  const marker = value as Partial<BundledSnapshotMarker> | null
  if (
    marker == null ||
    marker.schema_version !== 1 ||
    typeof marker.snapshot_id !== 'string' ||
    !marker.snapshot_id.trim() ||
    typeof marker.version !== 'string' ||
    !/^v?6\./u.test(marker.version) ||
    marker.deployment_mode !== 'bundled-snapshot' ||
    !Array.isArray(marker.required_paths) ||
    marker.required_paths.some(item => typeof item !== 'string' || !item.trim()) ||
    typeof marker.wheel_manifest !== 'string' ||
    marker.wheelhouse_contract == null ||
    (expectedVersion != null && marker.version !== expectedVersion)
  ) {
    throw new Error('Bundled integration snapshot marker has an unsupported schema or version')
  }
  if (marker.wheel_manifest.replace(/\\/g, '/') !== 'plugins/wheels/manifest.json') {
    throw new Error(
      'Bundled integration snapshot wheel_manifest must reference plugins/wheels/manifest.json'
    )
  }
}

export function resolveContainedPath(rootPath: string, relativePath: string): string {
  if (!relativePath || path.isAbsolute(relativePath)) {
    throw new Error(`Bundled artifact path must be relative: ${relativePath}`)
  }

  const resolvedRoot = path.resolve(rootPath)
  const resolvedPath = path.resolve(resolvedRoot, relativePath)
  if (resolvedPath !== resolvedRoot && !resolvedPath.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error(`Bundled artifact path escapes its root: ${relativePath}`)
  }
  return resolvedPath
}

export function listBundledWheelFiles(wheelsDir: string): string[] {
  return fs
    .readdirSync(wheelsDir, { withFileTypes: true })
    .filter(entry => entry.isFile() && entry.name.toLowerCase().endsWith('.whl'))
    .map(entry => entry.name)
}

export function verifyBundledWheelDirectory(wheelsDir: string): string[] {
  const wheelFiles = listBundledWheelFiles(wheelsDir)
  if (wheelFiles.length === 0) {
    throw new Error(`Bundled wheel directory contains no wheel: ${wheelsDir}`)
  }

  const manifestPath = path.join(wheelsDir, 'manifest.json')
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`Bundled wheel manifest is missing: ${manifestPath}`)
  }

  let manifest: BundledWheelManifest
  try {
    manifest = readJsonFileWithOptionalBom<BundledWheelManifest>(manifestPath)
  } catch (error) {
    throw new Error(`Bundled wheel manifest is invalid JSON: ${error}`)
  }
  if (!Array.isArray(manifest.wheels)) {
    throw new Error('Bundled wheel manifest must contain a wheels array')
  }

  const declaredByName = new Map<string, BundledWheelManifestItem>()
  for (const item of manifest.wheels) {
    assertSafeWheelRecord(item as BundledRuntimeLockEntry, 'Bundled wheel manifest')

    const normalizedFilename = item.filename.toLowerCase()
    if (declaredByName.has(normalizedFilename)) {
      throw new Error(`Bundled wheel manifest contains a duplicate: ${item.filename}`)
    }
    declaredByName.set(normalizedFilename, item)
  }

  const actualNames = new Set(wheelFiles.map(filename => filename.toLowerCase()))
  for (const filename of actualNames) {
    if (!declaredByName.has(filename)) {
      throw new Error(`Bundled wheel is not declared in manifest: ${filename}`)
    }
  }

  for (const [normalizedFilename, item] of declaredByName) {
    if (!actualNames.has(normalizedFilename)) {
      throw new Error(`Bundled wheel declared by manifest is missing: ${item.filename}`)
    }

    const wheelPath = path.join(wheelsDir, item.filename)
    const actualSize = fs.statSync(wheelPath).size
    if (actualSize !== item.size_bytes) {
      throw new Error(
        `Bundled wheel size mismatch: ${item.filename} (expected ${item.size_bytes}, got ${actualSize})`
      )
    }
    const actualSha256 = sha256File(wheelPath)
    if (actualSha256.toLowerCase() !== item.sha256.toLowerCase()) {
      throw new Error(`Bundled wheel SHA-256 mismatch: ${item.filename}`)
    }
  }

  return wheelFiles
}

/**
 * Verify the complete runtime lock and return its immutable install plan.
 * A plugin-only seed manifest is deliberately rejected here.
 */
export function readAndVerifyBundledRuntimeLock(wheelsDir: string): BundledRuntimeLock {
  const wheelFiles = verifyBundledWheelDirectory(wheelsDir)
  const manifestPath = path.join(wheelsDir, 'manifest.json')
  const manifest = readJsonFileWithOptionalBom<BundledWheelManifest>(manifestPath)
  if (
    manifest.schema_version !== 3 ||
    manifest.artifact_scope !== 'complete-windows-x64-runtime-wheelhouse' ||
    manifest.expected_plugin_distribution_count !== 23 ||
    manifest.expected_plugin_entry_point_count !== 21
  ) {
    throw new Error(
      'Bundled wheel manifest is not the complete 23-distribution / 21-entry-point runtime artifact'
    )
  }

  const runtimeLockRecord = manifest.runtime_lock
  if (
    runtimeLockRecord == null ||
    runtimeLockRecord.filename !== 'runtime-lock.json' ||
    path.basename(runtimeLockRecord.filename) !== runtimeLockRecord.filename ||
    !Number.isSafeInteger(runtimeLockRecord.size_bytes) ||
    runtimeLockRecord.size_bytes < 0 ||
    typeof runtimeLockRecord.sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/i.test(runtimeLockRecord.sha256)
  ) {
    throw new Error('Bundled wheel manifest contains an invalid runtime-lock record')
  }

  const runtimeLockPath = path.join(wheelsDir, runtimeLockRecord.filename)
  if (!fs.existsSync(runtimeLockPath)) {
    throw new Error(`Bundled runtime lock is missing: ${runtimeLockPath}`)
  }
  const runtimeLockStat = fs.statSync(runtimeLockPath)
  if (runtimeLockStat.size !== runtimeLockRecord.size_bytes) {
    throw new Error('Bundled runtime lock size mismatch')
  }
  if (sha256File(runtimeLockPath).toLowerCase() !== runtimeLockRecord.sha256.toLowerCase()) {
    throw new Error('Bundled runtime lock SHA-256 mismatch')
  }

  let runtimeLock: BundledRuntimeLock
  try {
    runtimeLock = readJsonFileWithOptionalBom<BundledRuntimeLock>(runtimeLockPath)
  } catch (error) {
    throw new Error(`Bundled runtime lock is invalid JSON: ${error}`)
  }
  if (
    runtimeLock.schema_version !== 1 ||
    runtimeLock.target?.implementation !== 'cpython' ||
    runtimeLock.target?.python_version !== '3.12' ||
    runtimeLock.target?.platform !== 'win32' ||
    runtimeLock.target?.architecture !== 'x86_64' ||
    runtimeLock.target?.uv_platform !== 'x86_64-pc-windows-msvc'
  ) {
    throw new Error('Bundled runtime lock target is not CPython 3.12 / Windows x64')
  }

  const contract = runtimeLock.install_contract
  const requiredArguments = new Set(contract?.required_arguments)
  const forbiddenArguments = new Set(contract?.forbidden_arguments)
  if (
    contract == null ||
    contract.resolver_allowed !== false ||
    contract.index_allowed !== false ||
    contract.host_target !== '.venv' ||
    contract.plugin_target !== 'plugins/pypi/site-packages' ||
    !requiredArguments.has('--no-index') ||
    !requiredArguments.has('--no-deps') ||
    !forbiddenArguments.has('--upgrade') ||
    !forbiddenArguments.has('--index-url') ||
    !Array.isArray(contract.protected_host_distributions)
  ) {
    throw new Error('Bundled runtime lock install contract is unsafe or incomplete')
  }

  const manifestByFilename = new Map(
    manifest.wheels.map(item => [item.filename.toLowerCase(), item] as const)
  )
  const seenDistributions = new Map<string, BundledRuntimeWheelScope>()
  const seenFilenames = new Set<string>()
  const allLockEntries: BundledRuntimeLockEntry[] = []
  const validateScope = (
    entries: unknown,
    expectedScope: BundledRuntimeWheelScope
  ): BundledRuntimeLockEntry[] => {
    if (!Array.isArray(entries)) {
      throw new Error(`Bundled runtime lock ${expectedScope} scope must be an array`)
    }
    for (const rawEntry of entries) {
      const entry = rawEntry as BundledRuntimeLockEntry
      assertSafeWheelRecord(entry, `Bundled runtime lock ${expectedScope} scope`)
      if (
        typeof entry.distribution !== 'string' ||
        !entry.distribution ||
        typeof entry.version !== 'string' ||
        !entry.version ||
        entry.scope !== expectedScope
      ) {
        throw new Error(`Bundled runtime lock contains an invalid ${expectedScope} package`)
      }
      const normalizedDistribution = normalizeDistributionName(entry.distribution)
      const previousScope = seenDistributions.get(normalizedDistribution)
      if (previousScope != null) {
        throw new Error(
          `Bundled runtime lock distribution crosses scopes: ${entry.distribution} (${previousScope}/${expectedScope})`
        )
      }
      seenDistributions.set(normalizedDistribution, expectedScope)
      const normalizedFilename = entry.filename.toLowerCase()
      if (seenFilenames.has(normalizedFilename)) {
        throw new Error(`Bundled runtime lock repeats wheel filename: ${entry.filename}`)
      }
      seenFilenames.add(normalizedFilename)

      const manifestItem = manifestByFilename.get(normalizedFilename)
      if (
        manifestItem == null ||
        normalizeDistributionName(manifestItem.distribution || '') !== normalizedDistribution ||
        manifestItem.version !== entry.version ||
        manifestItem.size_bytes !== entry.size_bytes ||
        manifestItem.sha256.toLowerCase() !== entry.sha256.toLowerCase() ||
        !Array.isArray(manifestItem.scopes) ||
        !manifestItem.scopes.includes(expectedScope)
      ) {
        throw new Error(`Bundled runtime lock and manifest disagree for ${entry.filename}`)
      }
      allLockEntries.push(entry)
    }
    return entries as BundledRuntimeLockEntry[]
  }

  runtimeLock.host_runtime = validateScope(runtimeLock.host_runtime, 'host_runtime')
  runtimeLock.plugin_runtime = validateScope(runtimeLock.plugin_runtime, 'plugin_runtime')
  runtimeLock.plugins = validateScope(runtimeLock.plugins, 'plugin')
  if (runtimeLock.plugins.length !== 23) {
    throw new Error(
      `Bundled runtime lock must contain exactly 23 plugin distributions; got ${runtimeLock.plugins.length}`
    )
  }
  if (
    allLockEntries.length !== wheelFiles.length ||
    allLockEntries.length !== manifest.wheels.length
  ) {
    throw new Error('Bundled runtime lock must classify every manifest wheel exactly once')
  }

  const protectedHost = contract.protected_host_distributions.map(normalizeDistributionName).sort()
  const actualHost = runtimeLock.host_runtime
    .map(item => normalizeDistributionName(item.distribution))
    .sort()
  if (
    new Set(protectedHost).size !== protectedHost.length ||
    protectedHost.join('\n') !== actualHost.join('\n')
  ) {
    throw new Error('Bundled runtime lock protected host distribution set is inconsistent')
  }

  const lockedEntryPoints = validatePluginEntryPoints(
    runtimeLock.expected_plugin_entry_points,
    'Bundled runtime lock expected_plugin_entry_points'
  )
  const pluginEntryPoints = validatePluginEntryPoints(
    runtimeLock.plugins.flatMap(item => item.entry_points ?? []),
    'Bundled runtime lock plugin wheel entry points'
  )
  const manifestEntryPoints = validatePluginEntryPoints(
    manifest.wheels.flatMap(item => item.entry_points ?? []),
    'Bundled wheel manifest plugin entry points'
  )
  const expectedKeys = lockedEntryPoints.map(entryPointKey).sort()
  if (
    expectedKeys.length !== 21 ||
    expectedKeys.join('\n') !== pluginEntryPoints.map(entryPointKey).sort().join('\n') ||
    expectedKeys.join('\n') !== manifestEntryPoints.map(entryPointKey).sort().join('\n')
  ) {
    throw new Error(
      'Bundled runtime lock and manifest must agree on exactly 21 plugin entry points'
    )
  }

  return runtimeLock
}

/**
 * Bind a snapshot marker to the exact complete wheelhouse that will be deployed.
 *
 * The wheel manifest already authenticates every wheel and the runtime lock. This
 * additional contract prevents packaging a valid but stale/different wheelhouse
 * next to an unrelated integration snapshot marker.
 */
export function verifyBundledSnapshotWheelhouseContract(
  wheelsDir: string,
  contract: BundledSnapshotWheelhouseContract
): BundledRuntimeLock {
  if (
    contract == null ||
    contract.manifest_schema_version !== 3 ||
    contract.runtime_lock_schema_version !== 1 ||
    !Number.isSafeInteger(contract.wheel_count) ||
    contract.wheel_count <= 0 ||
    !Number.isSafeInteger(contract.plugin_distribution_count) ||
    contract.plugin_distribution_count <= 0 ||
    !Number.isSafeInteger(contract.plugin_entry_point_count) ||
    contract.plugin_entry_point_count <= 0 ||
    typeof contract.core_distribution_version !== 'string' ||
    !contract.core_distribution_version.trim() ||
    typeof contract.manifest_sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/i.test(contract.manifest_sha256) ||
    typeof contract.runtime_lock_sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/i.test(contract.runtime_lock_sha256)
  ) {
    throw new Error('Bundled snapshot wheelhouse contract has an unsupported schema')
  }

  const runtimeLock = readAndVerifyBundledRuntimeLock(wheelsDir)
  const manifestPath = path.join(wheelsDir, 'manifest.json')
  const runtimeLockPath = path.join(wheelsDir, 'runtime-lock.json')
  const manifest = readJsonFileWithOptionalBom<BundledWheelManifest>(manifestPath)
  const wheelCount = listBundledWheelFiles(wheelsDir).length
  const coreEntries = runtimeLock.plugins.filter(
    entry => normalizeDistributionName(entry.distribution) === 'auto-mas-core'
  )

  const mismatches: string[] = []
  if (manifest.schema_version !== contract.manifest_schema_version) {
    mismatches.push(
      `manifest schema expected ${contract.manifest_schema_version}, got ${manifest.schema_version ?? '<missing>'}`
    )
  }
  if (runtimeLock.schema_version !== contract.runtime_lock_schema_version) {
    mismatches.push(
      `runtime lock schema expected ${contract.runtime_lock_schema_version}, got ${runtimeLock.schema_version}`
    )
  }
  if (wheelCount !== contract.wheel_count) {
    mismatches.push(`wheel count expected ${contract.wheel_count}, got ${wheelCount}`)
  }
  if (runtimeLock.plugins.length !== contract.plugin_distribution_count) {
    mismatches.push(
      `plugin distribution count expected ${contract.plugin_distribution_count}, got ${runtimeLock.plugins.length}`
    )
  }
  if (runtimeLock.expected_plugin_entry_points.length !== contract.plugin_entry_point_count) {
    mismatches.push(
      `plugin entry point count expected ${contract.plugin_entry_point_count}, got ${runtimeLock.expected_plugin_entry_points.length}`
    )
  }
  if (coreEntries.length !== 1 || coreEntries[0].version !== contract.core_distribution_version) {
    mismatches.push(
      `core distribution version expected ${contract.core_distribution_version}, got ${
        coreEntries.length === 1 ? coreEntries[0].version : `<${coreEntries.length} entries>`
      }`
    )
  }
  if (sha256File(manifestPath).toLowerCase() !== contract.manifest_sha256.toLowerCase()) {
    mismatches.push('manifest SHA-256 does not match the snapshot marker')
  }
  if (sha256File(runtimeLockPath).toLowerCase() !== contract.runtime_lock_sha256.toLowerCase()) {
    mismatches.push('runtime lock SHA-256 does not match the snapshot marker')
  }

  if (mismatches.length > 0) {
    throw new Error(`Bundled snapshot wheelhouse contract mismatch:\n- ${mismatches.join('\n- ')}`)
  }

  return runtimeLock
}

export function resolveLockedWheelPaths(
  wheelsDir: string,
  entries: BundledRuntimeLockEntry[]
): string[] {
  return entries.map(entry => resolveContainedPath(wheelsDir, entry.filename))
}
