import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getConfig, saveConfig } from '@/utils/config'
import { usePerformanceStore } from './performance'

vi.mock('@/utils/config', () => ({
  getConfig: vi.fn(),
  saveConfig: vi.fn(),
}))

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
})
