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

export interface ExplosionPhase {
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
