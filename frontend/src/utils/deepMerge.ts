const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

export function deepMergeRecord(
  target: Record<string, unknown>,
  patch: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...target }
  for (const [key, value] of Object.entries(patch)) {
    const current = result[key]
    result[key] =
      isPlainObject(current) && isPlainObject(value)
        ? deepMergeRecord(current, value)
        : structuredClone(value)
  }
  return result
}
