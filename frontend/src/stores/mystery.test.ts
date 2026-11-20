import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { nextTick, ref, watch } from 'vue'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { getMysteryContext } from '@/composables/useMysteryApi'
import { getConfig } from '@/utils/config'
import { getMysteryDate } from '@/utils/mysteryAccess'
import type { WSConnectionState } from '@/composables/useWebSocket'
import { useMysteryStore } from './mystery'

const state = ref<WSConnectionState>('open')
vi.mock('@/composables/useWebSocket', () => ({ useWebSocket: () => ({ state }) }))
vi.mock('@/composables/useMysteryApi', () => ({
  getMysteryContext: vi.fn(),
  MysteryContextError: class extends Error {},
}))
vi.mock('@/utils/config', () => ({ getConfig: vi.fn(), saveConfig: vi.fn() }))

const pinia = createPinia()
afterEach(() => disposePinia(pinia))

it('同一后端重连保留已打开的功能，换用不同源码后锁回', async () => {
  setActivePinia(pinia)
  const context = { deviceHash: 'a'.repeat(64), backendHash: 'b'.repeat(64) }
  vi.mocked(getConfig, { partial: true }).mockResolvedValue({
    mysteryUnlockedDate: getMysteryDate(),
    mysteryUnlockedFingerprint: `${context.deviceHash}:${context.backendHash}`,
  })
  vi.mocked(getMysteryContext).mockResolvedValue(context)
  const store = useMysteryStore()
  await store.load()
  const visible = () => store.initialized && store.unlocked && !store.loadError
  expect(visible()).toBe(true)
  const changes: boolean[] = []
  const stop = watch(visible, value => changes.push(value))
  try {
    state.value = 'reconnecting'
    await nextTick()
    state.value = 'open'
    await nextTick()
    await store.load()
    expect(changes).toEqual([])

    vi.mocked(getMysteryContext).mockResolvedValue({ ...context, backendHash: 'c'.repeat(64) })
    state.value = 'reconnecting'
    await nextTick()
    state.value = 'open'
    await nextTick()
    await store.load()
    expect(visible()).toBe(false)
    expect(changes).toEqual([false])
  } finally {
    stop()
  }
})
