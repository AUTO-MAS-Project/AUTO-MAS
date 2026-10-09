import { describe, expect, it } from 'vitest'

import { createCoverLoader, type CoverTask } from './coverLoader'

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

/** 手动放行的封面请求，用来观察同一时刻有几张在途。 */
function controlledFetcher() {
  const pending = new Map<string, (value: string | null) => void>()
  let active = 0
  let peak = 0
  const started: string[] = []
  const task = (key: string): CoverTask => ({
    key,
    run: () => {
      active += 1
      peak = Math.max(peak, active)
      started.push(key)
      return new Promise<string | null>(resolve => {
        pending.set(key, value => {
          active -= 1
          resolve(value)
        })
      })
    },
  })
  const release = (key: string, value: string | null = `data:${key}`): void => {
    pending.get(key)?.(value)
    pending.delete(key)
  }
  return {
    task,
    release,
    started,
    pending,
    peak: () => peak,
  }
}

describe('createCoverLoader', () => {
  it('loads at most `concurrency` covers at a time', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 10, concurrency: 3 })
    loader.load(['a', 'b', 'c', 'd', 'e'].map(fetcher.task))
    expect(fetcher.started).toEqual(['a', 'b', 'c'])

    fetcher.release('a')
    await flush()
    expect(fetcher.started).toEqual(['a', 'b', 'c', 'd'])
    expect(loader.get('a')).toBe('data:a')
    expect(fetcher.peak()).toBe(3)
  })

  it('drops the old queue on reload but still counts requests already in flight', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 10, concurrency: 3 })
    loader.load(['a', 'b', 'c', 'd', 'e'].map(fetcher.task))
    loader.load(['x', 'y', 'z'].map(fetcher.task))
    // a、b、c 还在途，新列表要等它们让出位置
    expect(fetcher.started).toEqual(['a', 'b', 'c'])

    fetcher.release('a')
    fetcher.release('b')
    await flush()
    expect(fetcher.started).toEqual(['a', 'b', 'c', 'x', 'y'])
    expect(fetcher.peak()).toBe(3)

    fetcher.release('c')
    await flush()
    expect(fetcher.started).toEqual(['a', 'b', 'c', 'x', 'y', 'z'])
    // 旧列表里还没开始的 d、e 不再加载
    expect(fetcher.started).not.toContain('d')
    expect(fetcher.peak()).toBe(3)
  })

  it('does not fetch a cached or in-flight cover twice', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 10, concurrency: 3 })
    loader.load([fetcher.task('a')])
    loader.request(fetcher.task('a'))
    fetcher.release('a')
    await flush()
    loader.load([fetcher.task('a')])
    loader.request(fetcher.task('a'))
    expect(fetcher.started).toEqual(['a'])
  })

  it('puts a requested cover in front of the queue', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 10, concurrency: 1 })
    loader.load(['a', 'b', 'c'].map(fetcher.task))
    loader.request(fetcher.task('c'))
    fetcher.release('a')
    await flush()
    expect(fetcher.started).toEqual(['a', 'c'])
  })

  it('evicts the oldest covers beyond the limit', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 2, concurrency: 3 })
    loader.load(['a', 'b', 'c'].map(fetcher.task))
    for (const key of ['a', 'b', 'c']) fetcher.release(key)
    await flush()
    expect(Object.keys(loader.covers.value)).toEqual(['b', 'c'])
    expect(loader.get('a')).toBeUndefined()
  })

  it('keeps failures uncached so they can be retried', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 2, concurrency: 3 })
    loader.load([fetcher.task('a')])
    fetcher.release('a', null)
    await flush()
    expect(loader.get('a')).toBeUndefined()
    loader.request(fetcher.task('a'))
    expect(fetcher.started).toEqual(['a', 'a'])
  })

  it('reset clears the cache and ignores results that arrive afterwards', async () => {
    const fetcher = controlledFetcher()
    const loader = createCoverLoader({ limit: 10, concurrency: 3 })
    loader.load(['a', 'b'].map(fetcher.task))
    fetcher.release('a')
    await flush()
    expect(loader.get('a')).toBe('data:a')

    loader.reset()
    expect(loader.get('a')).toBeUndefined()
    fetcher.release('b')
    await flush()
    expect(loader.get('b')).toBeUndefined()
  })
})
