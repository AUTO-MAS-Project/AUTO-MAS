import { describe, expect, it } from 'vitest'
import { createCenterPokeCounter } from './centerPoke'

/** 每隔 100ms 点一次，返回每次点击的结果 */
function pokeTimes(counter: ReturnType<typeof createCenterPokeCounter>, times: number) {
  return Array.from({ length: times }, (_, index) => counter.poke(1000 + index * 100, false))
}

describe('center poke easter egg', () => {
  it('前 4 次不给机会，第 5 次起按概率', () => {
    const results = pokeTimes(
      createCenterPokeCounter(() => 0),
      5
    )
    expect(results).toEqual([null, null, null, null, 'lucky'])
  })

  it('手气一直不好，连点到 30 次保底', () => {
    const results = pokeTimes(
      createCenterPokeCounter(() => 1),
      30
    )
    expect(results.slice(0, 29).every(result => result === null)).toBe(true)
    expect(results[29]).toBe('guarantee')
  })

  it('两次点击间隔太长就从头数', () => {
    const counter = createCenterPokeCounter(() => 0)
    for (let index = 0; index < 4; index++) {
      counter.poke(1000 + index * 100, false)
    }
    expect(counter.poke(10_000, false)).toBeNull()
  })

  it('已经亮过就不再触发', () => {
    const counter = createCenterPokeCounter(() => 0)
    const results = Array.from({ length: 40 }, (_, index) => counter.poke(index * 100, true))
    expect(results.every(result => result === null)).toBe(true)
  })
})
