import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { useFluxdownInstallApi } from './useFluxdownInstallApi'

const api = vi.hoisted(() => ({ install: vi.fn(), release: vi.fn() }))
vi.mock('@/api', () => ({
  ApiError: class extends Error {},
  GetService: { getFluxdownReleaseApiUpdateFluxdownReleaseGet: api.release },
  Service: { installFluxdownApiUpdateFluxdownInstallPost: api.install },
}))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

beforeEach(() => vi.resetAllMocks())

describe('FluxDown installation result', () => {
  it('waits for the backend and returns the persisted installation result', async () => {
    let finish!: (result: object) => void
    api.install.mockImplementation(() => new Promise(resolve => (finish = resolve)))
    const state = useFluxdownInstallApi()
    const pending = state.installFluxdown('ghfast')
    expect(state.loading.value).toBe(true)
    expect(api.install).toHaveBeenCalledWith({ mirror: 'ghfast' })
    finish({ code: 200, path: 'installed', version: '0.6.3' })
    await expect(pending).resolves.toMatchObject({ path: 'installed' })
    expect(state.loading.value).toBe(false)
    expect(state.error.value).toBeNull()
  })

  it('rejects partial success when the backend could not persist the path', async () => {
    api.install.mockResolvedValue({ code: 500, status: 'error', message: 'path not saved' })
    const state = useFluxdownInstallApi()
    await expect(state.installFluxdown('auto')).rejects.toThrow('path not saved')
    expect(state.error.value).toBe('path not saved')
    expect(state.loading.value).toBe(false)
  })

  it('clears an earlier failure when retrying through another mirror', async () => {
    api.install.mockRejectedValueOnce(new Error('unreachable'))
    api.install.mockResolvedValueOnce({ code: 200, path: 'installed' })
    const state = useFluxdownInstallApi()
    await expect(state.installFluxdown('github')).rejects.toThrow('unreachable')
    await expect(state.installFluxdown('official')).resolves.toMatchObject({ code: 200 })
    expect(state.error.value).toBeNull()
    expect(state.loading.value).toBe(false)
  })
})
