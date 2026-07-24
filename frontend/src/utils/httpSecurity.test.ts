import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const BACKEND_BASE = 'http://localhost:36163'
type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

const loadSecurity = async (getBackendAuthToken?: () => Promise<string>) => {
  vi.stubGlobal('window', {
    electronAPI: getBackendAuthToken ? { getBackendAuthToken } : {},
  })
  const { OpenAPI } = await import('@/api/core/OpenAPI')
  OpenAPI.BASE = BACKEND_BASE
  return await import('./httpSecurity')
}

describe('local HTTP authentication', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('adds the process token to a direct API mutation', async () => {
    const fetcher = vi.fn<Fetcher>(async () => new Response('{}', { status: 200 }))
    const tokenProvider = vi.fn(async () => 'a'.repeat(64))
    vi.stubGlobal('fetch', fetcher)
    const { authenticatedApiFetch, HTTP_AUTH_HEADER } = await loadSecurity(tokenProvider)

    const response = await authenticatedApiFetch(`${BACKEND_BASE}/api/plugins/get`, {
      method: 'POST',
    })

    expect(response.status).toBe(200)
    expect(tokenProvider).toHaveBeenCalledOnce()
    const requestInit = fetcher.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(requestInit.headers).get(HTTP_AUTH_HEADER)).toBe('a'.repeat(64))
  })

  it('refreshes a stale token once after an HTTP 401', async () => {
    const fetcher = vi
      .fn<Fetcher>()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
    const tokenProvider = vi
      .fn()
      .mockResolvedValueOnce('a'.repeat(64))
      .mockResolvedValueOnce('b'.repeat(64))
    vi.stubGlobal('fetch', fetcher)
    const { authenticatedApiFetch, HTTP_AUTH_HEADER } = await loadSecurity(tokenProvider)

    const response = await authenticatedApiFetch(`${BACKEND_BASE}/api/core/close`, {
      method: 'POST',
    })

    expect(response.status).toBe(200)
    expect(tokenProvider).toHaveBeenCalledTimes(2)
    const firstInit = fetcher.mock.calls[0]?.[1] as RequestInit
    const secondInit = fetcher.mock.calls[1]?.[1] as RequestInit
    expect(new Headers(firstInit.headers).get(HTTP_AUTH_HEADER)).toBe('a'.repeat(64))
    expect(new Headers(secondInit.headers).get(HTTP_AUTH_HEADER)).toBe('b'.repeat(64))
  })

  it('never sends the backend token to another origin', async () => {
    const fetcher = vi.fn<Fetcher>(async () => new Response('{}', { status: 200 }))
    const tokenProvider = vi.fn(async () => 'a'.repeat(64))
    vi.stubGlobal('fetch', fetcher)
    const { authenticatedApiFetch, HTTP_AUTH_HEADER } = await loadSecurity(tokenProvider)

    await authenticatedApiFetch('https://example.invalid/api/plugins/reload', {
      method: 'POST',
    })

    expect(tokenProvider).not.toHaveBeenCalled()
    const requestInit = fetcher.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(requestInit.headers).has(HTTP_AUTH_HEADER)).toBe(false)
  })

  it('uses loopback metadata only when the Electron IPC bridge is unavailable', async () => {
    const fetcher = vi
      .fn<Fetcher>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ wsAuthToken: 'c'.repeat(64) }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetcher)
    const { authenticatedApiFetch, HTTP_AUTH_HEADER } = await loadSecurity()

    await authenticatedApiFetch(`${BACKEND_BASE}/api/queue/run`, { method: 'POST' })

    expect(fetcher.mock.calls[0]?.[0]).toBe(`${BACKEND_BASE}/api/core/ws_meta`)
    const requestInit = fetcher.mock.calls[1]?.[1] as RequestInit
    expect(new Headers(requestInit.headers).get(HTTP_AUTH_HEADER)).toBe('c'.repeat(64))
  })
})
