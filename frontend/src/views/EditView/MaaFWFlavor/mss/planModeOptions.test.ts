import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { getPlanCombox } = vi.hoisted(() => ({ getPlanCombox: vi.fn() }))

vi.mock('@/api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/api')>()),
  Service: { getPlanComboxApiInfoComboxPlanPost: getPlanCombox },
}))

import { PlanComboxIn } from '@/api'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import {
  buildPlanModeOptions,
  isMSSQueueUnrunnable,
  loadMSSPlanComboxItems,
  mssPlanComboxItems,
} from './planModeOptions'

const logError = vi.fn()

beforeEach(() => {
  vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: logError }) } })
})

afterEach(() => {
  vi.unstubAllGlobals()
  getPlanCombox.mockReset()
  logError.mockReset()
  mssPlanComboxItems.value = null
})

describe('MSS 计划表选项', () => {
  it('prepareUserPage 按 MSS 消费方取计划表，结果给下拉用', async () => {
    const items = [
      { label: 'Fixed', value: 'Fixed' },
      { label: '周常', value: 'plan-1' },
    ]
    getPlanCombox.mockResolvedValue({ code: 200, data: items })
    await resolveMaaFWFlavor('MSS').prepareUserPage?.()
    expect(getPlanCombox).toHaveBeenCalledWith({ consumer: PlanComboxIn.consumer.MSS })
    expect(mssPlanComboxItems.value).toEqual(items)
  })

  it('每次进页面重取；非 200 或抛错时只留「固定」，抛错记日志', async () => {
    mssPlanComboxItems.value = [{ label: '旧', value: 'old' }]
    getPlanCombox.mockResolvedValue({ code: 500, data: [] })
    await loadMSSPlanComboxItems()
    expect(mssPlanComboxItems.value).toBeNull()

    getPlanCombox.mockRejectedValue(new Error('断线'))
    await loadMSSPlanComboxItems()
    expect(mssPlanComboxItems.value).toBeNull()
    expect(logError).toHaveBeenCalledWith('加载计划表选项失败: 断线')
    expect(buildPlanModeOptions(mssPlanComboxItems.value, '固定')).toEqual([
      { label: '固定', value: 'Fixed' },
    ])
  })

  it('空队列 + 固定才判跑不起来', () => {
    expect(isMSSQueueUnrunnable(0, 'Fixed')).toBe(true)
    expect(isMSSQueueUnrunnable(0, undefined)).toBe(true)
    expect(isMSSQueueUnrunnable(0, 'plan-1')).toBe(false)
    expect(isMSSQueueUnrunnable(2, 'Fixed')).toBe(false)
  })
})
