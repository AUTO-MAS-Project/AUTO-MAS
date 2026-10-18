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
