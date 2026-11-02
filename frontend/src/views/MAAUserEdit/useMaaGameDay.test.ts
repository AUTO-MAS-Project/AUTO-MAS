import { effectScope, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMaaGameDay } from './useMaaGameDay'

afterEach(() => vi.useRealTimers())

describe('MAA game day clock', () => {
  it('updates at the game day boundary and cleans up when the page closes', () => {
    vi.useFakeTimers()
    const start = Date.parse('2026-11-01T19:59:59Z')
    vi.setSystemTime(start)
    const server = ref('Official')
    const scope = effectScope()
    const now = scope.run(() => useMaaGameDay(() => server.value))!

    expect(now.value).toBe(start)
    vi.advanceTimersByTime(1001)
    expect(now.value).toBe(start + 1001)
    expect(vi.getTimerCount()).toBe(1)
    server.value = 'YoStarEN'
    expect(vi.getTimerCount()).toBe(1)
    scope.stop()
    expect(vi.getTimerCount()).toBe(0)
  })
})
