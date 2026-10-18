export const CUSTOM_BACKGROUND_MAX_BYTES = 8 * 1024 * 1024

const MIME_BY_EXTENSION: Record<string, string> = {
  bmp: 'image/bmp',
  gif: 'image/gif',
  jpeg: 'image/jpeg',
  jpg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
}

export function getCustomBackgroundExtension(path: string): string {
  const fileName = path.split(/[\\/]/).pop() ?? ''
  const dotIndex = fileName.lastIndexOf('.')
  return dotIndex < 0 ? '' : fileName.slice(dotIndex + 1).toLowerCase()
}

export function hasCustomBackgroundExtension(path: string): boolean {
  return getCustomBackgroundExtension(path) in MIME_BY_EXTENSION
}

export function getCustomBackgroundMime(path: string): string | null {
  return MIME_BY_EXTENSION[getCustomBackgroundExtension(path)] ?? null
}

export function createCustomBackgroundDataUrl(base64: string, path: string): string | null {
  const mime = getCustomBackgroundMime(path)
  return base64 && mime ? `data:${mime};base64,${base64}` : null
}

export function clampCustomSurfaceOpacity(value: number): number {
  const opacity = Number.isFinite(value) ? value : 1
  return Math.min(1, Math.max(0.1, opacity))
}
