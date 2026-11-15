import { beforeEach, afterEach, expect, it, vi } from 'vite-plus/test'
import { message } from 'ant-design-vue'
import zhCN from '../../../res/i18n/zh_CN.json'

vi.mock('ant-design-vue', () => ({ message: { warning: vi.fn() } }))
vi.mock('@/api', () => ({ Service: {} }))
vi.mock('./useUpdateChecker', () => ({
  readUpdatePauseState: vi.fn(),
  requestUpdateCheck: vi.fn(),
}))
const check = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  vi.stubGlobal('window', {
    electronAPI: {
      checkRuntimeBackendUpdate: check,
      getLogger: () => ({ debug: vi.fn() }),
    },
  })
})
afterEach(() => vi.unstubAllGlobals())

it('预检失败显示原因，同一失败不重复提醒，成功后允许再次提醒', async () => {
  const { i18n } = await import('@/i18n')
  i18n.global.mergeLocaleMessage('zh-CN', zhCN)
  i18n.global.locale.value = 'zh-CN'
  const flow = await import('./useVersionService')
  const failure = {
    updateAvailable: true,
    staged: false,
    remoteCommit: 'b'.repeat(40),
    precheckError: 'adapter requires dependency<2',
    error: 'adapter requires dependency<2',
  }
  check.mockResolvedValue(failure)
  await flow.checkRuntimeBackendUpdate()
  await flow.checkRuntimeBackendUpdate()
  expect(message.warning).toHaveBeenCalledTimes(1)
  expect(message.warning).toHaveBeenCalledWith(
    expect.objectContaining({
      content: expect.stringContaining('adapter requires dependency<2'),
    })
  )
  expect(flow.runtimeBackendUpdateAvailable.value).toBe(false)
  check.mockResolvedValue({ updateAvailable: true, staged: true, commitMessage: 'ready' })
  await flow.checkRuntimeBackendUpdate()
  expect(flow.runtimeBackendUpdateAvailable.value).toBe(true)
  check.mockResolvedValue(failure)
  await flow.checkRuntimeBackendUpdate()
  expect(message.warning).toHaveBeenCalledTimes(2)
  expect(flow.runtimeBackendUpdateAvailable.value).toBe(true)
})
