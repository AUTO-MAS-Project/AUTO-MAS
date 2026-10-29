import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { useMaaCopilotApi } from './useMaaCopilotApi'

const { analyze, finish } = vi.hoisted(() => ({ analyze: vi.fn(), finish: vi.fn() }))
vi.mock('@/api', () => ({
  Service: { analyzeMaaCopilotTrainingApiScriptsMaaCopilotAnalyzePost: analyze },
}))
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish }),
}))

describe('MAA 作业分析', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each([false, true])('透传等级筛选 %s 并只观察一次分析结果', async ignoreLevelGaps => {
    const request = { scriptId: 'script', userId: 'user', ignoreLevelGaps }
    const response = { code: 200, ready: 1 }
    analyze.mockResolvedValue(response)
    await expect(useMaaCopilotApi().analyze(request)).resolves.toBe(response)
    expect(analyze).toHaveBeenCalledExactlyOnceWith(request)
    expect(finish).toHaveBeenCalledExactlyOnceWith({
      script_type: 'MAA',
      operation_kind: 'preview',
      engine_kind: 'unknown',
      outcome: 'success',
    })
  })

  it('保留业务失败提示并记录失败结果', async () => {
    analyze.mockResolvedValue({ code: 400, message: 'Synthetic rejection' })
    await expect(
      useMaaCopilotApi().analyze({ scriptId: 'script', userId: 'user' })
    ).rejects.toThrow('Synthetic rejection')
    expect(finish).toHaveBeenCalledOnce()
    expect(finish).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'failure' }))
  })

  it('保留网络异常并将分析结果记为未知', async () => {
    const error = new Error('Synthetic network failure')
    analyze.mockRejectedValue(error)
    await expect(useMaaCopilotApi().analyze({ scriptId: 'script', userId: 'user' })).rejects.toBe(
      error
    )
    expect(finish).toHaveBeenCalledOnce()
    expect(finish).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'unknown' }))
  })
})
