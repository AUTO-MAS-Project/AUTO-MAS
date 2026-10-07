import type { InstalledAppearance } from '@/types/appearance'

export function getAppearanceSurfaceOpacity(
  appearance: InstalledAppearance | null
): number | undefined {
  if (!appearance?.backgroundUrl) return undefined
  return Math.min(1, Math.max(0, appearance.background?.surfaceOpacity ?? 0.72))
}

export function createAppearanceSurfaceColor(color: string, opacity: number | undefined): string {
  if (opacity === undefined) return color
  // 使用最终 Ant token 的颜色，仅为主界面表面加入透明度；弹出层继续使用原 token。
  return `color-mix(in srgb, ${color} ${opacity * 100}%, transparent)`
}
