import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import { SATELLITE_COLORS, SATELLITE_CONFIG as C } from './config'

// ==================== 轨道与浮动 ====================

export interface Point3 {
  x: number
  y: number
  z: number
}

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

/** 第 index 颗卫星的初始相位：所有卫星沿轨道均分 */
export function getSatelliteBaseAngle(index: number, count: number): number {
  return (index / count) * Math.PI * 2
}

/**
 * 卫星在 time 时刻的位置：沿绕 x 轴倾斜的椭圆走，再叠一个上下浮动。
 * 倾斜方式和轨道线的 `rotation.x = orbitTilt` 一致，所以不浮动时卫星正好压在线上。
 */
export function getSatellitePosition(
  baseAngle: number,
  index: number,
  count: number,
  time: number
): Point3 {
  const angle = baseAngle + time * C.satelliteOrbitSpeed
  const x = Math.cos(angle) * C.orbitRadiusX
  const y = Math.sin(angle) * C.orbitRadiusY
  const floatOffset =
    Math.sin(time * C.satelliteFloatSpeed * 0.001 + index * ((Math.PI * 2) / count)) *
    C.satelliteFloatAmplitude

  return {
    x,
    y: y * Math.cos(C.orbitTilt) + floatOffset,
    z: y * Math.sin(C.orbitTilt),
  }
}

export function getCenterFloat(time: number): number {
  return Math.sin(time * C.centerFloatSpeed * 0.001) * C.centerFloatAmplitude
}

// ==================== 入场 ====================

/** 入场总时长：中心先出，卫星依次隔 cardAppearDelay 跟上 */
export function getAppearDuration(satelliteCount: number): number {
  return C.cardAppearDelay * (satelliteCount + 1) + C.cardAppearDuration
}

/**
 * 入场进度（已缓动），同时用作卡片的透明度和缩放。
 * order 为 0 是中心图标，第 i 颗卫星是 i + 1。
 */
export function getAppearProgress(elapsed: number, order: number): number {
  const progress = Math.min(1, (elapsed - C.cardAppearDelay * order) / C.cardAppearDuration)
  return easeOutCubic(Math.max(0, progress))
}

// ==================== 状态光晕 ====================

/** 光晕颜色：十六进制，或者 [色相, 饱和度, 亮度]（各 0~1） */
export type GlowColor = number | readonly [number, number, number]

export interface GlowAppearance {
  color: GlowColor
  opacity: number
  /** 光晕贴图的边长（世界单位） */
  size: number
}

const SATELLITE_GLOW_SIZE = C.satelliteCardSize * C.glowSizeMultiplier

/** 运行中呼吸、排队常亮；上次失败时让给失败光晕。返回 null 表示不亮 */
export function getActivityGlow(
  status: SatelliteModuleStatus,
  time: number
): GlowAppearance | null {
  if (status.lastFailed) {
    return null
  }

  if (status.running) {
    const breathe = 0.5 + 0.5 * Math.sin(time * 0.003)
    return {
      color: SATELLITE_COLORS.active,
      opacity: 0.4 + breathe * 0.55,
      size: SATELLITE_GLOW_SIZE * (1 + breathe * 0.12),
    }
  }

  if (status.queued) {
    return { color: SATELLITE_COLORS.active, opacity: 0.62, size: SATELLITE_GLOW_SIZE }
  }

  return null
}

/** 上次失败：平时红色微弱起伏，又在跑时换成琥珀色、按运行节奏呼吸。返回 null 表示不亮 */
export function getErrorGlow(status: SatelliteModuleStatus, time: number): GlowAppearance | null {
  if (!status.lastFailed) {
    return null
  }

  const size = SATELLITE_GLOW_SIZE * 1.08
  if (status.running) {
    const pulse = 0.5 + 0.5 * Math.sin(time * 0.003)
    return {
      color: SATELLITE_COLORS.failedRunning,
      opacity: 0.4 + pulse * 0.32,
      size: size * (1 + pulse * 0.12),
    }
  }

  const pulse = 0.5 + 0.5 * Math.sin(time * 0.0016)
  return { color: SATELLITE_COLORS.failed, opacity: 0.42, size: size * (1 + pulse * 0.04) }
}

/** 中心光晕：有新版本时彩虹闪烁，平时绿色常亮 */
export type CenterGlowMode = 'rainbow' | 'green'

export function getCenterGlow(mode: CenterGlowMode, time: number): GlowAppearance {
  if (mode === 'rainbow') {
    const flash = 0.5 + 0.5 * Math.sin(time * 0.006)
    return {
      color: [(time * 0.0008) % 1, 0.75, 0.6],
      opacity: 0.58 + flash * 0.34,
      size: C.centerCardSize * (C.glowSizeMultiplier * 0.82 + flash * 0.1),
    }
  }

  return {
    color: SATELLITE_COLORS.active,
    opacity: 0.85,
    size: C.centerCardSize * C.glowSizeMultiplier * 0.85,
  }
}
