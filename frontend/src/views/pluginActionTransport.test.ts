import { describe, expect, it, vi } from 'vitest'
import {
  PluginWebSocketCommandError,
  requestPluginActionWithFallback,
} from './pluginActionTransport'

describe('plugin action transport fallback', () => {
  it('falls back to HTTP when the WebSocket command was not sent', async () => {
    const sendOverHttp = vi.fn(async () => ({ transport: 'http' }))

    const result = await requestPluginActionWithFallback({
      endpoint: 'plugins.add',
      sendOverWebSocket: async () => {
        throw new PluginWebSocketCommandError('websocket unavailable', false)
      },
      sendOverHttp,
    })

    expect(result).toEqual({ transport: 'http' })
    expect(sendOverHttp).toHaveBeenCalledOnce()
  })

  it.each([
    'plugins.add',
    'plugins.update',
    'plugins.delete',
    'plugins.reload',
    'plugins.reload_instance',
    'plugins.reload_plugin',
    'plugins.install_package',
    'plugins.uninstall_package',
  ])('does not replay dispatched mutation %s over HTTP', async endpoint => {
    const sendOverHttp = vi.fn(async () => ({ transport: 'http' }))

    await expect(
      requestPluginActionWithFallback({
        endpoint,
        sendOverWebSocket: async () => {
          throw new PluginWebSocketCommandError('response timeout; outcome unknown', true)
        },
        sendOverHttp,
      })
    ).rejects.toThrow('outcome unknown')
    expect(sendOverHttp).not.toHaveBeenCalled()
  })

  it('allows the read-only plugins.get command to fall back after dispatch', async () => {
    const sendOverHttp = vi.fn(async () => ({ transport: 'http' }))

    const result = await requestPluginActionWithFallback({
      endpoint: 'plugins.get',
      sendOverWebSocket: async () => {
        throw new PluginWebSocketCommandError('response timeout; outcome unknown', true)
      },
      sendOverHttp,
    })

    expect(result).toEqual({ transport: 'http' })
    expect(sendOverHttp).toHaveBeenCalledOnce()
  })

  it('does not replay a mutation when an unclassified error has unknown delivery state', async () => {
    const sendOverHttp = vi.fn(async () => ({ transport: 'http' }))

    await expect(
      requestPluginActionWithFallback({
        endpoint: 'plugins.update',
        sendOverWebSocket: async () => {
          throw new Error('unexpected transport error')
        },
        sendOverHttp,
      })
    ).rejects.toThrow('unexpected transport error')
    expect(sendOverHttp).not.toHaveBeenCalled()
  })
})
