import * as path from 'path'
import { pathToFileURL } from 'url'

import { describe, expect, it } from 'vitest'

import { isTrustedRendererNavigation, normalizeExternalNavigation } from '../rendererSecurityPolicy'

describe('renderer navigation policy', () => {
  const packagedHtmlPath = path.resolve(
    'C:\\Program Files\\AUTO-MAS\\resources\\app.asar\\dist\\index.html'
  )

  it('allows only the packaged entry file in production', () => {
    const policy = { packagedHtmlPath }
    expect(isTrustedRendererNavigation(pathToFileURL(packagedHtmlPath).href, policy)).toBe(true)
    expect(
      isTrustedRendererNavigation(
        pathToFileURL(path.join(path.dirname(packagedHtmlPath), 'attacker.html')).href,
        policy
      )
    ).toBe(false)
    expect(isTrustedRendererNavigation('https://evil.example/plugin-docs', policy)).toBe(false)
  })

  it('allows only the configured development-server origin in development', () => {
    const policy = {
      packagedHtmlPath,
      devServerUrl: 'http://127.0.0.1:5173',
    }
    expect(isTrustedRendererNavigation('http://127.0.0.1:5173/#/scripts', policy)).toBe(true)
    expect(isTrustedRendererNavigation('http://localhost:5173/#/scripts', policy)).toBe(false)
    expect(isTrustedRendererNavigation('https://127.0.0.1:5173/', policy)).toBe(false)
  })

  it('delegates ordinary web and mail links but rejects executable schemes', () => {
    expect(normalizeExternalNavigation('https://docs.example/path')).toBe(
      'https://docs.example/path'
    )
    expect(normalizeExternalNavigation('mailto:team@example.com')).toBe('mailto:team@example.com')
    expect(normalizeExternalNavigation('javascript:alert(1)')).toBeNull()
    expect(normalizeExternalNavigation('file:///C:/Windows/win.ini')).toBeNull()
  })
})
