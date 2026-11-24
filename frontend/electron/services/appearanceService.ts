import * as path from 'path'
import type { MascotDefinition as AppearanceMascot } from '../../src/types/mascotPack'
import {
  AssetPackageError as AppearanceError,
  AssetPackageStore,
  assertAssetPath,
  assertOptionalNumber,
  assertPlainObject,
  assertString,
  fail,
  type LoadedAssetPackage,
} from './assetPackageService'
import { normalizeMascot, validateMascotAssets } from './mascotManifest'
export {
  ASSET_PACKAGE_LIMITS as APPEARANCE_LIMITS,
  AssetPackageError as AppearanceError,
} from './assetPackageService'

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
  'themeStore',
  'settings',
  'testRouter',
  'ocrDev',
  'overlayMaskDev',
  'updateDownloadDev',
] as const
type AppearanceMenuIconKey = (typeof APPEARANCE_MENU_ICON_KEYS)[number]
type AppearanceMenuIcons = Partial<Record<AppearanceMenuIconKey | 'default', string>>
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
  colorPageTitle?: string
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
  mascotAnimationUrl?: string
  mascotLookUrl?: string
  mascotResultUrl?: string
  mascotDragUrl?: string
  menuIconUrls?: AppearanceMenuIcons
  cursorUrls?: Partial<Record<AppearanceCursorKey, string>>
}
interface AppearanceImportResult {
  success: boolean
  appearance?: InstalledAppearance
  code?: 'INVALID_PACKAGE' | 'INVALID_ANIMATION' | 'DUPLICATE_ID' | 'IMPORT_FAILED' | 'UNSUPPORTED'
  error?: string
  existing?: InstalledAppearance
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i
const APPEARANCE_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/
const WINDOWS_DEVICE_NAME = /^(?:con|prn|aux|nul|clock\$|com[1-9]|lpt[1-9])(?:\..*)?$/i
const POSITION = /^(?:left|center|right)(?:\s+(?:top|center|bottom))?$/

function assertOptionalHex(value: unknown, name: string): string | undefined {
  if (value === undefined) return undefined
  if (typeof value !== 'string' || !HEX_COLOR.test(value)) fail(`${name} 必须是 #rrggbb 颜色`)
  return value.toLowerCase()
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
    colorPageTitle: assertOptionalHex(rawTokens.colorPageTitle, 'tokens.colorPageTitle'),
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
    if (key !== 'default' && !(APPEARANCE_MENU_ICON_KEYS as readonly string[]).includes(key)) {
      fail(`menuIcons 包含未知菜单键: ${key}`)
    }
    menuIcons[key as keyof AppearanceMenuIcons] = assertAssetPath(assetPath, true)
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

function pngDimensions(relativePath: string, data: Buffer): { width: number; height: number } {
  if (
    (path.posix.extname(relativePath).toLowerCase() === '.png' ? 'image/png' : '') !== 'image/png'
  ) {
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

function referencedPaths(manifest: AppearanceManifest): string[] {
  return [
    manifest.background?.path,
    manifest.mascot?.path,
    manifest.mascot?.animation?.path,
    manifest.mascot?.animation?.lookPath,
    manifest.mascot?.animation?.resultPath,
    manifest.mascot?.animation?.dragPath,
    manifest.preview,
    ...Object.values(manifest.menuIcons ?? {}),
    ...Object.values(manifest.cursors ?? {}).map(cursor => cursor.path),
  ].filter((value): value is string => Boolean(value))
}

function serializeAppearance({
  manifest,
  assets,
}: LoadedAssetPackage<AppearanceManifest>): InstalledAppearance {
  const getAsset = (assetPath: string | undefined): string | undefined =>
    assetPath ? assets[assetPath] : undefined
  const menuIconUrls: AppearanceMenuIcons = {}
  for (const [key, assetPath] of Object.entries(manifest.menuIcons ?? {})) {
    const url = getAsset(assetPath)
    if (url) menuIconUrls[key as keyof AppearanceMenuIcons] = url
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
    ...(manifest.mascot?.animation
      ? { mascotAnimationUrl: getAsset(manifest.mascot.animation.path) }
      : {}),
    ...(manifest.mascot?.animation?.lookPath
      ? { mascotLookUrl: getAsset(manifest.mascot.animation.lookPath) }
      : {}),
    ...(manifest.mascot?.animation?.resultPath
      ? { mascotResultUrl: getAsset(manifest.mascot.animation.resultPath) }
      : {}),
    ...(manifest.mascot?.animation?.dragPath
      ? { mascotDragUrl: getAsset(manifest.mascot.animation.dragPath) }
      : {}),
    ...(manifest.menuIcons ? { menuIconUrls } : {}),
    ...(manifest.cursors ? { cursorUrls } : {}),
  }
}

const store = new AssetPackageStore<AppearanceManifest>({
  directoryName: 'appearances',
  manifestName: 'theme.json',
  normalize: normalizeManifest,
  referencedPaths,
  validateAssets(manifest, read) {
    for (const [key, cursor] of Object.entries(manifest.cursors ?? {}))
      validateCursorData(key as AppearanceCursorKey, cursor, read(cursor.path))
    validateMascotAssets(manifest.mascot, read)
  },
})

export const getAppearanceRoot = (userDataPath: string): string => store.root(userDataPath)
export const validateAppearanceManifest = normalizeManifest
export const readAppearancePackage = (zipPath: string) => store.readArchive(zipPath)

/** 与安装共用校验，只读预览，不写用户目录。 */
export function inspectAppearancePackage(zipPath: string): {
  manifest: AppearanceManifest
  previewUrl?: string
} {
  const { manifest, files } = store.readArchive(zipPath)
  const preview = files.find(file => file.path.toLowerCase() === manifest.preview?.toLowerCase())
  return {
    manifest,
    ...(preview
      ? { previewUrl: `data:${preview.mime};base64,${preview.data.toString('base64')}` }
      : {}),
  }
}

export function importAppearancePackage(
  userDataPath: string,
  zipPath: string,
  replace = false
): AppearanceImportResult {
  try {
    const { item, existing, ...result } = store.install(
      userDataPath,
      store.readArchive(zipPath),
      replace
    )
    return {
      ...result,
      ...(item ? { appearance: serializeAppearance(item) } : {}),
      ...(existing ? { existing: serializeAppearance(existing) } : {}),
    }
  } catch (error) {
    return {
      success: false,
      code: error instanceof AppearanceError ? error.code : 'IMPORT_FAILED',
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

export const listAppearances = (userDataPath: string): InstalledAppearance[] =>
  store.list(userDataPath).map(serializeAppearance)
export function getAppearance(userDataPath: string, id: string): InstalledAppearance | null {
  const item = store.get(userDataPath, id)
  return item ? serializeAppearance(item) : null
}
export const isAppearanceGone = (userDataPath: string, id: string): boolean =>
  store.isGone(userDataPath, id)
export const removeAppearance = (userDataPath: string, id: string) => store.remove(userDataPath, id)
