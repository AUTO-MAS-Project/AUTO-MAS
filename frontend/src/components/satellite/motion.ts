import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import { ORBIT_RINGS, SATELLITE_COLORS, SATELLITE_CONFIG as C, type OrbitRing } from './config'

// ==================== 轨道 ====================

export interface Point3 {
  x: number
  y: number
  z: number
}

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

/** 冲出去一点再回来，卫星从星核里甩出来时用 */
export function easeOutBack(t: number): number {
  const c1 = 1.70158
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

/** 轨道平面的两条正交基向量：u 指向 θ=0，v 指向 θ=π/2 */
export interface RingBasis {
  u: Point3
  v: Point3
}

/** 水平圆环先绕 x 轴倾斜 tiltX、再绕 z 轴转 tiltZ 后的基向量 */
export function getRingBasis(ring: OrbitRing): RingBasis {
  const cosX = Math.cos(ring.tiltX)
  const sinX = Math.sin(ring.tiltX)
  const cosZ = Math.cos(ring.tiltZ)
  const sinZ = Math.sin(ring.tiltZ)
  // u0 = (1, 0, 0) 绕 x 轴不变；v0 = (0, 0, 1) 绕 x 轴后变成 (0, -sinX, cosX)
  const rotateZ = (p: Point3): Point3 => ({
    x: p.x * cosZ - p.y * sinZ,
    y: p.x * sinZ + p.y * cosZ,
    z: p.z,
  })
  return {
    u: rotateZ({ x: 1, y: 0, z: 0 }),
    v: rotateZ({ x: 0, y: -sinX, z: cosX }),
  }
}

export function getRingPoint(basis: RingBasis, radius: number, angle: number): Point3 {
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  return {
    x: radius * (cos * basis.u.x + sin * basis.v.x),
    y: radius * (cos * basis.u.y + sin * basis.v.y),
    z: radius * (cos * basis.u.z + sin * basis.v.z),
  }
}

/** 内圈转得快：角速度和半径的 -1.5 次方成正比，以主轨道为 1 */
export function getRingSpeed(ring: OrbitRing): number {
  return Math.pow(ORBIT_RINGS[0].radius / ring.radius, 1.5)
}

export interface SatelliteSlot {
  ring: number
  baseAngle: number
}

/** 卫星按序号轮流分到各条轨道，同一条轨道上的均分一圈，各条轨道再错开一点相位 */
export function getSatelliteSlot(index: number, count: number): SatelliteSlot {
  const ringCount = Math.min(ORBIT_RINGS.length, count)
  const ring = index % ringCount
  const onRing = Math.floor((count - 1 - ring) / ringCount) + 1
  const order = Math.floor(index / ringCount)
  return {
    ring,
    baseAngle: (order / onRing) * Math.PI * 2 + ring * 1.1,
  }
}

export function getSatelliteFloat(index: number, count: number, time: number): number {
  return (
    Math.sin(time * C.satelliteFloatSpeed * 0.001 + index * ((Math.PI * 2) / Math.max(1, count))) *
    C.satelliteFloatAmplitude
  )
}

export function getCenterFloat(time: number): number {
  return Math.sin(time * C.centerFloatSpeed * 0.001) * C.centerFloatAmplitude
}

/** 冲击波把卫星往外推：先冲出去，再阻尼振荡回原轨道；返回半径的放大比例 */
export function getKnockback(elapsed: number): number {
  if (elapsed < 0 || elapsed > 2200) {
    return 0
  }
  return 0.42 * Math.exp(-elapsed / 420) * Math.sin(elapsed / 110)
}

// ==================== 入场 ====================

/** 入场总时长：中心先出，卫星依次隔 cardAppearDelay 跟上 */
export function getAppearDuration(satelliteCount: number): number {
  return C.cardAppearDelay * (satelliteCount + 1) + C.cardAppearDuration
}

/**
 * 入场进度（未缓动，0~1）。order 为 0 是中心图标，第 i 颗卫星是 i + 1。
 */
export function getAppearProgress(elapsed: number, order: number): number {
  const progress = (elapsed - C.cardAppearDelay * order) / C.cardAppearDuration
  return Math.min(1, Math.max(0, progress))
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

const SATELLITE_GLOW_SIZE = C.satelliteSize * C.glowSizeMultiplier

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

/** 彗尾颜色跟着状态走：失败红、失败重跑琥珀、运行或排队绿，空闲时为 null（用主题色） */
export function getTrailStatusColor(status: SatelliteModuleStatus): number | null {
  if (status.lastFailed) {
    return status.running ? SATELLITE_COLORS.failedRunning : SATELLITE_COLORS.failed
  }
  if (status.running || status.queued) {
    return SATELLITE_COLORS.active
  }
  return null
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
    opacity: 0.7,
    size: C.centerCardSize * C.glowSizeMultiplier * 0.85,
  }
}
