import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { effectScope } from 'vue'
import { OperationInfo, Service } from '@/api'
import { usePluginApi } from './usePluginApi'

const { finish } = vi.hoisted(() => ({ finish: vi.fn() }))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish }) }))
vi.mock('@/i18n', () => ({
  i18n: { global: { locale: { value: 'en-US' } } },
  translate: (key: string) => key,
}))

describe('plugin commands and settings', () => {
  const scopes: ReturnType<typeof effectScope>[] = []
  const body = { configUid: 'config', group: 'info', field: 'enable', value: true }
  const operation = {
    operationId: 'operation',
    configUid: 'config',
    field: 'info.enable',
    createdAt: '2026-11-12T00:00:00Z',
  }
  const createApi = () => {
    // 在真实 Vue 作用域内创建业务封装，确保轮询释放使用正式生命周期。
    const scope = effectScope()
    scopes.push(scope)
    return scope.run(usePluginApi)!
  }

  beforeEach(() => {
    // 仅隔离生成客户端和遥测边界，保留业务封装、错误转换和结果等待。
    vi.useFakeTimers()
    vi.stubGlobal('window', { setTimeout })
    finish.mockClear()
  })
  afterEach(() => {
    // 释放作用域、计时器和边界替身，避免跨场景遗留轮询。
    for (const scope of scopes.splice(0)) scope.stop()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each([
    [OperationInfo.state.SUCCEEDED, 'success'],
    [OperationInfo.state.FAILED, 'failure'],
    [OperationInfo.state.CANCELLED, 'cancelled'],
  ] as const)(
    'records %s only after the command reaches its terminal state',
    async (state, outcome) => {
      // 后台受理与完成分开；不同终态必须保留独立结果且只观测一次。
      const start = vi
        .spyOn(Service, 'startOperationApiOperationsStartPost')
        .mockResolvedValue({ code: 200, data: { ...operation, state: OperationInfo.state.QUEUED } })
      const query = vi
        .spyOn(Service, 'getOperationApiOperationsGetPost')
        .mockResolvedValue({ code: 200, data: { ...operation, state } })
      const settled = createApi()
        .runCommand('enable', body)
        .then(
          () => 'success',
          () => 'error'
        )
      await Promise.resolve()
      expect(finish).not.toHaveBeenCalled()
      await vi.runAllTimersAsync()
      expect(await settled).toBe(state === 'succeeded' ? 'success' : 'error')
      expect(start).toHaveBeenCalledWith(body)
      expect(query).toHaveBeenCalledWith({ operationId: 'operation' })
      expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'enable', outcome })
    }
  )

  it('reports unknown after repeated query failures without resubmitting the command', async () => {
    // 轮询网络故障不能变成操作成功，也不能重复提交产生副作用的命令。
    const start = vi
      .spyOn(Service, 'startOperationApiOperationsStartPost')
      .mockResolvedValue({ code: 200, data: { ...operation, state: OperationInfo.state.QUEUED } })
    const query = vi
      .spyOn(Service, 'getOperationApiOperationsGetPost')
      .mockRejectedValue(new Error('disconnected'))
    const settled = createApi()
      .runCommand('enable', body)
      .catch(error => error)
    await vi.runAllTimersAsync()
    expect(await settled).toMatchObject({ message: 'core.plugins.outcomeUnknown' })
    expect(start).toHaveBeenCalledTimes(1)
    expect(query).toHaveBeenCalledTimes(3)
    expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'enable', outcome: 'unknown' })
  })

  it('saves settings without expecting operation IDs or polling command state', async () => {
    // 普通配置保存只消费保存结果，不再依赖 update 返回操作列表。
    const save = vi
      .spyOn(Service, 'updatePluginConfigApiPluginConfigUpdatePost')
      .mockResolvedValue({ code: 200 })
    const query = vi.spyOn(Service, 'getOperationApiOperationsGetPost')
    const patch = { recordId: 'record', data: { info: { value: true } } }
    expect(await createApi().updateConfig(patch)).toEqual({ code: 200 })
    expect(save).toHaveBeenCalledWith(patch, 'en-US')
    expect(query).not.toHaveBeenCalled()
    expect(finish).toHaveBeenCalledExactlyOnceWith({ action: 'config', outcome: 'success' })
  })
})
