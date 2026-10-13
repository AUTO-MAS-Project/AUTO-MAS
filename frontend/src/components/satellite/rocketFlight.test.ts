import { describe, expect, it } from 'vitest'
import { createRocketPath, getRocketPose, RACE_TIMELINE } from './rocketFlight'

const box = { left: 50, right: 650, top: 60, bottom: 430 }
const path = createRocketPath(2, 6, 0.6, () => 0.37)

describe('rocket race flight', () => {
  it('倒数期间藏在底下', () => {
    expect(getRocketPose(path, box, 500).visible).toBe(false)
  })

  it('乱飞期间不出飞行区', () => {
    for (
      let elapsed = RACE_TIMELINE.liftoff + RACE_TIMELINE.entry;
      elapsed < RACE_TIMELINE.exit;
      elapsed += 37
    ) {
      const pose = getRocketPose(path, box, elapsed)
      expect(pose.visible).toBe(true)
      expect(pose.x).toBeGreaterThanOrEqual(box.left - 1)
      expect(pose.x).toBeLessThanOrEqual(box.right + 1)
      expect(pose.y).toBeGreaterThanOrEqual(box.top - 1)
      expect(pose.y).toBeLessThanOrEqual(box.bottom + 1)
    }
  })

  it('散场时顺着最后的方向冲出去，机头朝着前进方向', () => {
    const atExit = getRocketPose(path, box, RACE_TIMELINE.exit)
    const later = getRocketPose(path, box, RACE_TIMELINE.exit + RACE_TIMELINE.exitDuration * 0.8)
    const radians = (atExit.angle * Math.PI) / 180
    // 机头朝向：0° 朝上，所以前进方向是 (sin, -cos)
    const forward =
      (later.x - atExit.x) * Math.sin(radians) - (later.y - atExit.y) * Math.cos(radians)
    expect(forward).toBeGreaterThan(500)
    expect(getRocketPose(path, box, RACE_TIMELINE.exit + RACE_TIMELINE.exitDuration).visible).toBe(
      false
    )
  })

  it('commit 越多飞得越快', () => {
    expect(createRocketPath(0, 6, 1).speed).toBeGreaterThan(createRocketPath(5, 6, 0.2).speed)
  })
})
