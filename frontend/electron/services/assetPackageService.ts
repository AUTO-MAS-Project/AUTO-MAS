import type { ResourcePackageFailureCode } from '../../src/types/mascotPack'
import * as fs from 'fs'
import * as path from 'path'
import * as os from 'os'
import { Transform } from 'stream'
import { pipeline } from 'stream/promises'
import { crc32 } from 'zlib'
import { openPromise, type Entry, type ZipFile } from 'yauzl'

export const ASSET_PACKAGE_LIMITS = {
  manifestBytes: 256 * 1024,
  pathLength: 240,
} as const

// ZIP 与数据站分类上限一致；展开预算是客户端落盘预算，不是压缩比限制。
export const ASSET_CATEGORY_LIMITS = {
  theme: { archiveBytes: 100 * 1024 * 1024, extractedBytes: 400 * 1024 * 1024 },
  mascot: { archiveBytes: 50 * 1024 * 1024, extractedBytes: 200 * 1024 * 1024 },
} as const

export type AssetPackageKind = keyof typeof ASSET_CATEGORY_LIMITS
export interface ExtractedPackage<T> {
  manifest: T
  directory: string
  files: Array<{ path: string; source: string; mime: string }>
}

function readImageHeader(filePath: string): Buffer {
  const descriptor = fs.openSync(filePath, 'r')
  try {
    const header = Buffer.alloc(33)
    return header.subarray(0, fs.readSync(descriptor, header, 0, header.length, 0))
  } finally {
    fs.closeSync(descriptor)
  }
}

const zipOptions = { lazyEntries: true, validateEntrySizes: true, strictFileNames: true }

export async function detectAssetPackageKind(zipPath: string): Promise<AssetPackageKind> {
  const stat = await fs.promises.stat(zipPath)
  if (!stat.isFile() || stat.size > ASSET_CATEGORY_LIMITS.theme.archiveBytes)
    throw new AssetPackageError('TOO_LARGE', '资源 ZIP 无效或过大')
  const zip = await openPromise(zipPath, zipOptions)
  let hasTheme = false
  try {
    for await (const entry of zip.eachEntry()) {
      if (entry.fileName === 'mascot.json') return 'mascot'
      if (entry.fileName === 'theme.json') hasTheme = true
    }
  } finally {
    zip.close()
  }
  if (!hasTheme)
    throw new AssetPackageError('INVALID_MANIFEST', '资源包根目录缺少 theme.json 或 mascot.json')
  return 'theme'
}

async function readEntry(zip: ZipFile, entry: Entry, limit: number): Promise<Buffer> {
  if (entry.uncompressedSize > limit)
    throw new AssetPackageError('INVALID_MANIFEST', '资源包清单过大')
  const stream = await zip.openReadStreamPromise(entry)
  const chunks: Buffer[] = []
  let size = 0
  let checksum = 0
  for await (const chunk of stream) {
    const data: Buffer = chunk
    size += data.length
    if (size > limit) {
      stream.destroy()
      throw new AssetPackageError('INVALID_MANIFEST', '资源包清单过大')
    }
    checksum = crc32(data, checksum)
    chunks.push(data)
  }
  if (size !== entry.uncompressedSize || checksum !== entry.crc32)
    throw new AssetPackageError('CHECKSUM_MISMATCH', '资源包清单校验失败')
  return Buffer.concat(chunks, size)
}

const IMAGE_MIME: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
}

const APPEARANCE_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/
const WINDOWS_DEVICE_NAME = /^(?:con|prn|aux|nul|clock\$|com[1-9]|lpt[1-9])(?:\..*)?$/i

export type StoredFile = { path: string; data: Buffer; mime: string }

export class AssetPackageError extends Error {
  readonly code: PackageErrorCode

  constructor(code: PackageErrorCode, message: string) {
    super(message)
    this.name = 'AssetPackageError'
    this.code = code
  }
}

export function fail(message: string): never {
  throw new AssetPackageError('INVALID_PACKAGE', message)
}

export function assertPlainObject(value: unknown, name: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${name} 必须是对象`)
  }
  return value as Record<string, unknown>
}

export function assertString(value: unknown, name: string, maxLength: number): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > maxLength) {
    fail(`${name} 必须是 ${maxLength} 字符以内的非空文本`)
  }
  if ([...value].some(char => char.charCodeAt(0) < 0x20 || char === '\u007f')) {
    fail(`${name} 包含不可用字符`)
  }
  return value
}

export function assertOptionalNumber(
  value: unknown,
  name: string,
  min: number,
  max: number
): number | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) {
    fail(`${name} 超出允许范围`)
  }
  return value
}

export function assertAssetPath(value: unknown, requireAssetsDirectory: boolean): string {
  const assetPath = assertString(value, '资源路径', ASSET_PACKAGE_LIMITS.pathLength)
  if (
    assetPath.includes('\\') ||
    assetPath.includes('\u0000') ||
    assetPath.startsWith('/') ||
    assetPath.startsWith('//') ||
    /^[a-z]:/i.test(assetPath) ||
    assetPath.split('/').some(segment => segment === '' || segment === '.' || segment === '..')
  ) {
    fail('资源路径无效')
  }
  if (requireAssetsDirectory && !assetPath.startsWith('assets/')) fail('资源必须位于 assets 目录')
  const extension = path.posix.extname(assetPath).toLowerCase()
  if (!IMAGE_MIME[extension]) fail('图片资源只允许 PNG、JPEG 或 WebP')
  return assetPath
}

function validateEntryName(rawName: string): string {
  if (!rawName || rawName.length > ASSET_PACKAGE_LIMITS.pathLength || rawName.includes('\u0000')) {
    fail('ZIP 中包含无效文件名')
  }
  if (
    rawName.includes('\\') ||
    rawName.startsWith('/') ||
    rawName.startsWith('//') ||
    /^[a-z]:/i.test(rawName)
  ) {
    fail('ZIP 中包含绝对路径或 Windows 路径')
  }
  const segments = rawName.split('/')
  if (segments.some(segment => segment === '' || segment === '.' || segment === '..')) {
    fail('ZIP 中包含路径穿越')
  }
  if (segments.some(segment => /[<>:"|?*]/.test(segment) || /[. ]$/.test(segment))) {
    fail('ZIP 中包含 Windows 无效文件名')
  }
  if (segments.some(segment => WINDOWS_DEVICE_NAME.test(segment))) {
    fail('ZIP 中包含 Windows 保留文件名')
  }
  return rawName
}

function imageMimeAndMagic(relativePath: string, data: Buffer): string {
  const extension = path.posix.extname(relativePath).toLowerCase()
  const mime = IMAGE_MIME[extension]
  if (!mime) fail(`不支持的图片类型: ${relativePath}`)

  const isPng =
    data.length >= 8 &&
    data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
  const isJpeg = data.length >= 3 && data.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff]))
  const isWebp =
    data.length >= 12 &&
    data.subarray(0, 4).toString('ascii') === 'RIFF' &&
    data.subarray(8, 12).toString('ascii') === 'WEBP'
  if (
    (mime === 'image/png' && !isPng) ||
    (mime === 'image/jpeg' && !isJpeg) ||
    (mime === 'image/webp' && !isWebp)
  ) {
    fail(`图片内容与扩展名不匹配: ${relativePath}`)
  }
  return mime
}

function toDataUrl(file: StoredFile): string {
  return `data:${file.mime};base64,${file.data.toString('base64')}`
}

function ensureWithinRoot(root: string, candidate: string): string {
  const resolvedRoot = path.resolve(root)
  const resolvedCandidate = path.resolve(candidate)
  if (
    resolvedCandidate !== resolvedRoot &&
    !resolvedCandidate.startsWith(`${resolvedRoot}${path.sep}`)
  ) {
    throw new Error('资源路径超出专用目录')
  }
  return resolvedCandidate
}

// 只检查 base 以下的各级目录：userData 的上级被用户用 mklink /J 挪盘很常见，不能因此禁用外观。
function assertNoReparsePoint(base: string, target: string): void {
  const resolvedBase = path.resolve(base)
  let current = path.resolve(target)
  while (current !== resolvedBase) {
    if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) {
      throw new Error('资源目录不允许符号链接或目录联接')
    }
    const parent = path.dirname(current)
    if (parent === current) break
    current = parent
  }
}

export interface PackageManifest {
  formatVersion: 1
  id: string
  name: string
  description?: string
  preview?: string
}

export type PackageErrorCode =
  | ResourcePackageFailureCode
  | 'INVALID_PACKAGE'
  | 'INVALID_ANIMATION'
  | 'DUPLICATE_ID'
  | 'IMPORT_FAILED'
  | 'UNSUPPORTED'
export interface LoadedAssetPackage<T> {
  manifest: T
  assets: Record<string, string>
}
export interface PackageInstallResult<T> {
  success: boolean
  item?: LoadedAssetPackage<T>
  existing?: LoadedAssetPackage<T>
  code?: PackageErrorCode
  error?: string
}
interface AssetPackageFormat<T> {
  directoryName: 'appearances' | 'mascots'
  manifestName: 'theme.json' | 'mascot.json'
  normalize(value: unknown): T
  referencedPaths(manifest: T): string[]
  validateAssets(manifest: T, read: (assetPath: string) => Buffer): void
}

export function normalizePackageInfo(value: unknown, manifestName: string): PackageManifest {
  const raw = assertPlainObject(value, manifestName)
  if (raw.formatVersion !== 1) fail('不支持的资源包版本')
  const id = assertString(raw.id, 'id', 64)
  if (!APPEARANCE_ID.test(id)) fail('id 只能包含小写字母、数字、下划线和短横线')
  if (WINDOWS_DEVICE_NAME.test(id)) fail('id 不能使用 Windows 保留名')
  return {
    formatVersion: 1,
    id,
    name: assertString(raw.name, 'name', 80),
    ...(raw.description === undefined
      ? {}
      : { description: assertString(raw.description, 'description', 300) }),
    ...(raw.preview === undefined ? {} : { preview: assertAssetPath(raw.preview, false) }),
  }
}

/** 外观与桌宠共用 ZIP 校验和原子安装，清单与资源语义由各自模块负责。 */
export class AssetPackageStore<T extends PackageManifest> {
  constructor(private readonly format: AssetPackageFormat<T>) {}

  private get limits() {
    return ASSET_CATEGORY_LIMITS[this.format.manifestName === 'theme.json' ? 'theme' : 'mascot']
  }

  root(userDataPath: string): string {
    const root = ensureWithinRoot(userDataPath, path.join(userDataPath, this.format.directoryName))
    assertNoReparsePoint(userDataPath, root)
    return root
  }

  private directory(userDataPath: string, id: string): string {
    if (!APPEARANCE_ID.test(id) || WINDOWS_DEVICE_NAME.test(id)) throw new Error('资源包 ID 无效')
    const root = this.root(userDataPath)
    const directory = ensureWithinRoot(root, path.join(root, id))
    assertNoReparsePoint(root, directory)
    return directory
  }

  private readManifest(directory: string): T {
    const filePath = path.join(directory, this.format.manifestName)
    const stat = fs.lstatSync(filePath)
    if (!stat.isFile() || stat.isSymbolicLink()) fail(`${this.format.manifestName} 不是普通文件`)
    if (stat.size > ASSET_PACKAGE_LIMITS.manifestBytes) fail(`${this.format.manifestName} 过大`)
    const raw = fs.readFileSync(filePath, 'utf8')
    if (Buffer.byteLength(raw, 'utf8') > ASSET_PACKAGE_LIMITS.manifestBytes)
      fail(`${this.format.manifestName} 过大`)
    try {
      return this.format.normalize(JSON.parse(raw.replace(/^\uFEFF/, '')))
    } catch (error) {
      if (error instanceof AssetPackageError) throw error
      fail(
        `${this.format.manifestName} 无法解析: ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }

  private loadDirectory(
    directory: string,
    assetMode: 'all' | 'preview' = 'all'
  ): LoadedAssetPackage<T> {
    const manifest = this.validateDirectory(directory)
    const assets: Record<string, string> = {}
    const paths =
      assetMode === 'all'
        ? this.format.referencedPaths(manifest)
        : manifest.preview
          ? [manifest.preview]
          : []
    for (const assetPath of paths) {
      const candidate = ensureWithinRoot(directory, path.join(directory, ...assetPath.split('/')))
      const data = fs.readFileSync(candidate)
      assets[assetPath] = toDataUrl({
        path: assetPath,
        data,
        mime: imageMimeAndMagic(assetPath, data),
      })
    }
    return { manifest, assets }
  }

  private validateDirectory(directory: string): T {
    const manifest = this.readManifest(directory)
    const files = new Set<string>()
    let totalBytes = 0
    const visit = (current: string, relative = ''): void => {
      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        const entryPath = path.join(current, entry.name)
        const entryRelative = relative ? `${relative}/${entry.name}` : entry.name
        validateEntryName(entryRelative)
        if (entry.isSymbolicLink()) fail('已安装资源包包含符号链接')
        if (entry.isDirectory()) {
          visit(entryPath, entryRelative)
          continue
        }
        if (!entry.isFile() || files.has(entryRelative.toLowerCase()))
          fail('已安装资源包包含重复或特殊文件')
        files.add(entryRelative.toLowerCase())
        const stat = fs.statSync(entryPath)
        totalBytes += stat.size
        if (totalBytes > this.limits.extractedBytes)
          throw new AssetPackageError('EXTRACTION_LIMIT', '资源总大小超限')
      }
    }
    visit(directory)
    if (!files.has(this.format.manifestName)) fail(`缺少 ${this.format.manifestName}`)
    const allowed = new Set([
      this.format.manifestName,
      ...this.format.referencedPaths(manifest).map(value => value.toLowerCase()),
    ])
    for (const file of files) {
      if (!allowed.has(file)) fail(`包含未声明文件: ${file}`)
    }
    for (const assetPath of this.format.referencedPaths(manifest)) {
      const candidate = ensureWithinRoot(directory, path.join(directory, ...assetPath.split('/')))
      if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile())
        fail(`资源不存在: ${assetPath}`)
      imageMimeAndMagic(assetPath, readImageHeader(candidate))
    }
    this.format.validateAssets(manifest, assetPath =>
      readImageHeader(path.join(directory, ...assetPath.split('/')))
    )
    return manifest
  }

  async readArchive(zipPath: string, parent = os.tmpdir()): Promise<ExtractedPackage<T>> {
    const archiveStat = await fs.promises.stat(zipPath)
    if (!archiveStat.isFile()) fail('选择的路径不是文件')
    if (archiveStat.size > this.limits.archiveBytes)
      throw new AssetPackageError('TOO_LARGE', '资源 ZIP 文件过大')

    let manifestData: Buffer | undefined
    let declaredTotal = 0
    const index = await openPromise(zipPath, zipOptions)
    try {
      for await (const entry of index.eachEntry()) {
        const name = validateEntryName(entry.fileName.replace(/\/$/, ''))
        const directory = entry.fileName.endsWith('/')
        if (((entry.externalFileAttributes >>> 16) & 0xf000) === 0xa000)
          fail('ZIP 中不允许符号链接')
        if (directory) continue
        if (!Number.isSafeInteger(entry.uncompressedSize) || entry.uncompressedSize < 0)
          fail(`ZIP 文件过大: ${name}`)
        if (entry.uncompressedSize === 0) fail(`ZIP 文件为空: ${name}`)
        declaredTotal += entry.uncompressedSize
        if (declaredTotal > this.limits.extractedBytes)
          throw new AssetPackageError('EXTRACTION_LIMIT', 'ZIP 解压总大小超限')
        if (name === this.format.manifestName) {
          if (manifestData) fail('ZIP 中包含重复文件名')
          manifestData = await readEntry(index, entry, ASSET_PACKAGE_LIMITS.manifestBytes)
        }
      }
    } finally {
      index.close()
    }
    if (!manifestData)
      throw new AssetPackageError(
        'INVALID_MANIFEST',
        `${this.format.manifestName} 必须在 ZIP 根目录`
      )
    let manifest: T
    try {
      manifest = this.format.normalize(
        JSON.parse(manifestData.toString('utf8').replace(/^\uFEFF/, ''))
      )
    } catch (error) {
      if (error instanceof AssetPackageError) throw error
      fail(
        `${this.format.manifestName} 无法解析: ${error instanceof Error ? error.message : String(error)}`
      )
    }
    await fs.promises.mkdir(parent, { recursive: true })
    const space = await fs.promises.statfs(parent)
    if (space.bavail * space.bsize < declaredTotal)
      throw new AssetPackageError('NO_SPACE', '磁盘空间不足，无法解压资源包')
    const directory = await fs.promises.mkdtemp(path.join(parent, '.import-'))
    const files: ExtractedPackage<T>['files'] = []
    const expected = new Set(
      this.format.referencedPaths(manifest).map(value => value.toLowerCase())
    )
    const seen = new Set<string>()
    let written = 0
    let zip: ZipFile | undefined
    try {
      zip = await openPromise(zipPath, zipOptions)
      for await (const entry of zip.eachEntry()) {
        const name = validateEntryName(entry.fileName.replace(/\/$/, ''))
        if (((entry.externalFileAttributes >>> 16) & 0xf000) === 0xa000)
          fail('ZIP 中不允许符号链接')
        if (entry.fileName.endsWith('/')) continue
        const key = name.toLowerCase()
        if (seen.has(key)) fail('ZIP 中包含重复文件名')
        if (name !== this.format.manifestName && !expected.has(key)) fail(`包含未声明文件: ${name}`)
        seen.add(key)
        if (
          name === this.format.manifestName &&
          entry.uncompressedSize > ASSET_PACKAGE_LIMITS.manifestBytes
        )
          throw new AssetPackageError('INVALID_MANIFEST', '资源包清单过大')
        const destination = ensureWithinRoot(directory, path.join(directory, ...name.split('/')))
        await fs.promises.mkdir(path.dirname(destination), { recursive: true })
        let checksum = 0
        let entryBytes = 0
        const budget = new Transform({
          transform: (chunk: Buffer, _encoding, callback) => {
            written += chunk.length
            entryBytes += chunk.length
            if (written > this.limits.extractedBytes) {
              callback(new AssetPackageError('EXTRACTION_LIMIT', 'ZIP 解压总大小超限'))
              return
            }
            checksum = crc32(chunk, checksum)
            callback(null, chunk)
          },
        })
        await pipeline(
          await zip.openReadStreamPromise(entry),
          budget,
          fs.createWriteStream(destination, { highWaterMark: 64 * 1024, flags: 'wx' })
        )
        if (entryBytes !== entry.uncompressedSize || checksum !== entry.crc32)
          throw new AssetPackageError('CHECKSUM_MISMATCH', `ZIP 文件校验失败: ${name}`)
        if (name === this.format.manifestName) {
          if (!(await fs.promises.readFile(destination)).equals(manifestData))
            throw new AssetPackageError('PACKAGE_CHANGED', '资源包清单在读取期间发生变化')
        } else {
          files.push({
            path: name,
            source: destination,
            mime: imageMimeAndMagic(name, readImageHeader(destination)),
          })
        }
      }
      for (const name of expected) if (!seen.has(name)) fail(`缺少资源: ${name}`)
      if (!seen.has(this.format.manifestName)) fail(`缺少 ${this.format.manifestName}`)
      this.format.validateAssets(manifest, assetPath =>
        readImageHeader(path.join(directory, ...assetPath.split('/')))
      )
      return { manifest, files, directory }
    } catch (error) {
      await fs.promises.rm(directory, { recursive: true, force: true })
      throw error
    } finally {
      zip?.close()
    }
  }

  install(
    userDataPath: string,
    pack: ExtractedPackage<T>,
    replace = false
  ): PackageInstallResult<T> {
    try {
      const { manifest, files } = pack
      const root = this.root(userDataPath)
      fs.mkdirSync(root, { recursive: true })
      const target = this.directory(userDataPath, manifest.id)
      if (fs.existsSync(target)) {
        if (!replace) {
          let existing: LoadedAssetPackage<T> | undefined
          try {
            existing = this.loadDirectory(target)
          } catch {
            // 损坏的旧包也要走明确的替换流程，不能阻塞用户修复它。
          }
          return {
            success: false,
            code: 'DUPLICATE_ID',
            error: '已有相同 ID 的资源包',
            ...(existing ? { existing } : {}),
          }
        }
      }

      const required = files.reduce((total, file) => total + fs.statSync(file.source).size, 0)
      if (required > this.limits.extractedBytes)
        throw new AssetPackageError('EXTRACTION_LIMIT', '资源总大小超限')
      const reuse = path.dirname(pack.directory) === root
      const space = fs.statfsSync(root)
      if (!reuse && space.bavail * space.bsize < required)
        throw new AssetPackageError('NO_SPACE', '磁盘空间不足，无法安装资源包')
      const temp = reuse ? pack.directory : fs.mkdtempSync(path.join(root, '.import-'))
      try {
        fs.writeFileSync(
          path.join(temp, this.format.manifestName),
          `${JSON.stringify(manifest, null, 2)}\n`,
          'utf8'
        )
        if (!reuse)
          for (const file of files) {
            const destination = ensureWithinRoot(temp, path.join(temp, ...file.path.split('/')))
            fs.mkdirSync(path.dirname(destination), { recursive: true })
            fs.copyFileSync(file.source, destination)
          }
        // 先完成图片转换，避免替换旧包后才发现资源无法加载。
        const item = this.loadDirectory(temp)

        let backup: string | undefined
        if (fs.existsSync(target)) {
          backup = path.join(root, `.backup-${manifest.id}-${Date.now()}`)
          fs.renameSync(target, backup)
        }
        try {
          fs.renameSync(temp, target)
        } catch (error) {
          if (backup && fs.existsSync(backup) && !fs.existsSync(target))
            fs.renameSync(backup, target)
          throw error
        }
        if (backup && fs.existsSync(backup)) {
          try {
            fs.rmSync(backup, { recursive: true, force: true })
          } catch {
            // 新包已原子落地，清理旧备份失败不影响应用；下次导入时仍会忽略隐藏备份目录。
          }
        }
        return { success: true, item }
      } catch (error) {
        if (fs.existsSync(temp)) fs.rmSync(temp, { recursive: true, force: true })
        throw error
      }
    } catch (error) {
      const code = error instanceof AssetPackageError ? error.code : 'IMPORT_FAILED'
      return {
        success: false,
        code,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }

  list(userDataPath: string, assetMode: 'all' | 'preview' = 'all'): LoadedAssetPackage<T>[] {
    let root: string
    try {
      root = this.root(userDataPath)
    } catch {
      return []
    }
    if (!fs.existsSync(root)) return []
    const results: LoadedAssetPackage<T>[] = []
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(root, { withFileTypes: true })
    } catch {
      return []
    }
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith('.')) continue
      try {
        const directory = this.directory(userDataPath, entry.name)
        const item = this.loadDirectory(directory, assetMode)
        const manifest = item.manifest
        if (manifest.id !== entry.name) continue
        results.push(item)
      } catch {
        // 旧的或损坏的外观包不能阻塞其他包加载；导入/移除时仍给出明确错误。
      }
    }
    return results.sort((left, right) => left.manifest.name.localeCompare(right.manifest.name))
  }

  get(userDataPath: string, id: string): LoadedAssetPackage<T> | null {
    try {
      const directory = this.directory(userDataPath, id)
      if (!fs.existsSync(directory)) return null
      return this.loadDirectory(directory)
    } catch {
      return null
    }
  }

  /**
   * 外观包确实已不存在或内容无效时返回 true；读文件被占用等暂时性 IO 错误直接抛出，
   * 避免调用方据此永久清掉用户的外观选择。
   */
  isGone(userDataPath: string, id: string): boolean {
    const directory = this.directory(userDataPath, id)
    if (!fs.existsSync(directory)) return true
    try {
      this.validateDirectory(directory)
      return false
    } catch (error) {
      if (error instanceof AssetPackageError) return true
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return true
      throw error
    }
  }

  remove(userDataPath: string, id: string): { success: boolean; error?: string } {
    try {
      const directory = this.directory(userDataPath, id)
      if (!fs.existsSync(directory)) return { success: false, error: '外观不存在' }
      const stat = fs.lstatSync(directory)
      if (!stat.isDirectory() || stat.isSymbolicLink())
        return { success: false, error: '外观目录无效' }
      fs.rmSync(directory, { recursive: true, force: false })
      return { success: true }
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) }
    }
  }
}
