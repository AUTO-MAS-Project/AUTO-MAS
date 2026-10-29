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
    expect(options.headers.Authorization).toBe(`Bearer ${env.AUTO_MAS_INSTALL_TOKEN}`)
    expect(options.redirect).toBe('error')
    expect(JSON.parse(options.body)).toEqual({ mirror: 'auto' })
    expect(JSON.stringify(result).includes(env.AUTO_MAS_INSTALL_TOKEN!)).toBe(false)
  })

  it.each(['https://attacker.test', 'http://attacker.test', 'http://user:pass@127.0.0.1'])(
    'refuses to disclose a credential to %s',
    async url => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)
      await expect(installFluxdown(url, 'auto')).rejects.toThrow()
      expect(fetchMock).not.toHaveBeenCalled()
    }
  )

  it('rejects arbitrary payloads before making a request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      installFluxdown('http://127.0.0.1:36164', { url: 'https://attacker.test' })
    ).rejects.toThrow()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
