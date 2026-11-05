import type { PlanGetOut } from '@/api'
import { describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { useMaaPlanData } from './useMaaPlanData'

const result = (id: string, stage: string): PlanGetOut => ({
  code: 200,
  index: [],
  data: { [id]: { ALL: { Stage: stage } } },
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('MAA plan display data', () => {
  it('ignores old responses and errors after mode changes or disposal', async () => {
    const mode = ref('a')
    const a = deferred<PlanGetOut>()
    const b = deferred<PlanGetOut>()
    const fetch = vi.fn((id: string) => (id === 'a' ? a.promise : b.promise))
    const onError = vi.fn()
    const scope = effectScope()
    const state = scope.run(() => useMaaPlanData(() => mode.value, fetch, onError))!

    mode.value = 'b'
    b.resolve(result('b', '1-7'))
    await nextTick()
    a.reject(new Error('old request'))
    await nextTick()
    expect(state.status.value).toBe('ready')
    expect(state.data.value).toEqual({ ALL: { Stage: '1-7' } })
    expect(onError).not.toHaveBeenCalled()

    mode.value = 'a'
    scope.stop()
    await nextTick()
    expect(onError).not.toHaveBeenCalled()
  })

  it('does not display fixed values when the plan request fails or has no plan', async () => {
    const mode = ref('plan')
    const onError = vi.fn()
    const scope = effectScope()
    const state = scope.run(() =>
      useMaaPlanData(
        () => mode.value,
        async () => ({ code: 200, index: [], data: {} }),
        onError
      )
    )!
    await nextTick()
    expect(state.status.value).toBe('error')
    expect(state.data.value).toBeNull()
    expect(onError).toHaveBeenCalledOnce()
    scope.stop()
  })
})
