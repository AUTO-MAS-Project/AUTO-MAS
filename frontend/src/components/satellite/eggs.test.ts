import { describe, expect, it } from 'vitest'
import {
  createDizzyDetector,
  createKonamiMatcher,
  createMaaPokeTally,
  isAprilFools,
  MAA_POKE_TARGET,
} from './eggs'

const KONAMI = [
  'ArrowUp',
  'ArrowUp',
  'ArrowDown',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'ArrowLeft',
  'ArrowRight',
  'b',
  'a',
]

describe('konami code', () => {
  it('整串按完的那一下触发，大小写不论', () => {
    const matcher = createKonamiMatcher()
    const results = [...KONAMI.slice(0, -2), 'B', 'A'].map(key => matcher.feed(key))
    expect(results.slice(0, -1).every(result => !result)).toBe(true)
    expect(results.at(-1)).toBe(true)
  })

  it('按错就从头来，多按一个 ↑ 不影响', () => {
    const matcher = createKonamiMatcher()
    expect(['ArrowUp', 'ArrowUp', 'x', ...KONAMI.slice(0, -1)].some(key => matcher.feed(key))).toBe(
      false
    )
    expect(matcher.feed('a')).toBe(true)

    const extraUp = createKonamiMatcher()
    expect(['ArrowUp', ...KONAMI].map(key => extraUp.feed(key)).at(-1)).toBe(true)
  })
})

describe('MAA poke tally', () => {
  it('第 100、200、300 下预告，最后 5 下倒数，第 325 下周哥出场后从头数', () => {
    const tally = createMaaPokeTally()
    const events = Array.from({ length: MAA_POKE_TARGET }, () => tally.poke())

    expect(events[99]).toEqual({ kind: 'hint', hint: 'maaHint1' })
    expect(events[199]).toEqual({ kind: 'hint', hint: 'maaHint2' })
    expect(events[299]).toEqual({ kind: 'hint', hint: 'maaHint3' })
    expect(events.slice(319, 324)).toEqual(
      [5, 4, 3, 2, 1].map(remaining => ({ kind: 'countdown', remaining }))
    )
    expect(events[324]).toEqual({ kind: 'reveal' })
    expect(events.filter(event => event !== null)).toHaveLength(3 + 5 + 1)
    expect(tally.count).toBe(0)
  })
})

describe('dizzy detector', () => {
  it('猛转够久才晕，晕过之后冷却一阵', () => {
    const detector = createDizzyDetector()
    const spin = (speed: number, frames: number, start: number) =>
      Array.from({ length: frames }, (_, i) => detector.feed(speed, 16, start + i * 16))

    // 甩一下：快转不到 1.2 秒就慢下来了，不晕
    expect(spin(14, 50, 0).some(Boolean)).toBe(false)
    expect(spin(3, 200, 1000).some(Boolean)).toBe(false)
    const fast = spin(14, 100, 5000)
    expect(fast.filter(Boolean)).toHaveLength(1)
    expect(spin(14, 100, 7000).some(Boolean)).toBe(false)
  })
})

describe('april fools', () => {
  it('只认 4 月 1 日', () => {
    expect(isAprilFools(new Date(2026, 3, 1, 12))).toBe(true)
    expect(isAprilFools(new Date(2026, 3, 2, 12))).toBe(false)
    expect(isAprilFools(new Date(2026, 0, 4, 12))).toBe(false)
  })
})
