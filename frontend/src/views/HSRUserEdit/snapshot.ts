export type HSRAbyssKey = 'ForgottenHall' | 'PureFiction' | 'Apocalyptic'

export const parseAbyssSnapshots = (
  raw: string | null | undefined,
): Partial<Record<HSRAbyssKey, Record<string, any>>> => {
  if (!raw || !raw.trim()) return {}

  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed
      : {}
  } catch {
    return {}
  }
}
