import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { getFluxdownInstallEnvironment } from './fluxdownInstallService'
import { fetchProtectedLocal } from './protectedBackend'

afterEach(() => vi.unstubAllGlobals())

describe('protected local backend', () => {
  it('sends backup requests to the fixed local endpoint with authority and no redirects', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('backup'))
    vi.stubGlobal('fetch', fetchMock)
    await fetchProtectedLocal('http://127.0.0.1:36164', '/api/setting/backup')
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('http://127.0.0.1:36164/api/setting/backup')
    expect(options.method).toBe('GET')
    expect(options.headers.Authorization).toBe(
      `Bearer ${getFluxdownInstallEnvironment().AUTO_MAS_INSTALL_TOKEN}`
    )
    expect(options.redirect).toBe('error')
  })

  it('rejects unsupported paths and nonlocal backends before sending the token', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    expect(() => fetchProtectedLocal('http://127.0.0.1', '/arbitrary')).toThrow()
    expect(() => fetchProtectedLocal('http://example.invalid', '/api/setting/backup')).toThrow()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
