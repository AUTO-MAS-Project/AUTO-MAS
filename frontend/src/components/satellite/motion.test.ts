import { describe, expect, it } from 'vitest'
import { SATELLITE_COLORS, SATELLITE_CONFIG as C } from './config'
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
  getSatelliteBaseAngle,
  getSatellitePosition,
} from './motion'

const idle = { queued: false, running: false, lastFailed: false }

describe('satellite orbit', () => {
  it('卫星落在倾斜椭圆上，只在竖直方向浮动', () => {
    for (const time of [0, 1234, 98765]) {
      for (let index = 0; index < 5; index++) {
        const p = getSatellitePosition(getSatelliteBaseAngle(index, 5), index, 5, time)
        const planeY = p.z / Math.sin(C.orbitTilt)
        expect((p.x / C.orbitRadiusX) ** 2 + (planeY / C.orbitRadiusY) ** 2).toBeCloseTo(1)
        expect(Math.abs(p.y - planeY * Math.cos(C.orbitTilt))).toBeLessThanOrEqual(
          C.satelliteFloatAmplitude
        )
      }
    }
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
  })

  it('排队常亮，运行中呼吸', () => {
    const queued = getActivityGlow({ ...idle, queued: true }, 0)
    expect(queued).toMatchObject({ color: SATELLITE_COLORS.active, opacity: 0.62 })

    const opacities = [0, 500, 1000, 1500].map(
      time => getActivityGlow({ ...idle, running: true }, time)?.opacity
    )
    expect(new Set(opacities).size).toBeGreaterThan(1)
  })

  it('上次失败时只亮失败光晕，又在跑时换成琥珀色', () => {
    const failed = { ...idle, lastFailed: true }
    expect(getActivityGlow(failed, 0)).toBeNull()
    expect(getErrorGlow(failed, 0)?.color).toBe(SATELLITE_COLORS.failed)
    expect(getErrorGlow({ ...failed, running: true }, 0)?.color).toBe(
      SATELLITE_COLORS.failedRunning
    )
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
