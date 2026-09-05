import { beforeEach, expect, it, vi } from 'vitest'

const check = vi.fn()
const backendVersion = vi.fn()
vi.mock('@/api', () => ({ Service: { getGitVersionApiInfoVersionPost: backendVersion } }))
vi.mock('./useUpdateChecker', () => ({
  requestUpdateCheck: vi.fn(),
  useUpdateChecker: vi.fn(),
  useUpdateModal: vi.fn(),
}))

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  vi.stubGlobal('window', {
    electronAPI: {
      checkRuntimeBackendUpdate: check,
      getLogger: () => ({ debug: vi.fn(), error: vi.fn() }),
    },
  })
})

it('仅在更新已准备完成时提示，并在版本刷新或检查失败时保留提示', async () => {
  const service = await import('./useVersionService')
  check.mockResolvedValueOnce({ updateAvailable: true, staged: false })
  await service.checkRuntimeBackendUpdate()
  expect(service.runtimeBackendUpdateAvailable.value).toBe(false)
  check.mockResolvedValueOnce({ updateAvailable: true, staged: true })
  await service.checkRuntimeBackendUpdate()
  backendVersion.mockResolvedValueOnce({ current_hash: 'old' })
  await service.getBackendVersion()
  expect(service.runtimeBackendUpdateAvailable.value).toBe(true)
  check.mockRejectedValueOnce(new Error('offline'))
  await service.checkRuntimeBackendUpdate()
  expect(service.runtimeBackendUpdateAvailable.value).toBe(true)
})
