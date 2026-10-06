import { describe, expect, it } from 'vitest'
import {
  createCodeMatcher,
  createDizzyDetector,
  createKonamiMatcher,
  createPityTally,
  createRapidClickDetector,
  isAprilFools,
  KEY_CODES,
  PITY_EGGS,
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

describe('pity tally', () => {
  it('MAA：第 100、200、300 下预告，最后 5 下倒数，第 325 下周哥出场后从头数', () => {
    const tally = createPityTally(PITY_EGGS.MAA!)
    const events = Array.from({ length: 325 }, () => tally.poke())

    expect(events[99]).toEqual({ kind: 'hint', key: 'maaHint1' })
    expect(events[199]).toEqual({ kind: 'hint', key: 'maaHint2' })
    expect(events[299]).toEqual({ kind: 'hint', key: 'maaHint3' })
    expect(events.slice(319, 324)).toEqual(
      [5, 4, 3, 2, 1].map(remaining => ({ kind: 'countdown', remaining }))
    )
    expect(events[324]).toEqual({ kind: 'reward', reward: 'zhouge' })
    expect(events.filter(event => event !== null)).toHaveLength(3 + 5 + 1)
    expect(tally.count).toBe(0)
  })

  it('原神按 90 抽保底：第 74 下提示概率上涨，第 90 下出金，不倒数', () => {
    const tally = createPityTally(PITY_EGGS.BetterGI!)
    const events = Array.from({ length: 90 }, () => tally.poke())

    expect(events[73]).toEqual({ kind: 'hint', key: 'softPity' })
    expect(events[89]).toEqual({ kind: 'reward', reward: 'gold' })
    expect(events.filter(event => event !== null)).toHaveLength(2)
  })

  it('各游戏的保底抽数', () => {
    const targets = Object.fromEntries(
      Object.entries(PITY_EGGS).map(([type, config]) => [type, config.target])
    )
    expect(targets).toMatchObject({
      BetterGI: 90,
      SRC: 90,
      HSR: 90,
      ZzzOd: 90,
      Okww: 80,
      MaaEnd: 80,
      M9A: 70,
      BAAH: 200,
    })
  })
})

describe('rapid click detector', () => {
  it('窗口内点满才算，触发后冷却', () => {
    const detector = createRapidClickDetector(5, 3000, 15000)
    const clicks = (times: number[]) => times.map(time => detector.click(time))

    // 点得太散：每一下都离第一下超过 3 秒
    expect(clicks([0, 1000, 2000, 3500, 4600]).some(Boolean)).toBe(false)
    expect(clicks([10000, 10200, 10400, 10600, 10800])).toEqual([false, false, false, false, true])
    expect(clicks([11000, 11100, 11200, 11300, 11400]).some(Boolean)).toBe(false)
    expect(clicks([30000, 30100, 30200, 30300, 30400]).at(-1)).toBe(true)
  })
})

describe('key codes', () => {
  it('连着敲出口令才触发，字母不分大小写', () => {
    const matcher = createCodeMatcher(KEY_CODES)
    const type = (keys: string) => [...keys].map(key => matcher.feed(key)).filter(Boolean)

    expect(type('1648')).toEqual(['648'])
    expect(type('19x99')).toEqual([])
    expect(type('1999')).toEqual(['1999'])
    expect(type('MaS')).toEqual(['mas'])
    expect(type('66666')).toEqual(['666'])
  })

  it('中间按了别的键就从头来', () => {
    const matcher = createCodeMatcher(KEY_CODES)
    expect(['5', '2', 'Enter', '0'].map(key => matcher.feed(key))).toEqual([null, null, null, null])
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

  it('时间往回跳（帧间隔为负）不算转', () => {
    const detector = createDizzyDetector()
    expect(detector.feed(0, -7000, 0)).toBe(false)
    expect(detector.feed(0, 16, 16)).toBe(false)
  })
})

describe('april fools', () => {
  it('只认 4 月 1 日', () => {
    expect(isAprilFools(new Date(2026, 3, 1, 12))).toBe(true)
    expect(isAprilFools(new Date(2026, 3, 2, 12))).toBe(false)
    expect(isAprilFools(new Date(2026, 0, 4, 12))).toBe(false)
  })
})
