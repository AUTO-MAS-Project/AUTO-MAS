import { Service } from '@/api'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { PLAN_CONFIG_TYPES, getPlanTypeOption } from '@/utils/planTypeRegistry'
import { message } from 'ant-design-vue'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { usePlanApi } from './usePlanApi'

const playSound = vi.hoisted(() => {
  vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: vi.fn() }) } })
  return vi.fn()
})
vi.mock('@/composables/useAudioPlayer', () => ({ useAudioPlayer: () => ({ playSound }) }))

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('拒绝 HTTP 成功的计划写入失败，且不播放成功音效', async () => {
  const failure = { code: 500, status: 'error', message: '计划写入被拒绝' }
  vi.spyOn(message, 'error').mockImplementation(vi.fn())
  vi.spyOn(Service, 'addPlanApiPlanAddPost').mockResolvedValue({ ...failure, planId: '', data: {} })
  vi.spyOn(Service, 'deletePlanApiPlanDeletePost').mockResolvedValue(failure)
  vi.spyOn(Service, 'reorderPlanApiPlanOrderPost').mockResolvedValue(failure)

  const api = usePlanApi()
  const plan = getPlanTypeOption(PLAN_CONFIG_TYPES.UNIVERSAL, indexPluginScriptTypes())!
  await expect(api.createPlan(plan)).rejects.toMatchObject({ code: 500, message: failure.message })
  await expect(api.deletePlan('plan')).rejects.toMatchObject({
    code: 500,
    message: failure.message,
  })
  await expect(api.reorderPlans(['plan'])).rejects.toMatchObject({
    code: 500,
    message: failure.message,
  })
  expect(playSound).not.toHaveBeenCalled()
})
