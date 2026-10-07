export type AppearanceMode = 'light' | 'dark'

export const APPEARANCE_MENU_ICON_KEYS = [
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

export type AppearanceMenuIconKey = (typeof APPEARANCE_MENU_ICON_KEYS)[number]

export const APPEARANCE_CURSOR_KEYS = ['default', 'pointer', 'text'] as const

export type AppearanceCursorKey = (typeof APPEARANCE_CURSOR_KEYS)[number]

export interface AppearanceTokens {
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

export interface AppearanceBackground {
  path: string
  opacity?: number
  surfaceOpacity?: number
  position?: string
  size?: 'cover' | 'contain' | 'auto'
}

export interface AppearanceMascot {
  path: string
  width?: number
  opacity?: number
  position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
}

export type AppearanceMenuIcons = Partial<Record<AppearanceMenuIconKey, string>>

export interface AppearanceCursor {
  path: string
  hotspotX?: number
  hotspotY?: number
}

export type AppearanceCursors = Partial<Record<AppearanceCursorKey, AppearanceCursor>>

export interface AppearanceManifest {
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

export interface InstalledAppearance extends AppearanceManifest {
  previewUrl?: string
  backgroundUrl?: string
  mascotUrl?: string
  menuIconUrls?: Partial<Record<AppearanceMenuIconKey, string>>
  cursorUrls?: Partial<Record<AppearanceCursorKey, string>>
}

export interface AppearanceImportResult {
  success: boolean
  appearance?: InstalledAppearance
  code?: 'INVALID_PACKAGE' | 'DUPLICATE_ID' | 'IMPORT_FAILED' | 'UNSUPPORTED'
  error?: string
  existing?: InstalledAppearance
}

export interface AppearanceCleanupResult {
  success: boolean
  cleared?: boolean
  appearanceId?: string | null
  error?: string
}

/** 分享站上的外观包在本机的安装状态；只认通过在线安装装上、且目录仍在的包。 */
export interface OnlineAppearanceInstalled {
  appearanceId: string
  versionNo: number
}

export interface OnlineAppearanceItem {
  fileKey: string
  displayName: string
  description: string
  ownerUsername: string
  publishedVersionNo: number | null
  publishedAt: string
  updatedAt: string
  installed: OnlineAppearanceInstalled | null
  /** 发布版本有没有封面；有才去取 getOnlineAppearanceCover。 */
  hasCover: boolean
}

export interface OnlineAppearanceVersion {
  versionNo: number
  fileSize: number
  sha256: string
  changeNote: string
  createdAt: string
  hasCover: boolean
}

export interface OnlineAppearanceQuery {
  page?: number
  pageSize?: number
  keyword?: string
}

export type OnlineAppearanceErrorCode =
  | 'NETWORK'
  | 'NOT_FOUND'
  | 'BAD_RESPONSE'
  | 'TOO_LARGE'
  | 'CHECKSUM_MISMATCH'
  | 'EXPIRED'
  | 'UNSUPPORTED'

export interface OnlineAppearanceListResult {
  success: boolean
  items?: OnlineAppearanceItem[]
  pagination?: { page: number; pageSize: number; total: number; hasNext: boolean }
  code?: OnlineAppearanceErrorCode
  error?: string
}

export interface OnlineAppearanceDetailResult {
  success: boolean
  item?: OnlineAppearanceItem
  /** 按版本号从新到旧排列。 */
  versions?: OnlineAppearanceVersion[]
  code?: OnlineAppearanceErrorCode
  error?: string
}

/** 已下载并校验过的包里读出的外观摘要，用于安装前预览。 */
export interface OnlineAppearancePreview {
  id: string
  name: string
  description?: string
  mode: AppearanceMode
  tokens: AppearanceTokens
  previewUrl?: string
}

export interface OnlineAppearancePrepareResult {
  success: boolean
  /** 主进程里这份已校验临时包的句柄，安装时只认它，不接受路径或 URL。 */
  token?: string
  fileKey?: string
  versionNo?: number
  fileSize?: number
  sha256?: string
  appearance?: OnlineAppearancePreview
  /** 本机已有同 ID 外观时给出名字，安装会走覆盖确认。 */
  existing?: { id: string; name: string } | null
  code?: OnlineAppearanceErrorCode | 'INVALID_PACKAGE'
  error?: string
}

export interface OnlineAppearanceInstallResult extends Omit<AppearanceImportResult, 'code'> {
  code?: AppearanceImportResult['code'] | OnlineAppearanceErrorCode
}

export interface OnlineAppearanceCoverResult {
  success: boolean
  /** 封面图片的 data URL（PNG / JPEG / WebP），主进程内存里按 fileKey + 版本号缓存。 */
  dataUrl?: string
  code?: OnlineAppearanceErrorCode
  error?: string
}

/** 上传前读取本地外观 ZIP 的结果；与导入同一套校验，不写任何目录。 */
export interface LocalAppearanceInspectResult {
  success: boolean
  appearance?: OnlineAppearancePreview
  fileSize?: number
  code?: 'INVALID_PACKAGE' | 'UNSUPPORTED'
  error?: string
}
