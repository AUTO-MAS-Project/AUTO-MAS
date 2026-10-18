import { describe, expect, it, vi } from 'vite-plus/test'
import { createMaaFWLeaveGuard } from './maafwLeaveGuard'

const deferred = () => {
  let resolve!: (value: boolean) => void
  const promise = new Promise<boolean>(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

describe('createMaaFWLeaveGuard', () => {
  it('离开过程中 leaving 为真；连着发起的离开共用一次检查', async () => {
    const gate = deferred()
    const prepare = vi.fn(() => gate.promise)
    const { leaving, guard } = createMaaFWLeaveGuard(prepare)

    const first = guard()
    const second = guard()
    expect(leaving.value).toBe(true)
    expect(prepare).toHaveBeenCalledOnce()

    gate.resolve(true)
    await expect(first).resolves.toBe(true)
    await expect(second).resolves.toBe(true)
    expect(leaving.value).toBe(false)
  })

  it('放行后同一次离开不再检查，reset 后下次照常检查', async () => {
    const prepare = vi.fn(async () => true)
    const { guard, reset } = createMaaFWLeaveGuard(prepare)
    await guard()
    await guard()
    expect(prepare).toHaveBeenCalledOnce()
    reset()
    await guard()
    expect(prepare).toHaveBeenCalledTimes(2)
  })

  it('选「继续编辑」留在本页：不记放行，下次离开重新检查', async () => {
    const prepare = vi.fn(async () => false)
    const { leaving, guard } = createMaaFWLeaveGuard(prepare)
    await expect(guard()).resolves.toBe(false)
    expect(leaving.value).toBe(false)
    await expect(guard()).resolves.toBe(false)
    expect(prepare).toHaveBeenCalledTimes(2)
  })
})
