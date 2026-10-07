import * as fs from 'fs'
import * as path from 'path'
import AdmZip = require('adm-zip')

type AppearanceMode = 'light' | 'dark'
const APPEARANCE_MENU_ICON_KEYS = [
  'home',
  'scripts',
  'plans',
  'emulators',
  'queue',
  'scheduler',
  'gameSign',
  'history',
  'tools',
  'settings',
  'testRouter',
  'ocrDev',
  'overlayMaskDev',
  'updateDownloadDev',
] as const
type AppearanceMenuIconKey = (typeof APPEARANCE_MENU_ICON_KEYS)[number]
type AppearanceMenuIcons = Partial<Record<AppearanceMenuIconKey, string>>
const APPEARANCE_CURSOR_KEYS = ['default', 'pointer', 'text'] as const
type AppearanceCursorKey = (typeof APPEARANCE_CURSOR_KEYS)[number]
interface AppearanceCursor {
  path: string
  hotspotX: number
  hotspotY: number
}
type AppearanceCursors = Partial<Record<AppearanceCursorKey, AppearanceCursor>>
interface AppearanceTokens {
  colorPrimary: string
  colorBgLayout?: string
  colorBgContainer?: string
  colorBgElevated?: string
  colorText?: string
  colorTextSecondary?: string
  colorBorder?: string
  colorBorderSecondary?: string
  borderRadius?: number
}
interface AppearanceBackground {
  path: string
  opacity?: number
  surfaceOpacity?: number
  position?: string
  size?: 'cover' | 'contain' | 'auto'
}
interface AppearanceMascot {
  path: string
  width?: number
  opacity?: number
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
}
interface AppearanceManifest {
  formatVersion: 1
  id: string
  name: string
  description?: string
  mode: AppearanceMode
  tokens: AppearanceTokens
  background?: AppearanceBackground
  mascot?: AppearanceMascot
  preview?: string
  menuIcons?: AppearanceMenuIcons
  cursors?: AppearanceCursors
}
interface InstalledAppearance extends AppearanceManifest {
  previewUrl?: string
  backgroundUrl?: string
  mascotUrl?: string
  menuIconUrls?: Partial<Record<AppearanceMenuIconKey, string>>
  cursorUrls?: Partial<Record<AppearanceCursorKey, string>>
}
interface AppearanceImportResult {
  success: boolean
  appearance?: InstalledAppearance
  code?: 'INVALID_PACKAGE' | 'DUPLICATE_ID' | 'IMPORT_FAILED' | 'UNSUPPORTED'
  error?: string
  existing?: InstalledAppearance
}

export const APPEARANCE_LIMITS = {
  archiveBytes: 16 * 1024 * 1024,
  extractedBytes: 32 * 1024 * 1024,
  entries: 32,
  singleFileBytes: 8 * 1024 * 1024,
  manifestBytes: 256 * 1024,
  pathLength: 240,
} as const

const IMAGE_MIME: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i
const APPEARANCE_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/
const WINDOWS_DEVICE_NAME = /^(?:con|prn|aux|nul|clock\$|com[1-9]|lpt[1-9])(?:\..*)?$/i
const POSITION = /^(?:left|center|right)(?:\s+(?:top|center|bottom))?$/

type StoredFile = { path: string; data: Buffer; mime: string }

export class AppearanceError extends Error {
  readonly code: AppearanceImportResult['code']

  constructor(code: NonNullable<AppearanceImportResult['code']>, message: string) {
    super(message)
    this.name = 'AppearanceError'
    this.code = code
  }
}

function fail(message: string): never {
  throw new AppearanceError('INVALID_PACKAGE', message)
}

function assertPlainObject(value: unknown, name: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${name} 必须是对象`)
  }
  return value as Record<string, unknown>
}

function assertString(value: unknown, name: string, maxLength: number): string {
  if (typeof value !== 'string' || value.length === 0 || value.length > maxLength) {
    fail(`${name} 必须是 ${maxLength} 字符以内的非空文本`)
  }
  if ([...value].some(char => char.charCodeAt(0) < 0x20 || char === '\u007f')) {
    fail(`${name} 包含不可用字符`)
  }
  return value
}

function assertOptionalHex(value: unknown, name: string): string | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'string' || !HEX_COLOR.test(value)) fail(`${name} 必须是 #rrggbb 颜色`)
  return value.toLowerCase()
}

function assertOptionalNumber(
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

function assertHotspot(value: unknown, name: string): number {
  if (
    value === undefined ||
    typeof value !== 'number' ||
    !Number.isSafeInteger(value) ||
    value < 0 ||
    value > 63
  ) {
    if (value === undefined) return 0
    fail(`${name} 必须是 0 到 63 的整数`)
  }
  return value
}

function normalizeManifest(value: unknown): AppearanceManifest {
  const raw = assertPlainObject(value, 'theme.json')
  if (raw.formatVersion !== 1) fail('不支持的外观包版本')

  const id = assertString(raw.id, 'id', 64)
  if (!APPEARANCE_ID.test(id)) fail('id 只能包含小写字母、数字、下划线和短横线')
  if (WINDOWS_DEVICE_NAME.test(id)) fail('id 不能使用 Windows 保留名')
  const name = assertString(raw.name, 'name', 80)
  const description =
    raw.description === undefined ? undefined : assertString(raw.description, 'description', 300)

  if (raw.mode !== 'light' && raw.mode !== 'dark') fail('mode 必须是 light 或 dark')
  const rawTokens = assertPlainObject(raw.tokens, 'tokens')
  const colorPrimary = assertOptionalHex(rawTokens.colorPrimary, 'tokens.colorPrimary')
  if (!colorPrimary) fail('tokens.colorPrimary 是必填项')

  const tokens: AppearanceTokens = {
    colorPrimary,
    colorBgLayout: assertOptionalHex(rawTokens.colorBgLayout, 'tokens.colorBgLayout'),
    colorBgContainer: assertOptionalHex(rawTokens.colorBgContainer, 'tokens.colorBgContainer'),
    colorBgElevated: assertOptionalHex(rawTokens.colorBgElevated, 'tokens.colorBgElevated'),
    colorText: assertOptionalHex(rawTokens.colorText, 'tokens.colorText'),
    colorTextSecondary: assertOptionalHex(
      rawTokens.colorTextSecondary,
      'tokens.colorTextSecondary'
    ),
    colorBorder: assertOptionalHex(rawTokens.colorBorder, 'tokens.colorBorder'),
    colorBorderSecondary: assertOptionalHex(
      rawTokens.colorBorderSecondary,
      'tokens.colorBorderSecondary'
    ),
    borderRadius: assertOptionalNumber(rawTokens.borderRadius, 'tokens.borderRadius', 0, 32),
  }

  const background = normalizeBackground(raw.background)
  const mascot = normalizeMascot(raw.mascot)
  const preview = raw.preview === undefined ? undefined : assertAssetPath(raw.preview, false)
  const menuIcons = normalizeMenuIcons(raw.menuIcons)
  const cursors = normalizeCursors(raw.cursors)

  return {
    formatVersion: 1,
    id,
    name,
    ...(description === undefined ? {} : { description }),
    mode: raw.mode as AppearanceMode,
    tokens,
    ...(background === undefined ? {} : { background }),
    ...(mascot === undefined ? {} : { mascot }),
    ...(preview === undefined ? {} : { preview }),
    ...(menuIcons === undefined ? {} : { menuIcons }),
    ...(cursors === undefined ? {} : { cursors }),
  }
}

function normalizeMenuIcons(value: unknown): AppearanceMenuIcons | undefined {
  if (value === undefined) return undefined
  const raw = assertPlainObject(value, 'menuIcons')
  const menuIcons: AppearanceMenuIcons = {}
  for (const [key, assetPath] of Object.entries(raw)) {
    if (!(APPEARANCE_MENU_ICON_KEYS as readonly string[]).includes(key)) {
      fail(`menuIcons 包含未知菜单键: ${key}`)
    }
    menuIcons[key as AppearanceMenuIconKey] = assertAssetPath(assetPath, true)
  }
  return menuIcons
}

function normalizeCursors(value: unknown): AppearanceCursors | undefined {
  if (value === undefined) return undefined
  const raw = assertPlainObject(value, 'cursors')
  const cursors: AppearanceCursors = {}
  for (const [key, cursorValue] of Object.entries(raw)) {
    if (!(APPEARANCE_CURSOR_KEYS as readonly string[]).includes(key)) {
      fail(`cursors 包含未知光标键: ${key}`)
    }
    const cursor = assertPlainObject(cursorValue, `cursors.${key}`)
    const assetPath = assertAssetPath(cursor.path, true)
    if (path.posix.extname(assetPath).toLowerCase() !== '.png') {
      fail(`cursors.${key}.path 必须是 PNG 图片`)
    }
    cursors[key as AppearanceCursorKey] = {
      path: assetPath,
      hotspotX: assertHotspot(cursor.hotspotX, `cursors.${key}.hotspotX`),
      hotspotY: assertHotspot(cursor.hotspotY, `cursors.${key}.hotspotY`),
    }
  }
  return cursors
}

function normalizeBackground(value: unknown): AppearanceBackground | undefined {
  if (value === undefined) return undefined
  const raw = assertPlainObject(value, 'background')
  const pathValue = assertAssetPath(raw.path, true)
  const opacity = assertOptionalNumber(raw.opacity, 'background.opacity', 0, 1)
  const surfaceOpacity = assertOptionalNumber(raw.surfaceOpacity, 'background.surfaceOpacity', 0, 1)
  const position =
    raw.position === undefined ? undefined : assertString(raw.position, 'background.position', 32)
  if (position !== undefined && !POSITION.test(position)) fail('background.position 不受支持')
  const size = raw.size === undefined ? undefined : raw.size
  if (size !== undefined && size !== 'cover' && size !== 'contain' && size !== 'auto') {
    fail('background.size 不受支持')
  }
  return {
    path: pathValue,
    ...(opacity === undefined ? {} : { opacity }),
    ...(surfaceOpacity === undefined ? {} : { surfaceOpacity }),
    ...(position === undefined ? {} : { position }),
    ...(size === undefined ? {} : { size }),
  }
}

function normalizeMascot(value: unknown): AppearanceMascot | undefined {
  if (value === undefined) return undefined
  const raw = assertPlainObject(value, 'mascot')
  const pathValue = assertAssetPath(raw.path, true)
  const width = assertOptionalNumber(raw.width, 'mascot.width', 16, 1024)
  const opacity = assertOptionalNumber(raw.opacity, 'mascot.opacity', 0, 1)
  const position = raw.position === undefined ? undefined : raw.position
  if (
    position !== undefined &&
    position !== 'top-left' &&
    position !== 'top-right' &&
    position !== 'bottom-left' &&
    position !== 'bottom-right'
  ) {
    fail('mascot.position 不受支持')
  }
  return {
    path: pathValue,
    ...(width === undefined ? {} : { width }),
    ...(opacity === undefined ? {} : { opacity }),
    ...(position === undefined ? {} : { position }),
  }
}

function assertAssetPath(value: unknown, requireAssetsDirectory: boolean): string {
  const assetPath = assertString(value, '资源路径', APPEARANCE_LIMITS.pathLength)
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
  if (!IMAGE_MIME[extension]) fail('外观资源只允许 PNG、JPEG 或 WebP')
  return assetPath
}

function validateEntryName(rawName: string): string {
  if (!rawName || rawName.length > APPEARANCE_LIMITS.pathLength || rawName.includes('\u0000')) {
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

function isSymlink(entry: AdmZip.IZipEntry): boolean {
  // Unix mode is stored in the high 16 bits of the external attributes.
  const unixMode = (entry.attr >>> 16) & 0xffff
  return (unixMode & 0xf000) === 0xa000
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

function pngDimensions(relativePath: string, data: Buffer): { width: number; height: number } {
  if (imageMimeAndMagic(relativePath, data) !== 'image/png') {
    fail(`光标资源必须是 PNG 图片: ${relativePath}`)
  }
  if (
    data.length < 33 ||
    data.readUInt32BE(8) !== 13 ||
    data.subarray(12, 16).toString('ascii') !== 'IHDR'
  ) {
    fail(`PNG 缺少有效 IHDR: ${relativePath}`)
  }
  const width = data.readUInt32BE(16)
  const height = data.readUInt32BE(20)
  if (width < 1 || width > 64 || height < 1 || height > 64) {
    fail(`光标图片尺寸必须在 1 到 64 像素之间: ${relativePath}`)
  }
  return { width, height }
}

function validateCursorData(
  key: AppearanceCursorKey,
  cursor: AppearanceCursor,
  data: Buffer
): void {
  const { width, height } = pngDimensions(cursor.path, data)
  if (cursor.hotspotX >= width || cursor.hotspotY >= height) {
    fail(`cursors.${key} 的热点必须位于图片范围内`)
  }
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
    throw new Error('外观路径超出专用目录')
  }
  return resolvedCandidate
}

// 只检查 base 以下的各级目录：userData 的上级被用户用 mklink /J 挪盘很常见，不能因此禁用外观。
function assertNoReparsePoint(base: string, target: string): void {
  const resolvedBase = path.resolve(base)
  let current = path.resolve(target)
  while (current !== resolvedBase) {
    if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) {
      throw new Error('外观目录不允许符号链接或目录联接')
    }
    const parent = path.dirname(current)
    if (parent === current) break
    current = parent
  }
}

function appearanceRoot(userDataPath: string): string {
  const root = ensureWithinRoot(userDataPath, path.join(userDataPath, 'appearances'))
  assertNoReparsePoint(userDataPath, root)
  return root
}

function isValidAppearanceId(id: string): boolean {
  return APPEARANCE_ID.test(id) && !WINDOWS_DEVICE_NAME.test(id)
}

function appearanceDirectory(userDataPath: string, id: string): string {
  if (!isValidAppearanceId(id)) throw new Error('外观 ID 无效')
  const root = appearanceRoot(userDataPath)
  const directory = ensureWithinRoot(root, path.join(root, id))
  assertNoReparsePoint(root, directory)
  return directory
}

function manifestPath(directory: string): string {
  return path.join(directory, 'theme.json')
}

function readManifest(directory: string): AppearanceManifest {
  const filePath = manifestPath(directory)
  const stat = fs.lstatSync(filePath)
  if (!stat.isFile() || stat.isSymbolicLink()) fail('theme.json 不是普通文件')
  if (stat.size > APPEARANCE_LIMITS.manifestBytes) fail('theme.json 过大')
  const raw = fs.readFileSync(filePath, 'utf8')
  if (Buffer.byteLength(raw, 'utf8') > APPEARANCE_LIMITS.manifestBytes) fail('theme.json 过大')
  try {
    return normalizeManifest(JSON.parse(raw.replace(/^\uFEFF/, '')))
  } catch (error) {
    if (error instanceof AppearanceError) throw error
    fail(`theme.json 无法解析: ${error instanceof Error ? error.message : String(error)}`)
  }
}

function referencedPaths(manifest: AppearanceManifest): string[] {
  return [
    manifest.background?.path,
    manifest.mascot?.path,
    manifest.preview,
    ...Object.values(manifest.menuIcons ?? {}),
    ...Object.values(manifest.cursors ?? {}).map(cursor => cursor.path),
  ].filter((value): value is string => Boolean(value))
}

function validateInstalledDirectory(directory: string): AppearanceManifest {
  const manifest = readManifest(directory)
  const files = new Set<string>()
  let totalBytes = 0
  const visit = (current: string, relative = ''): void => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const entryPath = path.join(current, entry.name)
      const entryRelative = relative ? `${relative}/${entry.name}` : entry.name
      validateEntryName(entryRelative)
      if (entry.isSymbolicLink()) fail('已安装外观包含符号链接')
      if (entry.isDirectory()) {
        visit(entryPath, entryRelative)
        continue
      }
      if (!entry.isFile() || files.has(entryRelative.toLowerCase()))
        fail('已安装外观包含重复或特殊文件')
      files.add(entryRelative.toLowerCase())
      if (files.size > APPEARANCE_LIMITS.entries) fail('已安装外观文件数量超限')
      const stat = fs.statSync(entryPath)
      if (stat.size > APPEARANCE_LIMITS.singleFileBytes) fail('外观图片过大')
      totalBytes += stat.size
      if (totalBytes > APPEARANCE_LIMITS.extractedBytes) fail('外观总大小超限')
    }
  }
  visit(directory)
  if (!files.has('theme.json')) fail('缺少 theme.json')
  const allowed = new Set([
    'theme.json',
    ...referencedPaths(manifest).map(value => value.toLowerCase()),
  ])
  for (const file of files) {
    if (!allowed.has(file)) fail(`包含未声明文件: ${file}`)
  }
  for (const assetPath of referencedPaths(manifest)) {
    const candidate = ensureWithinRoot(directory, path.join(directory, ...assetPath.split('/')))
    if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile())
      fail(`资源不存在: ${assetPath}`)
    imageMimeAndMagic(assetPath, fs.readFileSync(candidate))
  }
  for (const [key, cursor] of Object.entries(manifest.cursors ?? {})) {
    const candidate = ensureWithinRoot(directory, path.join(directory, ...cursor.path.split('/')))
    validateCursorData(key as AppearanceCursorKey, cursor, fs.readFileSync(candidate))
  }
  return manifest
}

function serializeAppearance(directory: string, manifest: AppearanceManifest): InstalledAppearance {
  const getAsset = (assetPath: string | undefined): string | undefined => {
    if (!assetPath) return undefined
    const candidate = ensureWithinRoot(directory, path.join(directory, ...assetPath.split('/')))
    const data = fs.readFileSync(candidate)
    return toDataUrl({ path: assetPath, data, mime: imageMimeAndMagic(assetPath, data) })
  }
  const menuIconUrls: Partial<Record<AppearanceMenuIconKey, string>> = {}
  for (const [key, assetPath] of Object.entries(manifest.menuIcons ?? {})) {
    const url = getAsset(assetPath)
    if (url) menuIconUrls[key as AppearanceMenuIconKey] = url
  }
  const cursorUrls: Partial<Record<AppearanceCursorKey, string>> = {}
  for (const [key, cursor] of Object.entries(manifest.cursors ?? {})) {
    const url = getAsset(cursor.path)
    if (url) cursorUrls[key as AppearanceCursorKey] = url
  }
  return {
    ...manifest,
    ...(manifest.preview ? { previewUrl: getAsset(manifest.preview) } : {}),
    ...(manifest.background ? { backgroundUrl: getAsset(manifest.background.path) } : {}),
    ...(manifest.mascot ? { mascotUrl: getAsset(manifest.mascot.path) } : {}),
    ...(manifest.menuIcons ? { menuIconUrls } : {}),
    ...(manifest.cursors ? { cursorUrls } : {}),
  }
}

function parseArchive(zipPath: string): { manifest: AppearanceManifest; files: StoredFile[] } {
  const archiveStat = fs.statSync(zipPath)
  if (!archiveStat.isFile()) throw new AppearanceError('INVALID_PACKAGE', '选择的路径不是文件')
  if (archiveStat.size > APPEARANCE_LIMITS.archiveBytes) {
    throw new AppearanceError('INVALID_PACKAGE', '外观 ZIP 文件过大')
  }

  let zip: AdmZip
  try {
    zip = new AdmZip(zipPath)
  } catch (error) {
    throw new AppearanceError(
      'INVALID_PACKAGE',
      `无法读取外观 ZIP: ${error instanceof Error ? error.message : String(error)}`
    )
  }
  const entries = zip.getEntries()
  if (entries.length === 0 || entries.length > APPEARANCE_LIMITS.entries) {
    throw new AppearanceError('INVALID_PACKAGE', '外观 ZIP 文件数量超限')
  }

  // 最常见的打包错误是连外层文件夹一起压缩，先给出明确提示，别让它报成别的错。
  if (
    !entries.some(entry => entry.entryName === 'theme.json') &&
    entries.some(entry => path.posix.basename(entry.entryName) === 'theme.json')
  ) {
    fail('theme.json 必须在 ZIP 根目录：请选中外观包里的文件压缩，不要压缩外层文件夹')
  }

  const names = new Set<string>()
  let declaredTotal = 0
  let manifestData: Buffer | undefined
  const files: StoredFile[] = []
  for (const entry of entries) {
    const name = validateEntryName(
      entry.isDirectory && entry.entryName.endsWith('/')
        ? entry.entryName.slice(0, -1)
        : entry.entryName
    )
    if (names.has(name.toLowerCase())) fail('ZIP 中包含重复文件名')
    names.add(name.toLowerCase())
    if (entry.isDirectory) continue
    if (isSymlink(entry)) fail('ZIP 中不允许符号链接')
    const size = entry.header.size
    const compressedSize = entry.header.compressedSize
    if (!Number.isSafeInteger(size) || size < 0 || size > APPEARANCE_LIMITS.singleFileBytes) {
      fail(`ZIP 文件过大: ${name}`)
    }
    if (size === 0) fail(`ZIP 文件为空: ${name}`)
    if (!Number.isSafeInteger(compressedSize) || compressedSize <= 0) fail('ZIP 文件大小字段无效')
    declaredTotal += size
    if (declaredTotal > APPEARANCE_LIMITS.extractedBytes) fail('ZIP 解压总大小超限')
    let data: Buffer
    try {
      data = entry.getData()
    } catch (error) {
      fail(
        `ZIP 文件损坏或使用了不支持的压缩方式: ${name}（${error instanceof Error ? error.message : String(error)}）`
      )
    }
    if (data.length !== size) fail(`ZIP 文件大小校验失败: ${name}`)

    if (name === 'theme.json') {
      if (data.length > APPEARANCE_LIMITS.manifestBytes) fail('theme.json 过大')
      manifestData = data
      continue
    }
    const mime = imageMimeAndMagic(name, data)
    files.push({ path: name, data, mime })
  }
  if (!manifestData) fail('缺少 theme.json')

  let manifest: AppearanceManifest
  try {
    manifest = normalizeManifest(JSON.parse(manifestData.toString('utf8').replace(/^\uFEFF/, '')))
  } catch (error) {
    if (error instanceof AppearanceError) throw error
    fail(`theme.json 无法解析: ${error instanceof Error ? error.message : String(error)}`)
  }

  const expectedFiles = new Set(referencedPaths(manifest).map(value => value.toLowerCase()))
  for (const file of files) {
    if (!expectedFiles.has(file.path.toLowerCase())) fail(`包含未声明文件: ${file.path}`)
  }
  for (const expected of expectedFiles) {
    if (!files.some(file => file.path.toLowerCase() === expected)) fail(`缺少资源: ${expected}`)
  }
  if (files.length !== expectedFiles.size) fail('外观资源重复或未声明')
  for (const [key, cursor] of Object.entries(manifest.cursors ?? {})) {
    const file = files.find(item => item.path.toLowerCase() === cursor.path.toLowerCase())
    if (!file) fail(`缺少光标资源: ${cursor.path}`)
    validateCursorData(key as AppearanceCursorKey, cursor, file.data)
  }
  return { manifest, files }
}

export function getAppearanceRoot(userDataPath: string): string {
  return appearanceRoot(userDataPath)
}

export function validateAppearanceManifest(value: unknown): AppearanceManifest {
  return normalizeManifest(value)
}

export function importAppearancePackage(
  userDataPath: string,
  zipPath: string,
  replace = false
): AppearanceImportResult {
  try {
    const { manifest, files } = parseArchive(zipPath)
    const root = appearanceRoot(userDataPath)
    fs.mkdirSync(root, { recursive: true })
    const target = appearanceDirectory(userDataPath, manifest.id)
    if (fs.existsSync(target)) {
      if (!replace) {
        let existing: InstalledAppearance | undefined
        try {
          existing = serializeAppearance(target, validateInstalledDirectory(target))
        } catch {
          // 损坏的旧包也要走明确的替换流程，不能阻塞用户修复它。
        }
        return {
          success: false,
          code: 'DUPLICATE_ID',
          error: '已有相同 ID 的外观',
          ...(existing ? { existing } : {}),
        }
      }
    }

    const temp = fs.mkdtempSync(path.join(root, '.import-'))
    try {
      fs.writeFileSync(manifestPath(temp), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
      for (const file of files) {
        const destination = ensureWithinRoot(temp, path.join(temp, ...file.path.split('/')))
        fs.mkdirSync(path.dirname(destination), { recursive: true })
        fs.writeFileSync(destination, file.data)
      }
      validateInstalledDirectory(temp)

      let backup: string | undefined
      if (fs.existsSync(target)) {
        backup = path.join(root, `.backup-${manifest.id}-${Date.now()}`)
        fs.renameSync(target, backup)
      }
      try {
        fs.renameSync(temp, target)
      } catch (error) {
        if (backup && fs.existsSync(backup) && !fs.existsSync(target)) fs.renameSync(backup, target)
        throw error
      }
      if (backup && fs.existsSync(backup)) {
        try {
          fs.rmSync(backup, { recursive: true, force: true })
        } catch {
          // 新包已原子落地，清理旧备份失败不影响应用；下次导入时仍会忽略隐藏备份目录。
        }
      }
    } catch (error) {
      if (fs.existsSync(temp)) fs.rmSync(temp, { recursive: true, force: true })
      throw error
    }

    return { success: true, appearance: serializeAppearance(target, manifest) }
  } catch (error) {
    const code = error instanceof AppearanceError ? error.code : 'IMPORT_FAILED'
    return {
      success: false,
      code,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

export function listAppearances(userDataPath: string): InstalledAppearance[] {
  let root: string
  try {
    root = appearanceRoot(userDataPath)
  } catch {
    return []
  }
  if (!fs.existsSync(root)) return []
  const results: InstalledAppearance[] = []
  let entries: fs.Dirent[]
  try {
    entries = fs.readdirSync(root, { withFileTypes: true })
  } catch {
    return []
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.')) continue
    try {
      const directory = appearanceDirectory(userDataPath, entry.name)
      const manifest = validateInstalledDirectory(directory)
      if (manifest.id !== entry.name) continue
      results.push(serializeAppearance(directory, manifest))
    } catch {
      // 旧的或损坏的外观包不能阻塞其他包加载；导入/移除时仍给出明确错误。
    }
  }
  return results.sort((left, right) => left.name.localeCompare(right.name))
}

export function getAppearance(userDataPath: string, id: string): InstalledAppearance | null {
  try {
    const directory = appearanceDirectory(userDataPath, id)
    if (!fs.existsSync(directory)) return null
    const manifest = validateInstalledDirectory(directory)
    return serializeAppearance(directory, manifest)
  } catch {
    return null
  }
}

/**
 * 外观包确实已不存在或内容无效时返回 true；读文件被占用等暂时性 IO 错误直接抛出，
 * 避免调用方据此永久清掉用户的外观选择。
 */
export function isAppearanceGone(userDataPath: string, id: string): boolean {
  const directory = appearanceDirectory(userDataPath, id)
  if (!fs.existsSync(directory)) return true
  try {
    validateInstalledDirectory(directory)
    return false
  } catch (error) {
    if (error instanceof AppearanceError) return true
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return true
    throw error
  }
}

export function removeAppearance(
  userDataPath: string,
  id: string
): { success: boolean; error?: string } {
  try {
    const directory = appearanceDirectory(userDataPath, id)
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
