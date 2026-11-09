import { createApp, effectScope } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ScriptStatusOverviewItem } from '@/api'
import { collectSatelliteStatuses, useSatelliteStatus } from './useSatelliteStatus'

const { fetchOverview } = vi.hoisted(() => ({ fetchOverview: vi.fn() }))
vi.mock('@/api', () => ({
  GetService: { getScriptStatusOverviewApiInfoScriptsStatusGet: fetchOverview },
}))
vi.mock('./useTaskRuntimeState', () => {
  throw new Error('卫星配置查询不得依赖任务运行状态')
})

const overview = (
  scriptId: string,
  scriptType: string,
  scheduled: boolean,
  lastRunAt: string | null = null,
  lastFailed = false
): ScriptStatusOverviewItem => ({ scriptId, scriptType, scheduled, lastRunAt, lastFailed })

function mountStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let state!: ReturnType<typeof useSatelliteStatus>
  const app = createApp({
    setup() {
      return () => null
    },
  })
  app.use(VueQueryPlugin, { queryClient: client })
  const scope = effectScope()
  scope.run(() =>
    app.runWithContext(() => {
      state = useSatelliteStatus()
    })
  )
  return {
    state,
    dispose() {
      scope.stop()
      client.clear()
      client.unmount()
    },
  }
}

const response = (data: ScriptStatusOverviewItem[], code = 200) =>
  Object.assign(Promise.resolve({ code, message: code === 200 ? '' : 'unavailable', data }), {
    cancel: vi.fn(),
  })

describe('卫星配置与历史概览', () => {
  beforeEach(() => fetchOverview.mockReset())

  it('同类型合并排期，并以最近持久化记录决定结果', () => {
    const data = [
      overview('old', 'MAA', false, '2026-11-01T00:00:00Z', true),
      overview('latest', 'MAA', true, '2026-11-02T00:00:00Z', false),
    ]
    expect(collectSatelliteStatuses(data, new Map()).get('MAA')).toEqual({
      scheduled: true,
      lastFailed: false,
    })
    expect(collectSatelliteStatuses([...data].reverse(), new Map()).get('MAA')).toEqual({
      scheduled: true,
      lastFailed: false,
    })
  })

  it('相同时刻的结果保留失败，通用 MFW 项目按配置关系分别汇总', () => {
    const time = '2026-11-02T00:00:00Z'
    const result = collectSatelliteStatuses(
      [
        overview('a', 'MaaFW', false, time, false),
        overview('b', 'MaaFW', true, time, true),
        overview('c', 'MaaFW', false),
      ],
      new Map([
        ['a', 'project-a'],
        ['b', 'project-a'],
        ['c', 'project-b'],
      ])
    )
    expect(result.get('project-a')).toEqual({ scheduled: true, lastFailed: true })
    expect(result.get('project-b')).toEqual({ scheduled: false, lastFailed: false })
  })

  it('重新挂载后直接恢复后端历史结果，不需要任务事件', async () => {
    fetchOverview.mockImplementation(() =>
      response([overview('s', 'MAA', true, '2026-11-02T00:00:00Z', true)])
    )
    for (let count = 0; count < 2; count++) {
      const { state, dispose } = mountStatus()
      try {
        await state.refresh()
        expect(state.statuses.value.get('MAA')).toEqual({ scheduled: true, lastFailed: true })
        state.setScriptKeys(new Map([['s', 'configured-module']]))
        expect(state.statuses.value.get('configured-module')?.lastFailed).toBe(true)
      } finally {
        dispose()
      }
    }
    expect(fetchOverview).toHaveBeenCalledTimes(2)
  })

  it('查询失败保留最近一次有效配置结果', async () => {
    fetchOverview
      .mockImplementationOnce(() => response([overview('s', 'MAA', true)]))
      .mockImplementationOnce(() => response([], 503))
    const { state, dispose } = mountStatus()
    try {
      await state.refresh()
      await state.refresh()
      expect(state.statuses.value.get('MAA')).toEqual({ scheduled: true, lastFailed: false })
    } finally {
      dispose()
    }
  })
})
