import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const downloadRequest = vi.fn()
const installRequest = vi.fn()
const cancelRequest = vi.fn()
const switchRequest = vi.fn()
type UpdateWsMessage = {
  id: string
  type: string
  data: Record<string, unknown>
}
type UpdateWsHandler = (message: UpdateWsMessage) => void

const subscribe = vi.fn((_filter: { id?: string; type?: string }, _handler: UpdateWsHandler) => {
  return 'update-subscription'
})
const unsubscribe = vi.fn()

vi.mock('@/api/services/Service', () => ({
  Service: {
    downloadUpdateApiUpdateDownloadPost: downloadRequest,
    installUpdateApiUpdateInstallPost: installRequest,
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
  unsubscribe,
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
    installRequest.mockResolvedValue({ code: 200 })
    cancelRequest.mockResolvedValue({ code: 200 })
    switchRequest.mockResolvedValue({ code: 200 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts download with the requested target version', async () => {
    const download = await loadDownload()

    await download.start('v9.9.9', {})

    expect(downloadRequest).toHaveBeenCalledWith('v9.9.9')
    expect(download.status.value).toBe('downloading')
  })

  it('closes the modal after cancellation succeeds', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    await download.cancel()

    expect(download.status.value).toBe('idle')
    expect(download.modalVisible.value).toBe(false)
    expect(unsubscribe).toHaveBeenCalledWith('update-subscription')
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

  it('clears failed state when the user closes the failed modal', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.receiveSignal({ Failed: '下载失败' })

    download.reset()

    expect(download.status.value).toBe('idle')
    expect(download.modalVisible.value).toBe(false)
    expect(unsubscribe).toHaveBeenCalledWith('update-subscription')
  })

  it('moves to failed after the download timeout', async () => {
    vi.useFakeTimers()
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    await vi.advanceTimersByTimeAsync(2 * 60 * 60 * 1000)

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toContain('下载超时')
  })

  it('enters completed state when download Accomplish signal arrives', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})

    download.receiveSignal({ Accomplish: 'update.zip' })

    expect(download.status.value).toBe('completed')
  })

  it('enters installing state after the backend queues installation', async () => {
    vi.useFakeTimers()
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.receiveSignal({ Accomplish: 'update.zip' })

    await download.install()

    // Lane 01：安装请求发送后直接进入 verifying，等待后端 WS 事件推进
    expect(download.status.value).toBe('verifying')
    expect(installRequest).toHaveBeenCalled()
  })

  it('transitions to installing when update.installing WS event arrives', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.status.value = 'verifying'
    download.failureReason.value = ''

    // 通过 subscribe mock 找到 installing handler
    const wsCall = subscribe.mock.calls.find(
      (call: unknown[]) => (call[0] as { type?: string }).type === 'update.installing'
    )
    expect(wsCall).toBeDefined()
    if (!wsCall) throw new Error('update.installing subscription missing')

    const handler = wsCall[1]
    handler({
      id: 'Update',
      type: 'update.installing',
      data: { job_id: 'test-job', version: 'v6.0.1' },
    })

    expect(download.status.value).toBe('installing')
    expect(download.failureReason.value).toBe('')
  })

  it('transitions to verifying when update.verifying WS event arrives', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.status.value = 'completed'

    const wsCall = subscribe.mock.calls.find(
      (call: unknown[]) => (call[0] as { type?: string }).type === 'update.verifying'
    )
    expect(wsCall).toBeDefined()
    if (!wsCall) throw new Error('update.verifying subscription missing')

    const handler = wsCall[1]
    handler({
      id: 'Update',
      type: 'update.verifying',
      data: { job_id: 'test-job', version: 'v6.0.1' },
    })

    expect(download.status.value).toBe('verifying')
  })

  it('subscribes to verifying and installing WS events', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.reset()

    // 重新触发一次 start 来确保 subscribe 带有完整类型
    await download.start('v9.9.9', {})
    const subscribedTypes = subscribe.mock.calls
      .filter((call: unknown[]) => (call[0] as { id?: string }).id === 'Update')
      .map((call: unknown[]) => (call[0] as { type?: string }).type)
    expect(subscribedTypes).toContain('update.verifying')
    expect(subscribedTypes).toContain('update.installing')
  })

  it('fails from verifying state when failed event arrives', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.status.value = 'verifying'

    const wsCall = subscribe.mock.calls.find(
      (call: unknown[]) => (call[0] as { type?: string }).type === 'update.failed'
    )
    expect(wsCall).toBeDefined()
    if (!wsCall) throw new Error('update.failed subscription missing')

    const handler = wsCall[1]
    handler({
      id: 'Update',
      type: 'update.failed',
      data: { message: '摘要不匹配，完整性校验失败' },
    })

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toContain('摘要不匹配')
  })

  it('fails instead of spinning forever when installation preparation times out', async () => {
    vi.useFakeTimers()
    const download = await loadDownload()
    download.status.value = 'completed'

    await download.install()
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000)

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toContain('安装准备超时')
  })

  it('moves to failed when install returns non-200', async () => {
    installRequest.mockResolvedValue({ code: 500, message: '安装文件损坏' })
    const download = await loadDownload()
    download.status.value = 'completed'

    await download.install()

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toContain('安装文件损坏')
  })

  it('moves to failed when install throws', async () => {
    installRequest.mockRejectedValue(new Error('Network error'))
    const download = await loadDownload()
    download.status.value = 'completed'

    await download.install()

    expect(download.status.value).toBe('failed')
    expect(download.failureReason.value).toContain('Network error')
  })

  // Lane 8：诊断信息测试
  it('diagnosticInfo contains version, source, and failure reason', async () => {
    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.receiveSignal({ Failed: '校验失败' })

    const info = download.diagnosticInfo.value
    expect(info).toContain('v9.9.9')
    expect(info).toContain('校验失败')
    expect(info).toContain('更新诊断信息')
  })

  it('copyDiagnostic calls clipboard writeText', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const download = await loadDownload()
    await download.start('v9.9.9', {})
    download.receiveSignal({ Failed: '测试失败' })

    await download.copyDiagnostic()

    expect(writeText).toHaveBeenCalled()
    const copiedText = writeText.mock.calls[0][0]
    expect(copiedText).toContain('v9.9.9')
    expect(copiedText).toContain('测试失败')
  })
})
