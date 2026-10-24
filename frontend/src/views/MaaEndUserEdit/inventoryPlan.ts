export function readInventoryTargets(raw: string): Record<string, string> | null {
  try {
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    const entries = Object.entries(value)
    if (entries.some(([, quantity]) => typeof quantity !== 'string' || !/^\d+$/.test(quantity))) {
      return null
    }
    return Object.fromEntries(entries) as Record<string, string>
  } catch {
    return null
  }
}

export function isInventoryTargetActive(value: string | undefined): boolean {
  return !!value && /^\d+$/.test(value) && /[1-9]/.test(value)
}
