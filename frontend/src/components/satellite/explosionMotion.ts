import { easeOutCubic, type Point3 } from './motion'

export const SATELLITE_EXPLOSION_CONFIG = {
  fragmentColumns: 4,
  fragmentRows: 4,
  fragmentDuration: 900,
  reassembleDuration: 300,
  flashDuration: 180,
  ringDuration: 520,
  fragmentGravity: 82,
  fragmentSpread: 58,
} as const

export interface ExplosionFragmentMotion {
  velocityX: number
  velocityY: number
  velocityZ: number
  rotationX: number
  rotationY: number
  rotationZ: number
  rotationSpeedX: number
  rotationSpeedY: number
  rotationSpeedZ: number
}

interface ExplosionPhase {
  isReassembling: boolean
  progress: number
  complete: boolean
}

function createSeededRandom(seed: number): () => number {
  let state = seed | 0 || 1
  return () => {
    state = (state * 1664525 + 1013904223) | 0
    return (state >>> 0) / 0x100000000
  }
}

export function createExplosionFragmentMotion(
  index: number,
  total: number,
  seed: number
): ExplosionFragmentMotion {
  const random = createSeededRandom(seed + index * 7919)
  const angle = (index / total) * Math.PI * 2 + (random() - 0.5) * 0.45
  const spread = SATELLITE_EXPLOSION_CONFIG.fragmentSpread * (0.75 + random() * 0.5)

  return {
    velocityX: Math.cos(angle) * spread,
    velocityY: Math.sin(angle) * spread * 0.72 + 24 + random() * 18,
    velocityZ: (random() - 0.5) * spread * 1.2,
    rotationX: (random() - 0.5) * 0.8,
    rotationY: (random() - 0.5) * 0.8,
    rotationZ: (random() - 0.5) * 0.8,
    rotationSpeedX: (random() - 0.5) * 8,
    rotationSpeedY: (random() - 0.5) * 8,
    rotationSpeedZ: (random() - 0.5) * 10,
  }
}

export function getExplosionPhase(elapsedMs: number): ExplosionPhase {
  const { fragmentDuration, reassembleDuration } = SATELLITE_EXPLOSION_CONFIG

  if (elapsedMs < fragmentDuration) {
    return {
      isReassembling: false,
      progress: Math.max(0, elapsedMs / fragmentDuration),
      complete: false,
    }
  }

  const reassembleProgress = Math.min(
    1,
    Math.max(0, (elapsedMs - fragmentDuration) / reassembleDuration)
  )
  return {
    isReassembling: true,
    progress: reassembleProgress,
    complete: reassembleProgress >= 1,
  }
}

export function getExplosionEffectProgress(elapsedMs: number, duration: number): number {
  return Math.min(1, Math.max(0, elapsedMs / duration))
}

export interface FragmentPose {
  x: number
  y: number
  z: number
  rotationX: number
  rotationY: number
  rotationZ: number
  opacity: number
}

/** 碎片飞出 seconds 秒时的位姿：匀速飞散叠加重力下坠，边飞边转 */
function getFlightPose(motion: ExplosionFragmentMotion, origin: Point3, seconds: number) {
  return {
    x: origin.x + motion.velocityX * seconds,
    y:
      origin.y +
      motion.velocityY * seconds -
      0.5 * SATELLITE_EXPLOSION_CONFIG.fragmentGravity * seconds ** 2,
    z: origin.z + motion.velocityZ * seconds,
    rotationX: motion.rotationX + motion.rotationSpeedX * seconds,
    rotationY: motion.rotationY + motion.rotationSpeedY * seconds,
    rotationZ: motion.rotationZ + motion.rotationSpeedZ * seconds,
  }
}

function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * t
}

/** 碎片在爆开后 elapsedMs 时的位姿：先飞散淡出，再从飞散终点缓动拼回原位 */
export function getFragmentPose(
  motion: ExplosionFragmentMotion,
  origin: Point3,
  elapsedMs: number
): FragmentPose {
  const { fragmentDuration } = SATELLITE_EXPLOSION_CONFIG
  const phase = getExplosionPhase(elapsedMs)

  if (!phase.isReassembling) {
    return {
      ...getFlightPose(motion, origin, Math.min(elapsedMs, fragmentDuration) / 1000),
      opacity: 1 - getExplosionEffectProgress(elapsedMs, fragmentDuration),
    }
  }

  const exploded = getFlightPose(motion, origin, fragmentDuration / 1000)
  const progress = easeOutCubic(phase.progress)
  return {
    x: lerp(exploded.x, origin.x, progress),
    y: lerp(exploded.y, origin.y, progress),
    z: lerp(exploded.z, origin.z, progress),
    rotationX: lerp(exploded.rotationX, 0, progress),
    rotationY: lerp(exploded.rotationY, 0, progress),
    rotationZ: lerp(exploded.rotationZ, 0, progress),
    opacity: progress,
  }
}
