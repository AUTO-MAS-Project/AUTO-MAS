import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { getFluxdownInstallEnvironment } from './fluxdownInstallService'
import { qqCredentials } from './qqCredentialService'

afterEach(() => vi.unstubAllGlobals())

describe('QQ credentials authority', () => {
  it('sends the token only from the main process to the fixed local endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 200 })))
    vi.stubGlobal('fetch', fetchMock)
    const data = { bindingId: 'binding', appId: 'app', userOpenId: 'owner', clientSecret: 'secret' }
    await qqCredentials('http://127.0.0.1:36164', 'set', data)
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('http://127.0.0.1:36164/api/setting/openclaw-qq/credentials/set')
    expect(options.headers.Authorization).toBe(
      `Bearer ${getFluxdownInstallEnvironment().AUTO_MAS_INSTALL_TOKEN}`
    )
    expect(options.redirect).toBe('error')
    expect(JSON.parse(options.body)).toEqual(data)
  })

  it.each(['https://example.invalid', 'http://example.invalid', 'http://u:p@127.0.0.1'])(
    'rejects an untrusted backend %s before sending credentials',
    async base => {
      const fetchMock = vi.fn()
      vi.stubGlobal('fetch', fetchMock)
      await expect(qqCredentials(base, 'get')).rejects.toThrow()
      expect(fetchMock).not.toHaveBeenCalled()
    }
  )
})
