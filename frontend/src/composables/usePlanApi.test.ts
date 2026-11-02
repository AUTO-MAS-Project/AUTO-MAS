import { beforeEach, describe, expect, it, vi } from 'vitest'

const { request, errorMessage } = vi.hoisted(() => ({ request: vi.fn(), errorMessage: vi.fn() }))
vi.mock('@/api', () => ({ Service: { getPlanApiPlanGetPost: request } }))
vi.mock('ant-design-vue', () => ({ message: { error: errorMessage } }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('@/composables/useAudioPlayer', () => ({ useAudioPlayer: vi.fn() }))
vi.mock('@/utils/planTypeRegistry', () => ({
  getPlanTypeDescriptor: vi.fn(),
  getPlanCreateType: vi.fn(),
}))
vi.mock('@/utils/analytics', () => ({
  analyticsCountBucket: vi.fn(),
  beginAnalyticsOperation: vi.fn(),
}))

describe('plan read notifications', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: vi.fn() }) } })
  })

  it('keeps silent requests free of UI side effects while preserving normal errors', async () => {
    const { usePlanApi } = await import('./usePlanApi')
    const api = usePlanApi()
    request.mockRejectedValue(new Error('network'))
    await expect(api.getPlans('plan', { silent: true })).rejects.toThrow('network')
    expect(errorMessage).not.toHaveBeenCalled()
    expect(api.loading.value).toBe(false)
    await expect(api.getPlans('plan')).rejects.toThrow('network')
    expect(errorMessage).toHaveBeenCalledOnce()
    expect(api.loading.value).toBe(false)
  })
})
