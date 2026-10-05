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
