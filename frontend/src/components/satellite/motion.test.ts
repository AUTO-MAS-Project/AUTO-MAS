import { describe, expect, it } from 'vitest'
import { ORBIT_RINGS, SATELLITE_COLORS, SATELLITE_CONFIG as C } from './config'
import {
  createExplosionFragmentMotion,
  getFragmentPose,
  SATELLITE_EXPLOSION_CONFIG,
} from './explosionMotion'
import {
  getActivityGlow,
  getAppearDuration,
  getAppearProgress,
  getCenterGlow,
  getErrorGlow,
  getKnockback,
  getRingBasis,
  getRingPoint,
  getRingSpeed,
  getSatelliteSlot,
  getTrailStatusColor,
} from './motion'

const idle = { queued: false, running: false, lastFailed: false }

describe('satellite orbit', () => {
  it('每条轨道的两条基向量正交、长度为 1，轨道上的点到星核距离等于半径', () => {
    for (const ring of ORBIT_RINGS) {
      const { u, v } = getRingBasis(ring)
      expect(u.x * v.x + u.y * v.y + u.z * v.z).toBeCloseTo(0)
      expect(Math.hypot(u.x, u.y, u.z)).toBeCloseTo(1)
      expect(Math.hypot(v.x, v.y, v.z)).toBeCloseTo(1)

      for (const angle of [0, 1, 2.5, 4]) {
        const p = getRingPoint({ u, v }, ring.radius, angle)
        expect(Math.hypot(p.x, p.y, p.z)).toBeCloseTo(ring.radius)
      }
    }
  })

  it('卫星轮流分到各条轨道，同一条轨道上均分一圈', () => {
    const slots = Array.from({ length: 6 }, (_, index) => getSatelliteSlot(index, 6))
    expect(slots.map(slot => slot.ring)).toEqual([0, 1, 2, 0, 1, 2])
    expect(slots[3].baseAngle - slots[0].baseAngle).toBeCloseTo(Math.PI)

    // 只有一颗卫星时只用主轨道
    expect(getSatelliteSlot(0, 1).ring).toBe(0)
  })

  it('内圈比主轨道转得快', () => {
    expect(getRingSpeed(ORBIT_RINGS[0])).toBeCloseTo(1)
    for (const ring of ORBIT_RINGS.slice(1)) {
      expect(getRingSpeed(ring)).toBeGreaterThan(1)
    }
  })

  it('冲击波先把卫星往外推，过后回到原轨道', () => {
    expect(getKnockback(-1)).toBe(0)
    expect(getKnockback(100)).toBeGreaterThan(0)
    expect(getKnockback(5000)).toBe(0)
  })

  it('入场按中心、第 1 颗、第 2 颗……依次出现，总时长内全部到位', () => {
    expect(getAppearProgress(0, 0)).toBe(0)
    expect(getAppearProgress(C.cardAppearDuration, 0)).toBe(1)
    expect(getAppearProgress(C.cardAppearDelay * 3, 3)).toBe(0)

    const count = 6
    expect(getAppearProgress(getAppearDuration(count), count)).toBe(1)
  })
})

describe('satellite glow', () => {
  it('空闲时不亮', () => {
    expect(getActivityGlow(idle, 0)).toBeNull()
    expect(getErrorGlow(idle, 0)).toBeNull()
    expect(getTrailStatusColor(idle)).toBeNull()
  })

  it('排队常亮，运行中呼吸', () => {
    const queued = getActivityGlow({ ...idle, queued: true }, 0)
    expect(queued).toMatchObject({ color: SATELLITE_COLORS.active, opacity: 0.62 })

    const opacities = [0, 500, 1000, 1500].map(
      time => getActivityGlow({ ...idle, running: true }, time)?.opacity
    )
    expect(new Set(opacities).size).toBeGreaterThan(1)
  })

  it('上次失败时只亮失败光晕，又在跑时换成琥珀色；彗尾颜色跟着变', () => {
    const failed = { ...idle, lastFailed: true }
    expect(getActivityGlow(failed, 0)).toBeNull()
    expect(getErrorGlow(failed, 0)?.color).toBe(SATELLITE_COLORS.failed)
    expect(getErrorGlow({ ...failed, running: true }, 0)?.color).toBe(
      SATELLITE_COLORS.failedRunning
    )
    expect(getTrailStatusColor(failed)).toBe(SATELLITE_COLORS.failed)
    expect(getTrailStatusColor({ ...idle, running: true })).toBe(SATELLITE_COLORS.active)
  })

  it('中心光晕平时绿色，有新版本时走彩虹', () => {
    expect(getCenterGlow('green', 0).color).toBe(SATELLITE_COLORS.active)
    expect(Array.isArray(getCenterGlow('rainbow', 0).color)).toBe(true)
  })
})

describe('satellite explosion fragments', () => {
  it('从原位飞出，最后拼回原位', () => {
    const motion = createExplosionFragmentMotion(3, 16, 17)
    const origin = { x: 5, y: -5, z: 4.4 }

    const start = getFragmentPose(motion, origin, 0)
    expect(start).toMatchObject({ ...origin, rotationX: motion.rotationX, opacity: 1 })

    const { fragmentDuration, reassembleDuration } = SATELLITE_EXPLOSION_CONFIG
    const end = getFragmentPose(motion, origin, fragmentDuration + reassembleDuration)
    expect(end.x).toBeCloseTo(origin.x)
    expect(end.y).toBeCloseTo(origin.y)
    expect(end.z).toBeCloseTo(origin.z)
    expect(end.rotationZ).toBeCloseTo(0)
    expect(end.opacity).toBe(1)
  })
})
