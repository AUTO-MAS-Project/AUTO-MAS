export const INVENTORY_TARGET_MAX = '3000000000'

export function isInventoryTargetValid(value: string): boolean {
  return value.match(/^(0|[1-9][0-9]{0,8}|[12][0-9]{9}|3000000000)$/)?.[0] === value
}

export function readInventoryTargets(raw: string): Record<string, string> | null {
  try {
    const value: unknown = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    const entries = Object.entries(value)
    if (
      entries.some(
        ([, quantity]) => typeof quantity !== 'string' || !isInventoryTargetValid(quantity)
      )
    ) {
      return null
    }
    return Object.fromEntries(entries) as Record<string, string>
  } catch {
    return null
  }
}

export function isInventoryTargetActive(value: string | undefined): boolean {
  return !!value && isInventoryTargetValid(value) && value !== '0'
}
