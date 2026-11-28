import { ScriptIndexItem, Service } from '@/api'
import { message } from 'ant-design-vue'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { defineComponent } from 'vue'
import { testView } from '../../../../tests/vueRenderer'
import { useMaaEndPlanOptions } from './useMaaEndPlanOptions'

vi.hoisted(() => {
  vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: vi.fn() }) } })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('脚本列表或资源加载失败时保留重试状态，重试成功后恢复选项', async () => {
  vi.spyOn(message, 'error').mockImplementation(vi.fn())
  vi.spyOn(Service, 'getScriptApiScriptsGetPost')
    .mockResolvedValueOnce({ code: 500, message: '脚本列表暂不可用', index: [], data: {} })
    .mockResolvedValue({
      code: 200,
      index: [{ uid: 'end', type: ScriptIndexItem.type.MAA_END_CONFIG }],
      data: { end: { Info: { Path: 'C:/MaaEnd' } } },
    })
  const resources = vi.spyOn(Service, 'getMaaendOptionsApiScriptsMaaendOptionsPost')
  const options = {
    controllers: [],
    controllerTypes: {},
    essenceLocations: [],
    essenceMenus: [],
    essenceTargetWeaponGroups: [],
  }
  resources.mockResolvedValueOnce({ ...options, code: 500, message: '资源暂不可用' })
  const location = { label: '地点', value: 'location' }
  resources.mockResolvedValue({ ...options, code: 200, essenceLocations: [location] })

  let state!: ReturnType<typeof useMaaEndPlanOptions>
  const view = testView(
    defineComponent({
      setup() {
        state = useMaaEndPlanOptions()
        return () => null
      },
    })
  )
  view.mount()
  try {
    await vi.waitFor(() => expect(state.essenceOptionsError.value).toBe('资源暂不可用'))
    expect(state.essenceOptionsLoaded.value).toBe(false)

    await state.retryOptions()
    expect(state.essenceOptionsLoaded.value).toBe(true)
    expect(state.essenceOptionsError.value).toBeNull()
    expect(state.essenceLocationOptions.value).toEqual([location])
  } finally {
    view.app.unmount()
  }
})
