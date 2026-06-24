import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const downloadRequest = vi.fn()
const cancelRequest = vi.fn()
const switchRequest = vi.fn()
const subscribe = vi.fn(() => 'update-subscription')

vi.mock('@/api/services/Service', () => ({
  Service: {
    downloadUpdateApiUpdateDownloadPost: downloadRequest,
    installUpdateApiUpdateInstallPost: vi.fn(),
  },
}))

vi.mock('@/services/updateDownloadApi', () => ({
  updateDownloadApi: {
    cancel: cancelRequest,
    switchToCnb: switchRequest,
  },
}))

vi.mock('@/composables/useWebSocket', () => ({
  subscribe,
}))

vi.mock('ant-design-vue', () => ({
  Modal: { confirm: vi.fn() },
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => logger,
  },
})

const loadDownload = async () => {
  vi.resetModules()
  const { useUpdateDownload } = await import('./useUpdateDownload')
  return useUpdateDownload()
}

describe('useUpdateDownload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    downloadRequest.mockResolvedValue({ code: 200 })
    cancelRequest.mockResolvedValue({ code: 200 })
    switchRequest.mockResolvedValue({ code: 200 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('closes the modal after cancellation succeeds', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    await download.cancel()

    expect(download.status.value).toBe('idle')
    expect(download.modalVisible.value).toBe(false)
  })

  it('keeps the current download when cancellation fails', async () => {
    cancelRequest.mockResolvedValue({ code: 409, message: '取消失败' })
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    await download.cancel()

    expect(download.status.value).toBe('downloading')
    expect(download.modalVisible.value).toBe(true)
    download.reset()
  })

  it('moves to failed when switching source fails after cancellation', async () => {
    switchRequest.mockResolvedValue({ code: 500, message: '保存 CNB 配置失败' })
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    await download.switchToCnb()

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toBe('保存 CNB 配置失败')
  })

  it('can reopen the modal after a background failure', async () => {
    switchRequest.mockResolvedValue({ code: 500, message: '切源失败' })
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.background()
    await download.switchToCnb()

    download.open()

    expect(download.status.value).toBe('failed')
    expect(download.modalVisible.value).toBe(true)
  })

  it('moves to failed after the download timeout', async () => {
    vi.useFakeTimers()
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    await vi.advanceTimersByTimeAsync(2 * 60 * 60 * 1000)

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toContain('下载超时')
  })
})
