import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { useFluxdownInstallApi } from './useFluxdownInstallApi'

const api = vi.hoisted(() => ({ install: vi.fn(), httpInstall: vi.fn() }))
vi.mock('@/api', () => ({
  ApiError: class extends Error {},
  GetService: {},
  Service: { installFluxdownApiUpdateFluxdownInstallPost: api.httpInstall },
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('window', { electronAPI: { installFluxdown: api.install } })
})

afterEach(() => vi.unstubAllGlobals())

describe('FluxDown installation result', () => {
  it('requires the desktop IPC bridge and never falls back to unauthenticated HTTP', async () => {
    vi.stubGlobal('window', {})
    await expect(useFluxdownInstallApi().installFluxdown('auto')).rejects.toThrow(
      'core.setting.others.fluxdownInstallDesktopRequired'
    )
    expect(api.install).not.toHaveBeenCalled()
    expect(api.httpInstall).not.toHaveBeenCalled()
  })

  it('rejects partial success when the backend could not persist the path', async () => {
    api.install
      .mockResolvedValueOnce({ code: 500, status: 'error', message: 'path not saved' })
      .mockResolvedValueOnce({ code: 200, status: 'error', message: 'path still not saved' })
      .mockResolvedValueOnce({
        code: 200,
        status: 'success',
        message: '',
        path: 'C:\\FluxDown',
      })
    const state = useFluxdownInstallApi()
    await expect(state.installFluxdown('auto')).rejects.toThrow('path not saved')
    expect(state.error.value).toBe('path not saved')
    expect(state.loading.value).toBe(false)
    await expect(state.installFluxdown('auto')).rejects.toThrow('path still not saved')
    expect(state.error.value).toBe('path still not saved')
    await expect(state.installFluxdown('auto')).resolves.toMatchObject({
      status: 'success',
      path: 'C:\\FluxDown',
    })
    expect(state.error.value).toBeNull()
    expect(state.loading.value).toBe(false)
    expect(api.httpInstall).not.toHaveBeenCalled()
  })
})
