/**
 * 实例设置的档位：雷电 14 / MuMu 6 共用一套，魔改 AVD 另有自己的限制。
 *
 * 弹窗只给档位下拉，不给自由数字框。实例现有的值不在档位里时，打开弹窗就选中最近的一档
 * （等距取大的那档），保存时把对齐后的值写进去；读不到或从没设过的项不对齐、不写。
 * 和界面拆开，是为了能在 node 里直接测；组件只管把结果画出来。
 */
import { MEMORY_CHOICES_MB } from './avdLogic'

/** ``standard`` 雷电 14 / MuMu 6；``avd`` 魔改 AVD */
export type TierKind = 'standard' | 'avd'

export type ResolutionTier = '720p' | '1080p'

/** 两档都是横屏；DPI 按 240×高/720 等比推出，两档的 dp 布局完全一致（都是 sw480dp） */
export const RESOLUTIONS: Record<ResolutionTier, { width: number; height: number; dpi: number }> = {
  '720p': { width: 1280, height: 720, dpi: 240 },
  '1080p': { width: 1920, height: 1080, dpi: 360 },
}

export const RESOLUTION_TIERS: readonly ResolutionTier[] = ['720p', '1080p']

/** 短边不超过它的归 720p，否则归 1080p（竖屏也按短边归档） */
const SHORT_SIDE_SPLIT = 900

export const STANDARD_TIERS = {
  cpu: [2, 4, 6, 8],
  memoryMb: [2048, 3072, 4096, 6144, 8192],
  fps: [30, 60],
} as const

/** 魔改 AVD：核数、内存与后端 ``CPU_CHOICES`` / ``MEMORY_CHOICES_MB`` 一致 */
export const AVD_TIERS = {
  cpu: [2, 4, 6],
  memoryMb: MEMORY_CHOICES_MB,
} as const

/** 魔改 AVD 显示固定 720p、帧率固定 60，弹窗里只显示、不能改 */
export const AVD_FIXED = { resolution: '720p' as ResolutionTier, fps: 60 }

export const tierKindOf = (realType: string | undefined): TierKind =>
  realType === 'avd' ? 'avd' : 'standard'

/**
 * 批量设置按整条配置下发。配置里全是魔改 AVD 时只给它能改的两项，否则按雷电 / MuMu 的档位给；
 * 混着放的配置里，魔改 AVD 改不了的项由后端逐台拒绝，列在失败清单里。
 */
export const batchKindOf = (pathTypes: string[]): TierKind =>
  pathTypes.length > 0 && pathTypes.every(type => type === 'avd') ? 'avd' : 'standard'

export const tiersOf = (kind: TierKind) => (kind === 'avd' ? AVD_TIERS : STANDARD_TIERS)

/** 最近的一档；等距取大的那档。没有值就不对齐。 */
export const nearestTier = (value: number | null, tiers: readonly number[]): number | null => {
  if (value === null || !tiers.length) return null
  let best = tiers[0]
  for (const tier of tiers) {
    const gap = Math.abs(tier - value)
    const bestGap = Math.abs(best - value)
    if (gap < bestGap || (gap === bestGap && tier > best)) best = tier
  }
  return best
}

/** 按短边归档，宽高缺一个就不归。 */
export const resolutionTierOf = (
  width: number | null,
  height: number | null
): ResolutionTier | null => {
  if (width === null || height === null) return null
  return Math.min(width, height) <= SHORT_SIDE_SPLIT ? '720p' : '1080p'
}

/** 实例现在的六项值（``null`` = 读不到或从没设过） */
export interface ActualSettings {
  width: number | null
  height: number | null
  dpi: number | null
  cpu: number | null
  memoryMb: number | null
  fps: number | null
}

/** 弹窗里的四个下拉（``null`` = 空着） */
export interface TierForm {
  resolution: ResolutionTier | null
  cpu: number | null
  memoryMb: number | null
  fps: number | null
}

/** 打开时发生了对齐的项，记下实际值给字段下的小字用；没对齐的项为 ``null`` */
export interface SnappedActual {
  resolution: { width: number; height: number } | null
  dpi: number | null
  cpu: number | null
  memoryMb: number | null
  fps: number | null
}

export const emptyTierForm = (): TierForm => ({
  resolution: null,
  cpu: null,
  memoryMb: null,
  fps: null,
})

const snappedIf = (actual: number | null, aligned: number | null) =>
  actual !== null && aligned !== null && actual !== aligned ? actual : null

/** 打开弹窗时：把实际值对齐到档位，并记下哪些项被对齐了。 */
export const alignSettings = (
  actual: ActualSettings,
  kind: TierKind
): { form: TierForm; snapped: SnappedActual } => {
  const tiers = tiersOf(kind)
  const cpu = nearestTier(actual.cpu, tiers.cpu)
  const memoryMb = nearestTier(actual.memoryMb, tiers.memoryMb)
  if (kind === 'avd') {
    return {
      form: { resolution: AVD_FIXED.resolution, cpu, memoryMb, fps: AVD_FIXED.fps },
      snapped: {
        resolution: null,
        dpi: null,
        cpu: snappedIf(actual.cpu, cpu),
        memoryMb: snappedIf(actual.memoryMb, memoryMb),
        fps: null,
      },
    }
  }
  const resolution = resolutionTierOf(actual.width, actual.height)
  const target = resolution ? RESOLUTIONS[resolution] : null
  const fps = nearestTier(actual.fps, STANDARD_TIERS.fps)
  return {
    form: { resolution, cpu, memoryMb, fps },
    snapped: {
      resolution:
        target &&
        actual.width !== null &&
        actual.height !== null &&
        (actual.width !== target.width || actual.height !== target.height)
          ? { width: actual.width, height: actual.height }
          : null,
      dpi: target ? snappedIf(actual.dpi, target.dpi) : null,
      cpu: snappedIf(actual.cpu, cpu),
      memoryMb: snappedIf(actual.memoryMb, memoryMb),
      fps: snappedIf(actual.fps, fps),
    },
  }
}

/**
 * 单台保存：只提交与实际值不同的字段。
 *
 * 分辨率一变就宽高一起写；DPI 和所选分辨率推出的值不同就写（实例从没设过 DPI、分辨率又没变时不写）。
 * 魔改 AVD 只写核数与内存。
 */
export const settingsChanges = (
  actual: ActualSettings,
  form: TierForm,
  kind: TierKind
): Record<string, number> => {
  const changes: Record<string, number> = {}
  if (kind === 'standard' && form.resolution) {
    const target = RESOLUTIONS[form.resolution]
    const resized = actual.width !== target.width || actual.height !== target.height
    if (resized) {
      changes.width = target.width
      changes.height = target.height
    }
    if (actual.dpi !== target.dpi && (resized || actual.dpi !== null)) changes.dpi = target.dpi
  }
  const fields =
    kind === 'avd' ? (['cpu', 'memoryMb'] as const) : (['cpu', 'memoryMb', 'fps'] as const)
  for (const name of fields) {
    const value = form[name]
    if (value !== null && value !== actual[name]) changes[name] = value
  }
  return changes
}

/** 批量：只下发选了的项；分辨率选了就连 DPI 一起下发。魔改 AVD 只下发核数与内存。 */
export const batchChanges = (form: TierForm, kind: TierKind): Record<string, number> => {
  const changes: Record<string, number> = {}
  if (kind === 'standard' && form.resolution) {
    const target = RESOLUTIONS[form.resolution]
    changes.width = target.width
    changes.height = target.height
    changes.dpi = target.dpi
  }
  if (form.cpu !== null) changes.cpu = form.cpu
  if (form.memoryMb !== null) changes.memoryMb = form.memoryMb
  if (kind === 'standard' && form.fps !== null) changes.fps = form.fps
  return changes
}

/** 内存档位与实际值的显示：整 GB 写 GB，不是整 GB 的照写 MB。 */
export const memoryText = (mb: number) => (mb % 1024 === 0 ? `${mb / 1024} GB` : `${mb} MB`)

export const resolutionText = (tier: ResolutionTier) => {
  const { width, height } = RESOLUTIONS[tier]
  return `${tier} (${width}×${height})`
}
