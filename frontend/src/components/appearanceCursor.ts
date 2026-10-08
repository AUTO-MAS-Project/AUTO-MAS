import type { AppearanceCursor, AppearanceCursorKey } from '@/types/appearance'

const CURSOR_FALLBACKS: Record<AppearanceCursorKey, string> = {
  default: 'auto',
  pointer: 'pointer',
  text: 'text',
}

const SAFE_PNG_DATA_URL = /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/

export function createAppearanceCursorValue(
  key: AppearanceCursorKey,
  cursorUrls: Partial<Record<AppearanceCursorKey, string>> | undefined,
  cursors: Partial<Record<AppearanceCursorKey, AppearanceCursor>> | undefined
): string {
  const fallback = CURSOR_FALLBACKS[key]
  const url = cursorUrls?.[key]
  if (!url || !SAFE_PNG_DATA_URL.test(url)) return fallback

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
