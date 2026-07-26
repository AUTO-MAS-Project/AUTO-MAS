import { describe, expect, it } from 'vitest'

import { buildCspPolicy, installCspHeaders } from '../contentSecurityPolicy'

describe('content security policy', () => {
  it('production CSP must not allow unsafe-eval', () => {
    const policy = buildCspPolicy()
    expect(policy.productionDirectives).not.toContain("'unsafe-eval'")
    expect(policy.productionDirectives).toContain("script-src 'self'")
    expect(policy.productionDirectives).toContain("default-src 'self'")
  })

  it('production CSP only allows packaged and loopback plugin frames', () => {
    const policy = buildCspPolicy()
    expect(policy.productionDirectives).toContain(
      "frame-src 'self' http://127.0.0.1:* http://localhost:*"
    )
    expect(policy.productionDirectives).not.toContain('frame-src http:')
    expect(policy.productionDirectives).not.toContain('frame-src https:')
  })

  it('production CSP must not allow object/embed', () => {
    const policy = buildCspPolicy()
    expect(policy.productionDirectives).toContain("object-src 'none'")
  })

  it('development CSP allows unsafe-eval for Vite HMR', () => {
    const policy = buildCspPolicy()
    expect(policy.developmentDirectives).toContain("'unsafe-eval'")
    expect(policy.developmentDirectives).toContain(
      "script-src 'self' 'unsafe-eval' 'unsafe-inline'"
    )
  })

  it('development CSP allows localhost connections for dev server', () => {
    const policy = buildCspPolicy()
    expect(policy.developmentDirectives).toContain('http://127.0.0.1:')
    expect(policy.developmentDirectives).toContain('ws://localhost:')
  })

  it('both CSPs restrict plugin frames to self and loopback', () => {
    const policy = buildCspPolicy()
    const expected = "frame-src 'self' http://127.0.0.1:* http://localhost:*"
    expect(policy.productionDirectives).toContain(expected)
    expect(policy.developmentDirectives).toContain(expected)
  })

  it('both CSPs set base-uri to self', () => {
    const policy = buildCspPolicy()
    expect(policy.productionDirectives).toContain("base-uri 'self'")
    expect(policy.developmentDirectives).toContain("base-uri 'self'")
  })

  it('both CSPs set form-action to self', () => {
    const policy = buildCspPolicy()
    expect(policy.productionDirectives).toContain("form-action 'self'")
    expect(policy.developmentDirectives).toContain("form-action 'self'")
  })

  it('production CSP allows only localhost backend connections', () => {
    const policy = buildCspPolicy()
    const connectSrc = policy.productionDirectives
    expect(connectSrc).toContain('connect-src')
    expect(connectSrc).toContain("'self'")
    expect(connectSrc).toContain('127.0.0.1')
    expect(connectSrc).toContain('localhost')
    // 生产态不应允许任意远程连接
    expect(connectSrc).not.toMatch(/https:\/\/\*|http:\/\/\*/)
  })

  it('production CSP permits images only from the packaged app, data/https, and local backend', () => {
    const policy = buildCspPolicy()
    expect(policy.productionDirectives).toContain(
      "img-src 'self' data: https: http://127.0.0.1:* http://localhost:*"
    )
    expect(policy.productionDirectives).not.toContain('img-src *')
  })

  it('custom config overrides defaults', () => {
    const custom = buildCspPolicy({
      productionDirectives: "default-src 'self'",
    })
    expect(custom.productionDirectives).toBe("default-src 'self'")
    expect(custom.developmentDirectives).not.toBe("default-src 'self'")
  })

  it('keeps X-Frame-Options on main documents but does not block approved plugin subframes', () => {
    let listener:
      | ((
          details: { resourceType: string; responseHeaders?: Record<string, string[]> },
          callback: (response: { responseHeaders: Record<string, string[]> }) => void
        ) => void)
      | undefined
    const fakeSession = {
      webRequest: {
        onHeadersReceived: (handler: typeof listener) => {
          listener = handler
        },
      },
    }

    installCspHeaders(fakeSession as never, true)
    expect(listener).toBeTypeOf('function')

    let mainHeaders: Record<string, string[]> = {}
    listener?.({ resourceType: 'mainFrame', responseHeaders: {} }, response => {
      mainHeaders = response.responseHeaders
    })
    expect(mainHeaders['X-Frame-Options']).toEqual(['DENY'])

    let pluginHeaders: Record<string, string[]> = {}
    listener?.({ resourceType: 'subFrame', responseHeaders: {} }, response => {
      pluginHeaders = response.responseHeaders
    })
    expect(pluginHeaders['X-Frame-Options']).toBeUndefined()
    expect(pluginHeaders['Content-Security-Policy']?.[0]).toContain(
      "frame-src 'self' http://127.0.0.1:* http://localhost:*"
    )
  })
})
