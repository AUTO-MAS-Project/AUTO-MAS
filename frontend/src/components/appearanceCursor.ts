import { INLINE_STYLE_VALUE_MAX } from '@/composables/appearanceBackground'
import type { AppearanceCursor, AppearanceCursorKey } from '@/types/appearance'

const CURSOR_FALLBACKS: Record<AppearanceCursorKey, string> = {
  default: 'auto',
  pointer: 'pointer',
  text: 'text',
}

const SAFE_PNG_DATA_URL = /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/
// 光标值也写进内联样式，超过 Chromium 的单条声明上限会被静默丢弃、留下上一个包的光标；
// 给热点和回退值留出余量，超长就直接用浏览器光标。
const CURSOR_URL_MAX = INLINE_STYLE_VALUE_MAX - 64

export function createAppearanceCursorValue(
  key: AppearanceCursorKey,
  cursorUrls: Partial<Record<AppearanceCursorKey, string>> | undefined,
  cursors: Partial<Record<AppearanceCursorKey, AppearanceCursor>> | undefined
): string {
  const fallback = CURSOR_FALLBACKS[key]
  const url = cursorUrls?.[key]
  if (!url || url.length > CURSOR_URL_MAX || !SAFE_PNG_DATA_URL.test(url)) return fallback

  const cursor = cursors?.[key]
  const hotspotX = cursor?.hotspotX ?? 0
  const hotspotY = cursor?.hotspotY ?? 0
  if (
    !Number.isSafeInteger(hotspotX) ||
    !Number.isSafeInteger(hotspotY) ||
    hotspotX < 0 ||
    hotspotY < 0 ||
    hotspotX > 63 ||
    hotspotY > 63
  ) {
    return fallback
  }
  return `url("${url}") ${hotspotX} ${hotspotY}, ${fallback}`
}

export const CURSOR_SIZE_MIN = 8
export const CURSOR_SIZE_MAX = 64

export function normalizeCursorSize(value: unknown): number | null {
  return typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= CURSOR_SIZE_MIN &&
    value <= CURSOR_SIZE_MAX
    ? value
    : null
}

export function scaleCursorGeometry(
  width: number,
  height: number,
  hotspotX: number,
  hotspotY: number,
  size: number
) {
  const scale = size / Math.max(width, height)
  const scaledWidth = Math.max(1, Math.round(width * scale))
  const scaledHeight = Math.max(1, Math.round(height * scale))
  return {
    width: scaledWidth,
    height: scaledHeight,
    hotspotX: Math.min(scaledWidth - 1, Math.round((hotspotX * scaledWidth) / width)),
    hotspotY: Math.min(scaledHeight - 1, Math.round((hotspotY * scaledHeight) / height)),
  }
}

type CursorUrls = Parameters<typeof createAppearanceCursorValue>[1]
type Cursors = Parameters<typeof createAppearanceCursorValue>[2]

export function createAppearanceCursorApplier() {
  const cache = new Map<
    AppearanceCursorKey,
    {
      original: string
      image: Promise<HTMLImageElement>
      sizes: Map<number, string>
    }
  >()
  let frame: number | undefined
  let revision = 0

  return (style: CSSStyleDeclaration, urls: CursorUrls, cursors: Cursors, size: number | null) => {
    const current = ++revision
    if (frame !== undefined) cancelAnimationFrame(frame)
    const keys = ['default', 'pointer', 'text'] as const

    for (const key of keys) {
      const original = createAppearanceCursorValue(key, urls, cursors)
      const cached = cache.get(key)
      if (cached?.original !== original) cache.delete(key)
      if (size === null || !cache.has(key)) {
        style.setProperty(`--app-appearance-cursor-${key}`, original)
      }
    }
    if (size === null || !urls) return

    frame = requestAnimationFrame(() => {
      frame = undefined
      for (const key of keys) {
        const original = createAppearanceCursorValue(key, urls, cursors)
        const url = urls[key]
        if (!url || original === CURSOR_FALLBACKS[key]) continue

        let entry = cache.get(key)
        if (!entry) {
          const image = new Image()
          image.src = url
          entry = { original, image: image.decode().then(() => image), sizes: new Map() }
          cache.set(key, entry)
        }
        const { image, sizes } = entry
        void image
          .then(decoded => {
            if (current !== revision) return
            let value = sizes.get(size)
            if (!value) {
              const cursor = cursors?.[key]
              const geometry = scaleCursorGeometry(
                decoded.naturalWidth,
                decoded.naturalHeight,
                cursor?.hotspotX ?? 0,
                cursor?.hotspotY ?? 0,
                size
              )
              const canvas = document.createElement('canvas')
              canvas.width = geometry.width
              canvas.height = geometry.height
              const context = canvas.getContext('2d')
              if (!context) return
              context.drawImage(decoded, 0, 0, canvas.width, canvas.height)
              value = `url("${canvas.toDataURL('image/png')}") ${geometry.hotspotX} ${geometry.hotspotY}, ${CURSOR_FALLBACKS[key]}`
              sizes.set(size, value)
            }
            style.setProperty(`--app-appearance-cursor-${key}`, value)
          })
          .catch(() => {
            if (current === revision) style.setProperty(`--app-appearance-cursor-${key}`, original)
          })
      }
    })
  }
}
