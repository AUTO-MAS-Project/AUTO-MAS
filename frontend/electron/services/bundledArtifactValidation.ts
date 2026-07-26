import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import { pipeline } from 'stream/promises'

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

/**
 * 单个 wheel 的流式读取块大小与并发度。
 *
 * 一次性 ``readFileSync`` 整个 wheelhouse 会把主进程事件循环阻塞整整一轮哈希
 * （实测 127 wheel / 146 MiB 在热 page cache 下约 100ms，冷盘可达秒级），
 * 期间所有 ``ipcMain.handle`` 排队。流式读取让每个 chunk 之间都能回到事件循环。
 */
const WHEEL_DIGEST_CHUNK_BYTES = 1024 * 1024
const WHEEL_DIGEST_CONCURRENCY = 4

function sha256File(filePath: string): string {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')
}

/** 流式 SHA-256：与 {@link sha256File} 结果一致，但不阻塞事件循环。 */
async function sha256FileStreaming(filePath: string): Promise<string> {
  const hash = crypto.createHash('sha256')
  await pipeline(fs.createReadStream(filePath, { highWaterMark: WHEEL_DIGEST_CHUNK_BYTES }), hash)
  return hash.digest('hex')
}

/** 有界并发地流式哈希一组文件，返回与入参同序的摘要数组。 */
async function sha256FilesStreaming(filePaths: string[]): Promise<string[]> {
  const digests = new Array<string>(filePaths.length)
  let nextIndex = 0
  const hashNext = async (): Promise<void> => {
    for (;;) {
      const index = nextIndex
      nextIndex += 1
      if (index >= filePaths.length) {
        return
      }
      digests[index] = await sha256FileStreaming(filePaths[index])
    }
  }
  const workerCount = Math.min(WHEEL_DIGEST_CONCURRENCY, filePaths.length)
  await Promise.all(Array.from({ length: workerCount }, () => hashNext()))
  return digests
}

/**
 * 解析 wheel 文件名中的 distribution 与 version。
 *
 * Wheel 文件名规范: ``<distribution>-<version>(-<rest>)*<python_tag>-<abi_tag>-<platform_tag>.whl``
 * 这里只关心前两段；任何无法识别的文件名返回 ``null``，由调用方决定如何处理。
 */
export function parseWheelFilenameParts(
  filename: string
): { distribution: string; version: string } | null {
  if (!filename || !filename.toLowerCase().endsWith('.whl')) {
    return null
  }
  const parts = filename.slice(0, -4).split('-')
  if (parts.length < 5 || !parts[0] || !parts[1]) {
    return null
  }
  return { distribution: parts[0], version: parts[1] }
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

interface BundledWheelInventory {
  wheelFiles: string[]
  /** manifest 声明的 wheel，按小写文件名索引，保持 manifest 声明顺序。 */
  declaredByName: Map<string, BundledWheelManifestItem>
}

/**
 * 校验 wheelhouse 的结构与元数据：manifest 可解析、声明集合与磁盘文件集合一一对应、
 * 每个 wheel 的字节大小与声明一致、无同分发多版本。
 *
 * 这一步只做 readdir/statSync 与 manifest.json 的解析（实测约 1ms），不读取任何
 * wheel 内容；内容摘要由 {@link verifyBundledWheelDirectory}（同步）或
 * {@link verifyBundledWheelDigestsAsync}（流式）单独完成。
 */
function collectBundledWheelInventory(wheelsDir: string): BundledWheelInventory {
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
  const declaredDistributionVersions = new Map<string, { filename: string; version: string }>()
  for (const item of manifest.wheels) {
    assertSafeWheelRecord(item as BundledRuntimeLockEntry, 'Bundled wheel manifest')

    const normalizedFilename = item.filename.toLowerCase()
    if (declaredByName.has(normalizedFilename)) {
      throw new Error(`Bundled wheel manifest contains a duplicate: ${item.filename}`)
    }
    declaredByName.set(normalizedFilename, item)

    // Lane 13 P0: 同分发多版本静默覆盖检测。manifest 内每条记录可以显式声明
    // distribution/version；缺失时回退到 wheel 文件名解析，确保始终能比对。
    const declaredDistribution = normalizeDistributionName(item.distribution || '')
    const declaredVersion = typeof item.version === 'string' ? item.version : ''
    const parsedFromFilename = parseWheelFilenameParts(item.filename)
    const effectiveDistribution =
      declaredDistribution || normalizeDistributionName(parsedFromFilename?.distribution || '')
    const effectiveVersion = declaredVersion || parsedFromFilename?.version || ''
    if (effectiveDistribution && effectiveVersion) {
      const previous = declaredDistributionVersions.get(effectiveDistribution)
      if (previous !== undefined && previous.version !== effectiveVersion) {
        throw new Error(
          `Bundled wheel manifest declares multiple versions for distribution "${effectiveDistribution}": ` +
            `"${previous.version}" (${previous.filename}) vs "${effectiveVersion}" (${item.filename}). ` +
            `Offline bootstrap must ship exactly one version per distribution.`
        )
      }
      if (previous === undefined) {
        declaredDistributionVersions.set(effectiveDistribution, {
          filename: item.filename,
          version: effectiveVersion,
        })
      }
    }
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
  }

  return { wheelFiles, declaredByName }
}

function assertWheelDigest(item: BundledWheelManifestItem, actualSha256: string): void {
  if (actualSha256.toLowerCase() !== item.sha256.toLowerCase()) {
    throw new Error(`Bundled wheel SHA-256 mismatch: ${item.filename}`)
  }
}

/**
 * 只做结构/大小校验，不读取 wheel 内容。
 *
 * 供"本次启动不需要安装"的快路径使用：仍能拦截缺失、多余、被截断或被替换成不同
 * 长度的 wheel，但不再为一次纯跳过的启动付出全量哈希代价。
 */
export function verifyBundledWheelDirectoryMetadata(wheelsDir: string): string[] {
  return collectBundledWheelInventory(wheelsDir).wheelFiles
}

/** 全量校验（结构 + 同步内容摘要）。保持原有同步 API 供构建脚本与测试使用。 */
export function verifyBundledWheelDirectory(wheelsDir: string): string[] {
  const inventory = collectBundledWheelInventory(wheelsDir)
  for (const item of inventory.declaredByName.values()) {
    assertWheelDigest(item, sha256File(path.join(wheelsDir, item.filename)))
  }
  return inventory.wheelFiles
}

/**
 * 全量校验（结构 + 流式内容摘要），不阻塞事件循环。
 *
 * 必须在任何把 wheelhouse 交给 uv 之前调用。摘要比对在全部哈希完成后按 manifest
 * 声明顺序进行，因此错误信息与同步版本完全一致、与并发调度无关。
 */
export async function verifyBundledWheelDigestsAsync(wheelsDir: string): Promise<string[]> {
  const inventory = collectBundledWheelInventory(wheelsDir)
  const items = [...inventory.declaredByName.values()]
  const digests = await sha256FilesStreaming(items.map(item => path.join(wheelsDir, item.filename)))
  for (let index = 0; index < items.length; index += 1) {
    assertWheelDigest(items[index], digests[index])
  }
  return inventory.wheelFiles
}

/**
 * Verify the complete runtime lock and return its immutable install plan.
 * A plugin-only seed manifest is deliberately rejected here.
 */
export function readAndVerifyBundledRuntimeLock(wheelsDir: string): BundledRuntimeLock {
  return completeRuntimeLockVerification(wheelsDir, verifyBundledWheelDirectory(wheelsDir))
}

/**
 * 与 {@link readAndVerifyBundledRuntimeLock} 校验完全相同的清单/锁文件契约，
 * 但跳过 127 个 wheel 的内容摘要（仍校验 runtime-lock.json 自身的摘要）。
 *
 * 用于在决定"是否真的需要安装"之前拿到 install plan：这一步不会把任何 wheel 交给
 * uv，真正安装前必须再调用 {@link verifyBundledWheelDigestsAsync}。
 */
export function readBundledRuntimeLockMetadata(wheelsDir: string): BundledRuntimeLock {
  return completeRuntimeLockVerification(wheelsDir, verifyBundledWheelDirectoryMetadata(wheelsDir))
}

function completeRuntimeLockVerification(
  wheelsDir: string,
  wheelFiles: string[]
): BundledRuntimeLock {
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
  const seenDistributions = new Map<
    string,
    { scope: BundledRuntimeWheelScope; version: string; filename: string }
  >()
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
      const previous = seenDistributions.get(normalizedDistribution)
      if (previous !== undefined) {
        // Lane 13 P0: 错误信息必须明确给出 distribution / 已记录版本 / 当前版本 / 已记录文件 / 当前文件，
        // 让"同分发多版本静默覆盖"在生产中可被一眼诊断。跨 scope 同名也归入此类，但区分
        // "cross-scope"与"same-scope duplicate"两种语义，避免误导。
        const scopeRelation =
          previous.scope === expectedScope ? 'same-scope duplicate' : 'cross-scope duplicate'
        if (previous.version !== entry.version) {
          throw new Error(
            `Bundled runtime lock declares multiple versions for distribution "${entry.distribution}" ` +
              `(${scopeRelation}): "${previous.version}" (${previous.filename}, scope=${previous.scope}) ` +
              `vs "${entry.version}" (${entry.filename}, scope=${expectedScope}). ` +
              `Offline bootstrap must ship exactly one version per distribution.`
          )
        }
        throw new Error(
          `Bundled runtime lock declares duplicate entries for distribution "${entry.distribution}" ` +
            `(${scopeRelation}): "${previous.version}" appears in both ${previous.filename} ` +
            `(scope=${previous.scope}) and ${entry.filename} (scope=${expectedScope}).`
        )
      }
      seenDistributions.set(normalizedDistribution, {
        scope: expectedScope,
        version: entry.version,
        filename: entry.filename,
      })
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
