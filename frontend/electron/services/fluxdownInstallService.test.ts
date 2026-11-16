import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { getFluxdownInstallEnvironment, installFluxdown } from './fluxdownInstallService'

afterEach(() => vi.unstubAllGlobals())

describe('FluxDown installation authority', () => {
  it('keeps the credential in the main process and authorizes the fixed backend action', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ code: 200, path: 'installed' })))
    vi.stubGlobal('fetch', fetchMock)
    const env = getFluxdownInstallEnvironment()
    expect(env.AUTO_MAS_INSTALL_TOKEN).toMatch(/^[a-f0-9]{64}$/)
    const result = await installFluxdown('http://127.0.0.1:36164', 'auto')
    expect(result).toEqual({ code: 200, path: 'installed' })
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('http://127.0.0.1:36164/api/update/fluxdown/install')
    expect(options.method).toBe('POST')
    expect(options.headers.Authorization).toBe(`Bearer ${env.AUTO_MAS_INSTALL_TOKEN}`)
    expect(options.redirect).toBe('error')
    expect(JSON.parse(options.body)).toEqual({ mirror: 'auto' })
    expect(JSON.stringify(result).includes(env.AUTO_MAS_INSTALL_TOKEN!)).toBe(false)
    for (const [baseUrl, mirror] of [
      ['https://attacker.test', 'auto'],
      ['http://attacker.test', 'auto'],
      ['http://user:pass@127.0.0.1', 'auto'],
      ['http://127.0.0.1:36164', { url: 'https://attacker.test' }],
    ] as const) {
      fetchMock.mockClear()
      await expect(installFluxdown(baseUrl, mirror), baseUrl).rejects.toThrow()
      expect(fetchMock, baseUrl).not.toHaveBeenCalled()
    }
  })
})
