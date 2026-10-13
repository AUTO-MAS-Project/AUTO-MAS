import { describe, expect, it, vi } from 'vitest'
import { useApiQuery } from './useApiQuery'

describe('useApiQuery', () => {
  it('reuses a pending read and clears loading after completion', async () => {
    let complete!: (value: number) => void
    const request = vi.fn(() => new Promise<number>(resolve => { complete = resolve }))
    const query = useApiQuery(request, () => 'Load failed')
    const first = query.execute()
    expect(query.execute()).toBe(first)
    expect(query.loading.value).toBe(true)
    await Promise.resolve()
    complete(7)
    await expect(first).resolves.toBe(7)
    expect(request).toHaveBeenCalledTimes(1)
    expect(query.loading.value).toBe(false)
    expect(query.data.value).toBe(7)
  })

  it('keeps loaded data after failure and recovers on a manual retry', async () => {
    const request = vi.fn<() => Promise<number>>()
      .mockResolvedValueOnce(1)
      .mockRejectedValueOnce(new Error('Disconnected'))
      .mockResolvedValueOnce(2)
    const query = useApiQuery(request, () => 'Load failed')
    await query.execute()
    await expect(query.execute()).resolves.toBeNull()
    expect(query.data.value).toBe(1)
    expect(query.error.value).toBe('Disconnected')
    expect(request).toHaveBeenCalledTimes(2)
    await query.execute()
    expect(query.error.value).toBeNull()
    expect(query.data.value).toBe(2)
  })

  it('recovers when the request throws before returning a promise', async () => {
    const request = vi.fn<() => Promise<number>>()
      .mockImplementationOnce(() => { throw new Error('Unavailable') })
      .mockResolvedValueOnce(3)
    const query = useApiQuery(request, () => 'Load failed')
    await expect(query.execute()).resolves.toBeNull()
    expect(query.loading.value).toBe(false)
    await expect(query.execute()).resolves.toBe(3)
    expect(request).toHaveBeenCalledTimes(2)
  })
})
