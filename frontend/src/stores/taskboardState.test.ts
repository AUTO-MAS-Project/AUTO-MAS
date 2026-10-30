import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  getState: vi.fn(),
  setWeekly: vi.fn(),
  setVersionStory: vi.fn(),
}))

vi.mock('@/api', () => ({
  ApiError: class ApiError extends Error {
    body?: unknown
  },
  GetService: {
    getTaskboardStateApiInfoTaskboardStateGet: mocks.getState,
  },
  SetService: {
    setTaskboardWeeklyApiInfoTaskboardWeeklyPut: mocks.setWeekly,
    setTaskboardVersionStoryApiInfoTaskboardVersionStoryPut: mocks.setVersionStory,
  },
}))

import { useTaskboardStateStore } from './taskboardState'

const emptyState = () => ({
  code: 200,
  data: {
    selected_games: null,
    weekly_games: null,
    archived: [],
    done_at: {},
    weekly: {},
    version_story: {},
    version_story_done: {},
  },
  weekly_week: '',
})

describe('taskboardState 周常与版本目录', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-26T03:59:00+08:00'))
    setActivePinia(createPinia())
    mocks.getState.mockReset()
    mocks.setWeekly.mockReset()
    mocks.setVersionStory.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('drops last week completion after the reset and marks the new week on first click', async () => {
    mocks.getState.mockResolvedValue({
      ...emptyState(),
      data: {
        ...emptyState().data,
        weekly: { genshin: { week: '2026-10-19', done_at: '2026-10-20 10:00' } },
      },
      weekly_week: '2026-10-19',
    })

    const store = useTaskboardStateStore()
    await store.load()
    expect(store.isWeeklyDone('genshin')).toBe(true)

    vi.setSystemTime(new Date('2026-10-26T04:01:00+08:00'))
    vi.advanceTimersByTime(2 * 60 * 1000)
    expect(store.isWeeklyDone('genshin')).toBe(false)

    mocks.setWeekly.mockResolvedValue({ code: 200, week: '2026-10-26' })
    await store.saveWeekly('genshin', true)

    expect(mocks.setWeekly).toHaveBeenCalledWith({
      key: 'genshin',
      done: true,
      week: '2026-10-26',
    })
    expect(store.isWeeklyDone('genshin')).toBe(true)
  })

  it('keeps a version record saved while the initial load is still in flight', async () => {
    let resolveLoad: (value: unknown) => void = () => {}
    mocks.getState.mockReturnValue(
      new Promise(resolve => {
        resolveLoad = resolve
      })
    )
    mocks.setVersionStory.mockResolvedValue({ code: 200 })

    const store = useTaskboardStateStore()
    const loading = store.load()

    await store.saveVersionStory([
      {
        game: 'genshin',
        version: '9.9',
        version_name: '测试版本',
        start: '2026-01-01T00:00:00+08:00',
        end: '2026-02-01T00:00:00+08:00',
        cover_url: '',
      },
    ])
    expect(store.versionStory['genshin|9.9']).toBeTruthy()

    resolveLoad({ ...emptyState() })
    await loading

    expect(store.loaded).toBe(true)
    expect(store.versionStory['genshin|9.9']).toBeTruthy()
  })
})
