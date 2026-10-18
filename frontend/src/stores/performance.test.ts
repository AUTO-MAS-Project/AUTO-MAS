import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { getConfig, saveConfig } from '@/utils/config'
import type { ScriptRuntimeStatus } from '@/composables/useTaskRuntimeState'
import { usePerformanceStore } from './performance'

vi.mock('@/utils/config', () => ({
  getConfig: vi.fn(),
  saveConfig: vi.fn(),
}))

// useTaskRuntimeState 在模块加载时就摸 window.electronAPI 建 logger，node 测试环境没有；
// 整条斩掉，换成手动驱动的状态表，顺便覆盖 store 里的运行态派生逻辑
vi.mock('@/composables/useTaskRuntimeState', async () => {
  const { ref } = await import('vue')
  const scriptStatusesByType = ref(new Map<string, ScriptRuntimeStatus>())
  return {
    useTaskRuntimeState: () => ({ scriptStatusesByType }),
    setScriptStatuses: (entries: [string, ScriptRuntimeStatus][]) => {
      scriptStatusesByType.value = new Map(entries)
    },
  }
})

const mockedGetConfig = vi.mocked(getConfig)
const mockedSaveConfig = vi.mocked(saveConfig)

describe('performance store', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { electronAPI: {} })
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockedGetConfig.mockResolvedValue({ lowPerformanceMode: false } as Awaited<
      ReturnType<typeof getConfig>
    >)
    mockedSaveConfig.mockResolvedValue()
  })

  it('locks out overlapping low-performance saves', async () => {
    let completeSave: (() => void) | undefined
    mockedSaveConfig.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          completeSave = resolve
        })
    )

    const store = usePerformanceStore()
    await store.initialize()

    const firstSave = store.setLowPerformanceMode(true)
    await vi.waitFor(() => expect(store.saving).toBe(true))

    await store.setLowPerformanceMode(false)

    expect(store.lowPerformanceMode).toBe(true)
    expect(mockedSaveConfig).toHaveBeenCalledTimes(1)
    expect(mockedSaveConfig).toHaveBeenCalledWith({ lowPerformanceMode: true })

    completeSave?.()
    await firstSave
    expect(store.saving).toBe(false)
  })

  it('restores the previous value when saving fails', async () => {
    mockedSaveConfig.mockRejectedValueOnce(new Error('save failed'))
    const store = usePerformanceStore()
    await store.initialize()

    await expect(store.setLowPerformanceMode(true)).rejects.toThrow('save failed')

    expect(store.lowPerformanceMode).toBe(false)
    expect(store.saving).toBe(false)
  })

  it('removes the window activity listener when disposed', async () => {
    const removeWindowActivityListener = vi.fn()
    const onWindowActivityChange = vi.fn(() => removeWindowActivityListener)
    vi.stubGlobal('window', {
      electronAPI: { onWindowActivityChange },
    })

    const store = usePerformanceStore()
    await store.initialize()
    store.$dispose()

    expect(onWindowActivityChange).toHaveBeenCalledOnce()
    expect(removeWindowActivityListener).toHaveBeenCalledOnce()
  })

  it('pauses home effects while a script runs, and resumes only after the debounce', async () => {
    vi.useFakeTimers()
    try {
      // vi.mock 不改 TS 类型，这里只取测试注入用的出口
      const taskRuntimeMock = (await import('@/composables/useTaskRuntimeState')) as unknown as {
        setScriptStatuses: (entries: [string, ScriptRuntimeStatus][]) => void
      }
      const running: [string, ScriptRuntimeStatus] = [
        'maa',
        { queued: false, running: true, lastFailed: false },
      ]

      const store = usePerformanceStore()
      await store.initialize()
      // 旧配置缺省按开启算
      expect(store.pauseHomeEffectsWhenRunning).toBe(true)
      expect(store.homeEffectsPaused).toBe(false)

      taskRuntimeMock.setScriptStatuses([running])
      await nextTick()
      expect(store.anyScriptRunning).toBe(true)
      expect(store.homeEffectsPaused).toBe(true)

      // 点「继续」：手动恢复挂在 store 上，切页/切样式（组件重建）不丢
      store.homeEffectsManuallyResumed = true

      // 队列内脚本交接：瞬时无脚本处于运行，防抖窗口内不恢复
      taskRuntimeMock.setScriptStatuses([
        ['maa', { queued: true, running: false, lastFailed: false }],
      ])
      await nextTick()
      expect(store.anyScriptRunning).toBe(false)
      expect(store.homeEffectsPaused).toBe(true)

      // 窗口内又跑起来：取消恢复，保持暂停
      taskRuntimeMock.setScriptStatuses([running])
      await nextTick()
      await vi.advanceTimersByTimeAsync(4000)
      expect(store.homeEffectsPaused).toBe(true)

      // 清零后要等满整个防抖窗口才恢复，手动恢复随之复位
      taskRuntimeMock.setScriptStatuses([])
      await nextTick()
      await vi.advanceTimersByTimeAsync(4999)
      expect(store.homeEffectsPaused).toBe(true)
      expect(store.homeEffectsManuallyResumed).toBe(true)
      await vi.advanceTimersByTimeAsync(1)
      expect(store.homeEffectsPaused).toBe(false)
      expect(store.homeEffectsManuallyResumed).toBe(false)

      // 关掉设置立即恢复，不看防抖
      taskRuntimeMock.setScriptStatuses([running])
      await nextTick()
      expect(store.homeEffectsPaused).toBe(true)
      await store.setPauseHomeEffectsWhenRunning(false)
      await nextTick()
      expect(mockedSaveConfig).toHaveBeenCalledWith({ pauseHomeEffectsWhenRunning: false })
      expect(store.homeEffectsPaused).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('cancels the pending resume when the store is disposed', async () => {
    vi.useFakeTimers()
    try {
      const store = usePerformanceStore()
      await store.initialize()
      // 先进入暂停，再清零并销毁：恢复定时器应被清掉，不再改动状态
      const { setScriptStatuses } =
        (await import('@/composables/useTaskRuntimeState')) as unknown as {
          setScriptStatuses: (entries: [string, ScriptRuntimeStatus][]) => void
        }
      setScriptStatuses([['maa', { queued: false, running: true, lastFailed: false }]])
      await nextTick()
      setScriptStatuses([])
      await nextTick()
      store.$dispose()
      await vi.advanceTimersByTimeAsync(5000)
      expect(store.homeEffectsPaused).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
