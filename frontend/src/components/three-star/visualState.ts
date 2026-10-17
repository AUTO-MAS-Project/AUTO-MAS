/** 显示策略与时间预算；不持有或修改积分状态。 */
export const STAR_COLORS = [0xffdfa5, 0x7dcfff, 0xdc72dc] as const
export interface EmissionPoint {
  x: number
  y: number
}
export interface FluidSplat extends EmissionPoint {
  vx: number
  vy: number
  amount: number
  star: number
}

export const FLUID_DT = 1 / 30
export const MAX_PATH_SAMPLES = 8

/** 每颗星每秒固定染料总量，补样只分摊总量；相机/恢复断点由调用方丢弃。 */
export function pathSplats(
  from: EmissionPoint,
  to: EmissionPoint,
  dt: number,
  star: number
): FluidSplat[] {
  if (!Number.isFinite(dt) || dt <= 0 || ![from.x, from.y, to.x, to.y].every(Number.isFinite))
    return []
  const dx = to.x - from.x
  const dy = to.y - from.y
  if (Math.hypot(dx, dy) > 0.3) return []
  const time = Math.min(dt, FLUID_DT)
  const count = Math.min(MAX_PATH_SAMPLES, Math.max(1, Math.ceil(Math.hypot(dx, dy) / 0.012)))
  const vx = Math.max(-0.35, Math.min(0.35, dx / dt))
  const vy = Math.max(-0.35, Math.min(0.35, dy / dt))
  return Array.from({ length: count }, (_, i) => ({
    x: from.x + dx * ((i + 1) / count),
    y: from.y + dy * ((i + 1) / count),
    vx,
    vy,
    amount: time / count,
    star,
  })).filter(p => p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)
}

/** 隐藏/暂停后重新起钟，帧慢时只消耗有界墙钟片段，不积压。 */
export class DisplayClock {
  private last: number | null = null
  reset(): void {
    this.last = null
  }
  tick(now: number): number {
    const previous = this.last
    this.last = now
    return previous === null ? 0 : Math.max(0, Math.min(0.05, (now - previous) / 1000))
  }
}

/** WebGL 上下文存在不代表硬件加速；不明或软件路径一律静态降级。 */
export function allowsGpu(renderer: string | null, electronHardware: boolean | null): boolean {
  if (
    electronHardware === false ||
    !renderer ||
    /swiftshader|llvmpipe|softpipe|software|microsoft basic|lavapipe|warp\b/i.test(renderer)
  )
    return false
  return (
    electronHardware === true ||
    /nvidia|geforce|radeon|\bamd\b|\bintel\b|apple|adreno|mali|powervr/i.test(renderer)
  )
}
