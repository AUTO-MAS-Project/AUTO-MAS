import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { useMaaCultivateDataApi } from './useMaaCultivateDataApi'

const { refresh, finish } = vi.hoisted(() => ({ refresh: vi.fn(), finish: vi.fn() }))
vi.mock('@/api', () => ({
  Service: { refreshMaaCultivateDataApiScriptsMaaCultivateRefreshPost: refresh },
}))
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish }),
}))

describe('MAA 养成数据手动刷新', () => {
  beforeEach(() => vi.clearAllMocks())

  it('只请求一次完整刷新并记录实际结果', async () => {
    refresh.mockResolvedValue({ code: 200 })
    await useMaaCultivateDataApi().refresh('script')
    expect(refresh).toHaveBeenCalledExactlyOnceWith({ scriptId: 'script' })
    expect(finish).toHaveBeenCalledExactlyOnceWith({
      script_type: 'MAA',
      operation_kind: 'data_refresh',
      engine_kind: 'unknown',
      outcome: 'success',
    })
  })

  it('业务失败不会被当成刷新成功', async () => {
    refresh.mockResolvedValue({ code: 500, message: 'Synthetic failure' })
    await expect(useMaaCultivateDataApi().refresh('script')).rejects.toThrow('Synthetic failure')
    expect(finish).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ outcome: 'failure' }))
  })

  it.each([
    [503, 'source'],
    [507, 'cache'],
    [500, 'service'],
  ] as const)('应用错误 %s 保留可本地化的失败原因', async (code, reason) => {
    refresh.mockResolvedValue({ code, message: 'Internal diagnostic detail' })
    await expect(useMaaCultivateDataApi().refresh('script')).rejects.toMatchObject({ reason })
    expect(finish).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ outcome: 'failure' }))
  })

  it('网络失败保留异常且只观察一次结果', async () => {
    const error = new Error('Synthetic network outage')
    refresh.mockRejectedValue(error)
    await expect(useMaaCultivateDataApi().refresh('script')).rejects.toBe(error)
    expect(finish).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ outcome: 'unknown' }))
  })
})
