import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://127.0.0.1:36163' },
}))

import {
  validatePluginUrl,
  validatePluginEntryUrl,
  validatePluginIframeUrl,
  validatePluginStyleUrl,
  validatePluginUrls,
  isSandboxBypassRisk,
  hasPathTraversal,
} from '../pluginSecurity'

describe('pluginSecurity', () => {
  describe('validatePluginUrl', () => {
    it('rejects empty URL', () => {
      const result = validatePluginUrl('')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('不能为空')
    })

    it('rejects javascript: protocol', () => {
      const result = validatePluginUrl('javascript:alert(1)')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('javascript:')
    })

    it('rejects data: protocol', () => {
      const result = validatePluginUrl('data:text/html,<script>alert(1)</script>')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('data:')
    })

    it('rejects vbscript: protocol', () => {
      const result = validatePluginUrl('vbscript:msgbox(1)')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('vbscript:')
    })

    it('rejects file: protocol', () => {
      const result = validatePluginUrl('file:///C:/Windows/System32/evil.exe')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('file:')
    })

    it('allows relative path starting with /', () => {
      const result = validatePluginUrl('/plugin/m9a/index.html')
      expect(result.safe).toBe(true)
      expect(result.sanitizedUrl).toContain('127.0.0.1:36163')
      expect(result.sanitizedUrl).toContain('/plugin/m9a/index.html')
    })

    it('allows relative path without leading /', () => {
      const result = validatePluginUrl('plugin/m9a/index.html')
      expect(result.safe).toBe(true)
      expect(result.sanitizedUrl).toContain('/plugin/m9a/index.html')
    })

    it('rejects path traversal with ..', () => {
      const result = validatePluginUrl('/plugin/../../../etc/passwd')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('../')
    })

    it('rejects path traversal without leading /', () => {
      const result = validatePluginUrl('../../../etc/passwd')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('../')
    })

    it('rejects protocol-relative URL', () => {
      const result = validatePluginUrl('//evil.com/script.js')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('协议相对')
    })

    it('allows localhost URL', () => {
      const result = validatePluginUrl('http://localhost:3000/plugin/page')
      expect(result.safe).toBe(true)
    })

    it('allows 127.0.0.1 URL', () => {
      const result = validatePluginUrl('http://127.0.0.1:8080/plugin/page')
      expect(result.safe).toBe(true)
    })

    it('allows loopback IPv6 URL', () => {
      const result = validatePluginUrl('http://[::1]:8080/plugin/page')
      expect(result.safe).toBe(true)
    })

    it('rejects non-backend IP addresses', () => {
      const result = validatePluginUrl('http://192.168.1.100:8080/plugin/page')
      expect(result.safe).toBe(false)
    })

    it('rejects remote domain by default', () => {
      const result = validatePluginUrl('https://evil.com/plugin/page')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('远程域名')
    })

    it('allows backend-same-origin URL', () => {
      const result = validatePluginUrl('http://127.0.0.1:36163/plugin/page')
      expect(result.safe).toBe(true)
    })
  })

  describe('validatePluginEntryUrl', () => {
    it('allows localhost entry script', () => {
      const result = validatePluginEntryUrl('http://localhost:5173/plugin/entry.js')
      expect(result.safe).toBe(true)
    })

    it('rejects remote entry script', () => {
      const result = validatePluginEntryUrl('https://evil.com/plugin/entry.js')
      expect(result.safe).toBe(false)
      expect(result.reason).toContain('远程')
    })

    it('allows relative entry script', () => {
      const result = validatePluginEntryUrl('/plugin/test/entry.js')
      expect(result.safe).toBe(true)
    })

    it('rejects dangerous protocol in entry script', () => {
      const result = validatePluginEntryUrl('javascript:evil()')
      expect(result.safe).toBe(false)
    })
  })

  describe('validatePluginIframeUrl', () => {
    it('rejects remote iframe URL', () => {
      const result = validatePluginIframeUrl('https://evil.com/plugin/page')
      expect(result.safe).toBe(false)
    })

    it('allows backend-local iframe URL', () => {
      const result = validatePluginIframeUrl('/plugin/m9a/page')
      expect(result.safe).toBe(true)
    })
  })

  describe('validatePluginStyleUrl', () => {
    it('allows local style URL', () => {
      const result = validatePluginStyleUrl('/plugin/test/style.css')
      expect(result.safe).toBe(true)
    })

    it('rejects empty style URL', () => {
      const result = validatePluginStyleUrl('')
      expect(result.safe).toBe(false)
    })
  })

  describe('validatePluginUrls', () => {
    it('validates multiple URLs', () => {
      const results = validatePluginUrls([
        'http://localhost:3000/a.js',
        'javascript:evil()',
        '/plugin/b.js',
      ])
      expect(results).toHaveLength(3)
      expect(results[0].safe).toBe(true)
      expect(results[1].safe).toBe(false)
      expect(results[2].safe).toBe(true)
    })
  })

  describe('isSandboxBypassRisk', () => {
    it('detects allow-scripts + allow-same-origin', () => {
      expect(isSandboxBypassRisk('allow-scripts allow-same-origin')).toBe(true)
    })

    it('passes allow-scripts alone', () => {
      expect(isSandboxBypassRisk('allow-scripts')).toBe(false)
    })

    it('passes allow-same-origin alone', () => {
      expect(isSandboxBypassRisk('allow-same-origin')).toBe(false)
    })

    it('passes empty sandbox', () => {
      expect(isSandboxBypassRisk('')).toBe(false)
    })
  })

  describe('hasPathTraversal', () => {
    it('detects ../', () => {
      expect(hasPathTraversal('/plugin/../etc/passwd')).toBe(true)
    })

    it('detects encoded ../', () => {
      expect(hasPathTraversal('/plugin/%2e%2e/etc/passwd')).toBe(true)
    })

    it('passes normal path', () => {
      expect(hasPathTraversal('/plugin/test/index.html')).toBe(false)
    })

    it('passes path with dots in filename', () => {
      expect(hasPathTraversal('/plugin/test.v1.0.js')).toBe(false)
    })
  })
})
