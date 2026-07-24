import { describe, expect, it } from 'vitest'

import { normalizeExternalUrl } from './openExternal'

describe('normalizeExternalUrl', () => {
  it.each([
    ['https://example.com/path?q=1', 'https://example.com/path?q=1'],
    ['http://127.0.0.1:8080/docs', 'http://127.0.0.1:8080/docs'],
    ['mailto:test@example.com', 'mailto:test@example.com'],
  ])('allows explicitly supported external URLs', (input, expected) => {
    expect(normalizeExternalUrl(input)).toBe(expected)
  })

  it.each([
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'file:///C:/Windows/System32/calc.exe',
    'custom-protocol://payload',
    '/relative/path',
    'not a URL',
  ])('rejects unsafe or ambiguous URLs', input => {
    expect(normalizeExternalUrl(input)).toBeNull()
  })
})
