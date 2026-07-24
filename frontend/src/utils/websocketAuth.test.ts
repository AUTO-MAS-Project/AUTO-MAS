import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpSecurityMocks = vi.hoisted(() => ({
  getLocalHttpAuthToken: vi.fn(async () => 'default-test-token'),
  invalidateLocalHttpAuthToken: vi.fn(),
}))

vi.mock('@/utils/httpSecurity', () => httpSecurityMocks)

import {
  buildWebSocketMetaUrl,
  createWebSocketAuthProtocol,
  fetchAuthenticatedWebSocketHandshake,
} from './websocketAuth'

describe('auxiliary WebSocket authentication', () => {
  beforeEach(() => {
    httpSecurityMocks.getLocalHttpAuthToken.mockClear()
    httpSecurityMocks.invalidateLocalHttpAuthToken.mockClear()
  })

  it('builds the shared process-auth subprotocol', () => {
    expect(createWebSocketAuthProtocol('  local-secret  ')).toBe('auto-mas-auth.local-secret')
    expect(createWebSocketAuthProtocol('   ')).toBeUndefined()
    expect(createWebSocketAuthProtocol(null)).toBeUndefined()
  })

  it('uses the HTTP peer of a WebSocket API base for metadata', () => {
    expect(buildWebSocketMetaUrl('ws://127.0.0.1:36163/')).toBe(
      'http://127.0.0.1:36163/api/core/ws_meta'
    )
    expect(buildWebSocketMetaUrl('wss://localhost:36163')).toBe(
      'https://localhost:36163/api/core/ws_meta'
    )
    expect(buildWebSocketMetaUrl('')).toBe('/api/core/ws_meta')
  })

  it('requires a non-empty token and never falls back to an unauthenticated socket', async () => {
    const fetcher = vi.fn(async () =>
      Promise.resolve(
        new Response(JSON.stringify({ devMode: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    )
    const tokenProvider = vi.fn(async () => '')

    await expect(
      fetchAuthenticatedWebSocketHandshake('http://127.0.0.1:36163', fetcher, 3000, tokenProvider)
    ).rejects.toThrow('后端未返回本地 WebSocket 握手令牌')
  })

  it('uses the trusted token provider instead of metadata response secrets', async () => {
    const fetcher = vi.fn(async () =>
      Promise.resolve(
        new Response(JSON.stringify({ devMode: true, wsAuthToken: 'untrusted-body-token' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    )
    const tokenProvider = vi.fn(async () => 'ipc-token-1')

    await expect(
      fetchAuthenticatedWebSocketHandshake('http://127.0.0.1:36163/', fetcher, 3000, tokenProvider)
    ).resolves.toEqual({
      authProtocol: 'auto-mas-auth.ipc-token-1',
      devMode: true,
    })
    expect(tokenProvider).toHaveBeenCalledWith('http://127.0.0.1:36163/')
    expect(httpSecurityMocks.invalidateLocalHttpAuthToken).toHaveBeenCalledOnce()
    expect(httpSecurityMocks.invalidateLocalHttpAuthToken).toHaveBeenCalledWith(
      'http://127.0.0.1:36163/'
    )
    expect(fetcher).toHaveBeenCalledWith(
      'http://127.0.0.1:36163/api/core/ws_meta',
      expect.objectContaining({ cache: 'no-store', method: 'GET' })
    )
  })
})

describe('auxiliary WebSocket call sites', () => {
  const pluginMarketSource = readFileSync(
    new URL('../views/PluginMarket.vue', import.meta.url),
    'utf8'
  )
  const wsdevSource = readFileSync(new URL('../views/WSdev.vue', import.meta.url), 'utf8')
  const schedulerDebugSource = readFileSync(
    new URL('./scheduler-debug.ts', import.meta.url),
    'utf8'
  )

  it('keeps the plugin market on the authenticated main renderer connection', () => {
    expect(pluginMarketSource).toContain('useWebSocket()')
    expect(pluginMarketSource).not.toContain('new WebSocket(')
    expect(pluginMarketSource).not.toContain('/api/ws/plugin')
  })

  it('keeps wsdev both authenticated and development-only', () => {
    expect(wsdevSource).toContain('new WebSocket(wsUrl, handshake.authProtocol)')
    expect(wsdevSource).toContain('if (!handshake.devMode)')
    expect(wsdevSource).not.toContain('new WebSocket(wsUrl)')
  })

  it('does not replace the main renderer connection from scheduler diagnostics', () => {
    expect(schedulerDebugSource).toContain('const { getConnectionInfo, sendRaw } = useWebSocket()')
    expect(schedulerDebugSource).not.toContain('new WebSocket(')
  })
})
