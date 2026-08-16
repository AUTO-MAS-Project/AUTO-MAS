export type CursorEffect = 'none' | 'sleek-line' | 'fluid'

export const DEFAULT_CURSOR_EFFECT: CursorEffect = 'none'

export const normalizeCursorEffect = (value: unknown): CursorEffect => {
  if (value === 'sleek-line' || value === 'fluid') {
    return value
  }

  return DEFAULT_CURSOR_EFFECT
}
