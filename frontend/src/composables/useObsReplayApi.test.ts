import { beforeEach, describe, expect, it, vi } from 'vitest'

const checkObsReplayMock = vi.fn()
const saveObsReplayMock = vi.fn()
const listObsReplaysMock = vi.fn()

vi.mock('@/api', () => ({
  ApiError: class extends Error {},
  GetService: {
    checkObsReplayApiSettingObsCheckPost: checkObsReplayMock,
    getObsReplaysApiHistoryReplaysGet: listObsReplaysMock,
  },
  ActionService: {
    saveObsReplayApiSettingObsSavePost: saveObsReplayMock,
  },
}))

vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

describe('useObsReplayApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('checks OBS through the generated service and tracks loading', async () => {
    let resolveCheck!: (value: unknown) => void
    checkObsReplayMock.mockReturnValueOnce(
      new Promise(resolve => {
        resolveCheck = resolve
      })
    )

    const { useObsReplayApi } = await import('./useObsReplayApi')
    const api = useObsReplayApi()
    const request = api.checkObsReplay()

    expect(api.loading.value).toBe(true)
    resolveCheck({
      code: 200,
      connected: true,
      replayActive: true,
      version: '30.2.3',
      directory: 'C:\\replays',
    })
    await expect(request).resolves.toMatchObject({ connected: true, replayActive: true })
    expect(api.loading.value).toBe(false)
    expect(checkObsReplayMock).toHaveBeenCalledOnce()
  })

  it('returns saved and listed replay data', async () => {
    saveObsReplayMock.mockResolvedValueOnce({
      code: 200,
      replay: { replayId: 'r1', failedAt: '2026-10-04T10:00:00', reason: 'failed' },
    })
    listObsReplaysMock.mockResolvedValueOnce({
      code: 200,
      replays: [{ replayId: 'r1', failedAt: '2026-10-04T10:00:00', reason: 'failed' }],
      directory: 'C:\\replays',
    })

    const { useObsReplayApi } = await import('./useObsReplayApi')
    const api = useObsReplayApi()

    await expect(api.saveObsReplay()).resolves.toMatchObject({ replay: { replayId: 'r1' } })
    await expect(api.listObsReplays()).resolves.toMatchObject({ directory: 'C:\\replays' })
    expect(saveObsReplayMock).toHaveBeenCalledOnce()
    expect(listObsReplaysMock).toHaveBeenCalledOnce()
  })

  it('normalizes unsuccessful responses and transport errors', async () => {
    saveObsReplayMock
      .mockResolvedValueOnce({ code: 503, message: 'OBS 未连接' })
      .mockRejectedValueOnce(new Error('network down'))

    const { useObsReplayApi } = await import('./useObsReplayApi')
    const api = useObsReplayApi()

    await expect(api.saveObsReplay()).rejects.toThrow('OBS 未连接')
    expect(api.error.value).toBe('OBS 未连接')
    expect(api.loading.value).toBe(false)

    await expect(api.saveObsReplay()).rejects.toThrow('network down')
    expect(api.error.value).toBe('network down')
    expect(api.loading.value).toBe(false)
  })
})
