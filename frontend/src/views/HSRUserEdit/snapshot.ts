export type HSRAbyssKey = 'ForgottenHall' | 'PureFiction' | 'Apocalyptic'

export const parseAbyssSnapshots = (
  raw: string | Record<string, unknown> | null | undefined
): Partial<Record<HSRAbyssKey, Record<string, any>>> => {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Partial<Record<HSRAbyssKey, Record<string, any>>>
  }
  if (!raw || typeof raw !== 'string' || !raw.trim()) return {}

  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}
