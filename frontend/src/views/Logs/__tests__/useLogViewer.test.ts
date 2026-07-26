import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const mockElectron = vi.hoisted(() => ({
  getLogs: vi.fn(),
  exportLogs: vi.fn(),
  showItemInFolder: vi.fn(),
}))

const loadUseLogViewer = async () => {
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
      getLogs: mockElectron.getLogs,
      exportLogs: mockElectron.exportLogs,
      showItemInFolder: mockElectron.showItemInFolder,
    },
  })
  vi.resetModules()
  return import('../useLogViewer')
}

const flushPromises = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

describe('useLogViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('初始加载 app.log 并启用实时刷新', async () => {
    mockElectron.getLogs.mockResolvedValue('line1\nline2')
    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, filteredLines, loading, isRealtime, load, startRealtime } = useLogViewer()

    await load()
    await flushPromises()

    expect(loading.value).toBe(false)
    expect(isRealtime.value).toBe(true)
    expect(rawLines.value).toHaveLength(2)
    expect(filteredLines.value).toHaveLength(2)
    expect(mockElectron.getLogs).toHaveBeenCalledWith(0, 'app.log')

    startRealtime()
    expect(vi.getTimerCount()).toBeGreaterThan(0)
  })

  // ---- 增量读取 ----
  it('首次加载全量读取，轮询时只读尾部 1000 行', async () => {
    mockElectron.getLogs.mockResolvedValue('line1\nline2\nline3')
    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, load, startRealtime } = useLogViewer()

    await load()
    await flushPromises()
    expect(mockElectron.getLogs).toHaveBeenCalledWith(0, 'app.log')
    expect(rawLines.value).toHaveLength(3)

    // 轮询：只读尾部
    mockElectron.getLogs.mockResolvedValue('line2\nline3\nline4')
    startRealtime()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(mockElectron.getLogs).toHaveBeenLastCalledWith(1000, 'app.log')
    // 增量合并：去重后应有 4 行
    expect(rawLines.value).toHaveLength(4)
  })

  // ---- 截断检测 ----
  it('检测到日志文件截断后重新全量加载', async () => {
    // 初始加载全量
    mockElectron.getLogs.mockResolvedValueOnce(
      Array.from({ length: 100 }, (_, i) => `line ${i}`).join('\n')
    )
    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, load, startRealtime } = useLogViewer()

    await load()
    await flushPromises()
    expect(rawLines.value).toHaveLength(100)

    // 轮询时文件被截断（只有 5 行，且内容完全不同）
    // 第一次调用：polling tail read（1000 行）
    // 第二次调用：loadFull full read（0 行）——截断检测后触发
    mockElectron.getLogs
      .mockResolvedValueOnce('new1\nnew2\nnew3\nnew4\nnew5')
      .mockResolvedValueOnce('new1\nnew2\nnew3\nnew4\nnew5')
    startRealtime()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    // 截断检测后应重新全量加载
    expect(mockElectron.getLogs).toHaveBeenLastCalledWith(0, 'app.log')
    expect(rawLines.value).toHaveLength(5)
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('截断'))
  })

  // ---- 有界缓存 ----
  it('超过 maxLines 时只保留最新的行', async () => {
    const longContent = Array.from({ length: 12000 }, (_, i) => `line ${i}`).join('\n')
    mockElectron.getLogs.mockResolvedValue(longContent)
    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, load } = useLogViewer({ maxLines: 10000 })

    await load()
    await flushPromises()

    expect(rawLines.value).toHaveLength(10000)
    expect(rawLines.value[0]).toBe('line 2000')
  })

  // ---- 连接状态 ----
  it('加载失败时进入 disconnected 状态并停止定时器', async () => {
    mockElectron.getLogs.mockRejectedValue(new Error('disk full'))
    const { useLogViewer } = await loadUseLogViewer()
    const { error, connectionState, load, startRealtime } = useLogViewer()

    startRealtime()
    await load()
    await flushPromises()

    expect(error.value).toBe('disk full')
    expect(connectionState.value).toBe('disconnected')
    expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('disk full'))
  })

  it('重连成功后恢复 connected 状态', async () => {
    mockElectron.getLogs.mockRejectedValueOnce(new Error('timeout'))
    const { useLogViewer } = await loadUseLogViewer()
    const { connectionState, retry, load } = useLogViewer()

    await load()
    await flushPromises()
    expect(connectionState.value).toBe('disconnected')

    // 重连成功
    mockElectron.getLogs.mockResolvedValue('restored data')
    const retryPromise = retry()
    // retry 内部 setTimeout(1000) 等待后调用 loadFull
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    await retryPromise

    expect(connectionState.value).toBe('connected')
  })

  it('重连达到最大重试次数后停止', async () => {
    mockElectron.getLogs.mockRejectedValue(new Error('persistent error'))
    const { useLogViewer } = await loadUseLogViewer()
    const { connectionState, error, retry, retryCount, load } = useLogViewer()

    await load()
    await flushPromises()
    expect(connectionState.value).toBe('disconnected')

    // 触发重连
    const retryPromise = retry()
    // 模拟所有重试失败
    for (let i = 0; i < 5; i++) {
      await vi.advanceTimersByTimeAsync(30000)
      await flushPromises()
    }
    await retryPromise

    expect(connectionState.value).toBe('disconnected')
    expect(error.value).toContain('5 次')
    expect(retryCount.value).toBe(5)
  })

  // ---- 可取消轮询 ----
  it('组件卸载后轮询回调不写入状态', async () => {
    mockElectron.getLogs.mockResolvedValue('line')
    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, load, startRealtime, stopRealtime } = useLogViewer()

    await load()
    await flushPromises()
    startRealtime()

    // 模拟卸载
    stopRealtime()
    // 假设组件卸载时的 mounted = false
    // 新的轮询回调不会修改状态
    mockElectron.getLogs.mockResolvedValue('should not appear')
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(rawLines.value).toHaveLength(1)
  })

  // ---- 级别/关键词筛选 ----
  it('按级别筛选日志', async () => {
    mockElectron.getLogs.mockResolvedValue('INFO normal\nERROR crash\nDEBUG detail')
    const { useLogViewer } = await loadUseLogViewer()
    const { filteredLines, setLevel, load } = useLogViewer()

    await load()
    await flushPromises()
    expect(filteredLines.value).toHaveLength(3)

    setLevel('error')
    expect(filteredLines.value).toHaveLength(1)
    expect(filteredLines.value[0]).toContain('ERROR')
  })

  it('按关键词筛选日志（大小写不敏感）', async () => {
    mockElectron.getLogs.mockResolvedValue('Alpha event\nBeta event\nGamma')
    const { useLogViewer } = await loadUseLogViewer()
    const { filteredLines, setKeyword, load } = useLogViewer()

    await load()
    await flushPromises()
    setKeyword('beta')
    expect(filteredLines.value).toHaveLength(1)
    expect(filteredLines.value[0]).toContain('Beta')
  })

  it('级别与关键词组合筛选', async () => {
    mockElectron.getLogs.mockResolvedValue('INFO alpha\nWARN alpha\nERROR beta')
    const { useLogViewer } = await loadUseLogViewer()
    const { filteredLines, setLevel, setKeyword, load } = useLogViewer()

    await load()
    await flushPromises()
    setLevel('warning')
    setKeyword('alpha')
    expect(filteredLines.value).toHaveLength(1)
    expect(filteredLines.value[0]).toContain('WARN')
  })

  // ---- 暂停 ----
  it('暂停时停止实时刷新但不停止加载', async () => {
    mockElectron.getLogs.mockResolvedValue('line')
    const { useLogViewer } = await loadUseLogViewer()
    const { isPaused, togglePause, rawLines, load, startRealtime } = useLogViewer()

    await load()
    await flushPromises()
    togglePause()
    expect(isPaused.value).toBe(true)

    startRealtime()
    mockElectron.getLogs.mockResolvedValue('line\nextra')
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(rawLines.value).toHaveLength(2)
  })

  it('清空视图时保留磁盘日志并停止轮询，手动刷新后可恢复', async () => {
    mockElectron.getLogs.mockResolvedValue('line1\nline2')
    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, isRealtime, viewCleared, clearView, load, startRealtime } = useLogViewer()

    await load()
    await flushPromises()
    startRealtime()

    clearView()
    expect(rawLines.value).toEqual([])
    expect(viewCleared.value).toBe(true)
    expect(isRealtime.value).toBe(false)
    expect(vi.getTimerCount()).toBe(0)

    await load()
    await flushPromises()
    expect(rawLines.value).toEqual(['line1', 'line2'])
    expect(viewCleared.value).toBe(false)
  })

  // ---- 复制/导出 ----
  it('复制当前筛选后的日志到剪贴板', async () => {
    mockElectron.getLogs.mockResolvedValue('a\nb\nc')
    const { useLogViewer } = await loadUseLogViewer()
    const { filteredLines, copyLines, load } = useLogViewer()

    await load()
    await flushPromises()

    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const ok = await copyLines(filteredLines.value)
    expect(ok).toBe(true)
    expect(writeText).toHaveBeenCalledWith('a\nb\nc')
  })

  it('导出日志成功并打开文件夹', async () => {
    mockElectron.exportLogs.mockResolvedValue({ success: true, zipPath: 'D:/logs.zip' })
    mockElectron.showItemInFolder.mockResolvedValue(undefined)
    const { useLogViewer } = await loadUseLogViewer()
    const { exportLogs } = useLogViewer()

    const result = await exportLogs()
    expect(result.success).toBe(true)
    expect(result.zipPath).toBe('D:/logs.zip')
    expect(mockElectron.showItemInFolder).toHaveBeenCalledWith('D:/logs.zip')
  })

  it('导出日志失败返回错误信息', async () => {
    mockElectron.exportLogs.mockResolvedValue({ success: false, error: '权限不足' })
    const { useLogViewer } = await loadUseLogViewer()
    const { exportLogs } = useLogViewer()

    const result = await exportLogs()
    expect(result.success).toBe(false)
    expect(result.error).toBe('权限不足')
  })

  // ---- 停止实时刷新 ----
  it('停止实时刷新后定时器不再触发', async () => {
    mockElectron.getLogs.mockResolvedValue('line')
    const { useLogViewer } = await loadUseLogViewer()
    const { load, startRealtime, stopRealtime } = useLogViewer()

    await load()
    await flushPromises()
    expect(mockElectron.getLogs).toHaveBeenCalledTimes(1)

    startRealtime()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(mockElectron.getLogs).toHaveBeenCalledTimes(2)

    stopRealtime()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(mockElectron.getLogs).toHaveBeenCalledTimes(2)
  })

  // ---- 切换日志源 ----
  it('切换日志源时重新加载对应文件', async () => {
    mockElectron.getLogs.mockResolvedValue('frontend log')
    const { useLogViewer } = await loadUseLogViewer()
    const { source, rawLines, load } = useLogViewer()

    await load()
    await flushPromises()
    expect(rawLines.value).toHaveLength(1)

    source.value = 'frontend'
    await load()
    await flushPromises()

    expect(mockElectron.getLogs).toHaveBeenLastCalledWith(0, 'frontend.log')
  })

  // ---- 大日志性能测试 ----
  it('大日志文件（50000行）加载性能可接受', async () => {
    const bigContent = Array.from(
      { length: 50000 },
      (_, i) => `2024-01-01 10:00:00 INFO [Module] line ${i}`
    ).join('\n')
    mockElectron.getLogs.mockResolvedValue(bigContent)

    const { useLogViewer } = await loadUseLogViewer()
    const { rawLines, load } = useLogViewer({ maxLines: 10000 })

    const start = performance.now()
    await load()
    await flushPromises()
    const elapsed = performance.now() - start

    expect(rawLines.value).toHaveLength(10000)
    // 解析和边界处理应在 500ms 内完成
    expect(elapsed).toBeLessThan(500)
  })
})
