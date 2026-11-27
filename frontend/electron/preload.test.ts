import { afterEach, describe, expect, it, vi } from 'vite-plus/test'

const { exposeInMainWorld } = vi.hoisted(() => ({ exposeInMainWorld: vi.fn() }))
vi.mock('electron', () => ({ contextBridge: { exposeInMainWorld }, ipcRenderer: {} }))

afterEach(() => {
  vi.unstubAllGlobals()
  exposeInMainWorld.mockClear()
})

describe('preload frame isolation', () => {
  it.each([false, true])('exposes host APIs only in the main frame (%s)', async isMainFrame => {
    vi.resetModules()
    vi.stubGlobal('process', Object.create(process, { isMainFrame: { value: isMainFrame } }))
    await import('./preload')
    expect(exposeInMainWorld.mock.calls.map(([name]) => name)).toEqual(
      isMainFrame ? ['appEnvironment', 'backendOwnership', 'electronAPI'] : []
    )
  })
})
