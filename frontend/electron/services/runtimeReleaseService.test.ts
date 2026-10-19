import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

import {
  RUNTIME_RELEASE_CACHE_TTL_MS,
  RUNTIME_VERSION_PATTERN,
  buildRuntimeReleaseSources,
  isNewerRuntimeVersion,
  parseRuntimeReleaseList,
  resetLatestRuntimeVersionCache,
  resolveLatestRuntimeVersion,
  resolveLatestRuntimeVersionCached,
  resolveRuntimeReleaseChannel,
  selectLatestRuntimeVersion,
} from './runtimeReleaseService'
import type { RuntimeReleaseFetcher } from './runtimeReleaseService'

const appRepo = 'AUTO-MAS-Project/AUTO-MAS-Runtime'

/** 一条 Release 记录的最小形状：两个来源同名字段。 */
function release(tagName: string, overrides: Record<string, unknown> = {}) {
  return { tag_name: tagName, draft: false, prerelease: false, ...overrides }
}

/** 把若干条记录包成一个「抓取成功」的结果。 */
function listOf(...entries: unknown[]) {
  return { kind: 'text' as const, text: JSON.stringify(entries) }
}

beforeEach(() => {
  resetLatestRuntimeVersionCache()
})

describe('resolveRuntimeReleaseChannel', () => {
  it.each([
    ['5.7.0', 'stable'],
    ['v5.7.0', 'stable'],
    ['5.7.0-beta.5', 'prerelease'],
    ['v5.7.0-rc.1', 'prerelease'],
    ['v5.7.0-beta.5+build.1', 'prerelease'],
  ] as const)('%s 的通道是 %s', (version, expected) => {
    expect(resolveRuntimeReleaseChannel(version)).toBe(expected)
  })
})

describe('buildRuntimeReleaseSources', () => {
  it('CNB 在前、GitHub 兜底，分别带各自的 Accept 与 User-Agent', () => {
    const sources = buildRuntimeReleaseSources()
    expect(sources.map(source => source.key)).toEqual(['cnb', 'github'])
    expect(sources[0].url).toBe(`https://cnb.cool/${appRepo}/-/releases?page_size=20`)
    expect(sources[0].headers.Accept).toBe('application/vnd.cnb.api+json')
    expect(sources[1].url).toBe(`https://api.github.com/repos/${appRepo}/releases?per_page=20`)
    expect(sources[1].headers.Accept).toBe('application/vnd.github+json')
    expect(sources[1].headers['User-Agent']).toBe('AutoMasGui')
  })
})

describe('parseRuntimeReleaseList', () => {
  it('解析出 tag / draft / prerelease 三个字段', () => {
    expect(
      parseRuntimeReleaseList(
        JSON.stringify([
          release('v0.1.23'),
          release('v0.1.24-beta.1', { prerelease: true }),
          release('v0.1.25', { draft: true }),
        ])
      )
    ).toEqual([
      { tagName: 'v0.1.23', draft: false, prerelease: false },
      { tagName: 'v0.1.24-beta.1', draft: false, prerelease: true },
      { tagName: 'v0.1.25', draft: true, prerelease: false },
    ])
  })

  it.each([
    ['非 JSON', '<html>not a list</html>'],
    ['JSON 但是对象', JSON.stringify({ tag_name: 'v0.1.23' })],
    ['空数组', '[]'],
    ['条目全无 tag_name', JSON.stringify([{ name: 'x' }, 1, null])],
    ['空串', ''],
  ])('%s 时返回 null', (_label, text) => {
    expect(parseRuntimeReleaseList(text)).toBeNull()
  })

  it('跳过非对象与空 tag_name 的条目，保留其余', () => {
    expect(
      parseRuntimeReleaseList(
        JSON.stringify([null, 1, { tag_name: '  v0.1.23  ' }, { tag_name: '' }])
      )
    ).toEqual([{ tagName: 'v0.1.23', draft: false, prerelease: false }])
  })
})

describe('selectLatestRuntimeVersion', () => {
  const entriesOf = (...items: string[]) =>
    items.map(tag => ({ tagName: tag, draft: false, prerelease: false }))

  it('正式版通道按语义版本取最大，不用列表顺序', () => {
    const entries = entriesOf('v0.1.9', 'v0.1.23', 'v0.1.10')
    expect(selectLatestRuntimeVersion(entries, 'stable')).toBe('v0.1.23')
  })

  it('正式版通道排除带预发布后缀的 tag', () => {
    const entries = entriesOf('v0.1.22', 'v0.2.0-beta.1')
    expect(selectLatestRuntimeVersion(entries, 'stable')).toBe('v0.1.22')
  })

  it('预发布通道把预发布版本也纳入，仍然取最大', () => {
    const entries = entriesOf('v0.1.22', 'v0.2.0-beta.1', 'v0.2.0')
    expect(selectLatestRuntimeVersion(entries, 'prerelease')).toBe('v0.2.0')
  })

  it('预发布通道里预发布版本比正式版新时选预发布版本', () => {
    const entries = entriesOf('v0.1.23', 'v0.2.0-beta.1')
    expect(selectLatestRuntimeVersion(entries, 'prerelease')).toBe('v0.2.0-beta.1')
  })

  it('去掉 draft 与非法 tag，没有可用条目时返回 null', () => {
    const entries = [
      { tagName: 'v0.1.24', draft: true, prerelease: false },
      { tagName: 'V0.1.25', draft: false, prerelease: false },
      { tagName: 'nightly', draft: false, prerelease: false },
      { tagName: 'v0.1.26; rm -rf /', draft: false, prerelease: false },
    ]
    expect(selectLatestRuntimeVersion(entries, 'prerelease')).toBeNull()
  })

  it('正式版通道同时按 prerelease 标记与 tag 后缀过滤', () => {
    const entries = [
      { tagName: 'v0.1.23', draft: false, prerelease: true },
      { tagName: 'v0.1.22', draft: false, prerelease: false },
    ]
    expect(selectLatestRuntimeVersion(entries, 'stable')).toBe('v0.1.22')
  })
})

describe('isNewerRuntimeVersion', () => {
  it.each([
    ['v0.1.10', 'v0.1.9', true],
    ['v0.1.9', 'v0.1.10', false],
    ['v0.1.5', 'v0.1.5', false],
    ['v0.2.0-beta.1', 'v0.1.23', true],
    ['v0.1.23', 'v0.2.0-beta.1', false],
    ['v0.1.5-beta.10', 'v0.1.5-beta.2', true],
    ['v0.1.5', 'v0.1.5-beta.10', true],
    ['v0.1.5+build.2', 'v0.1.5+build.1', false],
  ] as const)('%s 对 %s 是否更新：%s', (target, installed, expected) => {
    expect(isNewerRuntimeVersion(target, installed)).toBe(expected)
  })
})

describe('resolveLatestRuntimeVersion', () => {
  it('CNB 先给出结果就立刻采用，不再请求 GitHub', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async source => {
      if (source.key === 'cnb') return listOf(release('v0.1.22'), release('v0.1.23'))
      return listOf(release('v0.1.99'))
    })
    const lookup = await resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease })
    expect(lookup).toEqual({ status: 'resolved', version: 'v0.1.23', source: 'cnb' })
    expect(fetchRelease).toHaveBeenCalledTimes(1)
  })

  it('CNB 失败时回落 GitHub', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async source => {
      if (source.key === 'cnb') return { kind: 'failed', error: 'HTTP 503' }
      return listOf(release('v0.1.23'))
    })
    await expect(resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease })).resolves.toEqual(
      { status: 'resolved', version: 'v0.1.23', source: 'github' }
    )
  })

  it('CNB 返回 HTML 之类的非列表内容时也回落 GitHub', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async source => {
      if (source.key === 'cnb') return { kind: 'text', text: '<html>portal</html>' }
      return listOf(release('v0.1.23'))
    })
    await expect(resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease })).resolves.toEqual(
      { status: 'resolved', version: 'v0.1.23', source: 'github' }
    )
  })

  it('两个来源都网络失败时标记 networkUnavailable', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () => ({
      kind: 'failed',
      error: '断网',
      networkUnavailable: true,
    }))
    const lookup = await resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease })
    expect(lookup.status).toBe('unavailable')
    if (lookup.status === 'unavailable') {
      expect(lookup.networkUnavailable).toBe(true)
      expect(lookup.error).toContain('CNB')
      expect(lookup.error).toContain('GitHub')
    }
  })

  it('抓取实现自己抛异常时按失败处理，继续换下一个来源', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async source => {
      if (source.key === 'cnb') throw new Error('boom')
      return listOf(release('v0.1.23'))
    })
    await expect(resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease })).resolves.toEqual(
      { status: 'resolved', version: 'v0.1.23', source: 'github' }
    )
  })

  it('列表里没有该通道的可用版本时是明确失败，不算断网', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () =>
      listOf(release('v0.2.0-beta.1', { prerelease: true }))
    )
    const lookup = await resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease })
    expect(lookup.status).toBe('unavailable')
    if (lookup.status === 'unavailable') expect(lookup.networkUnavailable).toBeUndefined()
  })

  it('默认每个来源的请求带自己的 URL 与请求头', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () => ({
      kind: 'failed',
      error: '跳过',
    }))
    await resolveLatestRuntimeVersion({ channel: 'stable', fetchRelease, timeoutMs: 1234 })
    const sources = buildRuntimeReleaseSources().map(source => source.key)
    expect(fetchRelease.mock.calls.map(([source]) => source.key)).toEqual(sources)
    for (const [, timeoutMs] of fetchRelease.mock.calls) expect(timeoutMs).toBe(1234)
  })
})

describe('resolveLatestRuntimeVersionCached', () => {
  it('缓存有效期内的重复调用不再联网', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () => listOf(release('v0.1.23')))
    const first = await resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    const second = await resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    expect(second).toEqual(first)
    expect(fetchRelease).toHaveBeenCalledTimes(1)
  })

  it('并发调用共用一次请求', async () => {
    let releaseCall!: () => void
    const gate = new Promise<void>(resolve => {
      releaseCall = resolve
    })
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () => {
      await gate
      return listOf(release('v0.1.23'))
    })
    const first = resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    const second = resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    releaseCall()
    await expect(first).resolves.toEqual({ status: 'resolved', version: 'v0.1.23', source: 'cnb' })
    await expect(second).resolves.toEqual({ status: 'resolved', version: 'v0.1.23', source: 'cnb' })
    expect(fetchRelease).toHaveBeenCalledTimes(1)
  })

  it('失败不缓存，下一次会重新联网', async () => {
    let attempt = 0
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () => {
      attempt += 1
      if (attempt <= 2) return { kind: 'failed', error: '断网', networkUnavailable: true }
      return listOf(release('v0.1.23'))
    })
    await expect(
      resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    ).resolves.toMatchObject({ status: 'unavailable' })
    await expect(
      resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    ).resolves.toEqual({ status: 'resolved', version: 'v0.1.23', source: 'cnb' })
    expect(fetchRelease).toHaveBeenCalledTimes(3)
  })

  it('超过缓存时长后重新解析', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () => listOf(release('v0.1.23')))
    const now = vi.spyOn(Date, 'now')
    now.mockReturnValue(1_000_000)
    await resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    now.mockReturnValue(1_000_000 + RUNTIME_RELEASE_CACHE_TTL_MS + 1)
    await resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    expect(fetchRelease).toHaveBeenCalledTimes(2)
    now.mockRestore()
  })

  it('两个通道各自缓存，不互相顶掉', async () => {
    const fetchRelease = vi.fn<RuntimeReleaseFetcher>(async () =>
      listOf(release('v0.1.23'), release('v0.2.0-beta.1', { prerelease: true }))
    )
    await expect(
      resolveLatestRuntimeVersionCached({ channel: 'stable', fetchRelease })
    ).resolves.toEqual({ status: 'resolved', version: 'v0.1.23', source: 'cnb' })
    await expect(
      resolveLatestRuntimeVersionCached({ channel: 'prerelease', fetchRelease })
    ).resolves.toEqual({ status: 'resolved', version: 'v0.2.0-beta.1', source: 'cnb' })
    expect(fetchRelease).toHaveBeenCalledTimes(2)
  })
})

describe('版本号形态', () => {
  it('运行时发布 tag 都能过版本号校验', () => {
    for (const version of ['v0.1.23', 'v1.0.0', 'v0.2.0-beta.1', 'v0.2.0+build.1']) {
      expect(RUNTIME_VERSION_PATTERN.test(version)).toBe(true)
    }
  })
})
