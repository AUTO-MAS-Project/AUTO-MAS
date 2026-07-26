/**
 * 插件 UI 安全边界：恶意输入穿透测试。
 *
 * 覆盖：
 * - 恶意 URL/path 越界攻击
 * - 危险协议注入
 * - iframe sandbox 绕过
 * - manifest 恶意字段
 * - 编码绕过
 */

import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://127.0.0.1:36163' },
}))

import {
  validatePluginUrl,
  validatePluginEntryUrl,
  validatePluginStyleUrl,
  isSandboxBypassRisk,
  hasPathTraversal,
} from '../pluginSecurity'
import { validateManifest, PLUGIN_UI_MANIFEST_VERSION } from '../pluginUIManifest'

describe('pluginSecurity - malicious input penetration', () => {
  describe('URL protocol attacks', () => {
    it('rejects javascript: protocol with encoded characters', () => {
      expect(validatePluginUrl('javascript:alert(1)').safe).toBe(false)
      expect(validatePluginUrl('JavaScript:alert(1)').safe).toBe(false)
      expect(validatePluginUrl('  javascript:alert(1)').safe).toBe(false)
    })

    it('rejects data: protocol with HTML payload', () => {
      expect(
        validatePluginUrl('data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==').safe
      ).toBe(false)
      expect(validatePluginUrl('data:text/html,<script>alert(1)</script>').safe).toBe(false)
    })

    it('rejects vbscript: protocol', () => {
      expect(validatePluginUrl('vbscript:msgbox("xss")').safe).toBe(false)
    })

    it('rejects file: protocol with absolute Windows path', () => {
      expect(validatePluginUrl('file:///C:/Windows/System32/cmd.exe').safe).toBe(false)
      expect(validatePluginUrl('file:///etc/passwd').safe).toBe(false)
    })

    it('rejects protocol-relative URL (//) with various hosts', () => {
      expect(validatePluginUrl('//evil.com/steal.js').safe).toBe(false)
      expect(validatePluginUrl('//localhost:3000/plugin/evil.js').safe).toBe(false)
    })
  })

  describe('path traversal attacks', () => {
    it('rejects ../ traversal', () => {
      expect(validatePluginUrl('/plugin/../../etc/passwd').safe).toBe(false)
      expect(validatePluginUrl('../../../Windows/System32/config').safe).toBe(false)
    })

    it('rejects URL-encoded ../ traversal', () => {
      expect(hasPathTraversal('/plugin/%2e%2e/etc/passwd')).toBe(true)
      expect(hasPathTraversal('/plugin/%2E%2E/etc/passwd')).toBe(true)
      expect(hasPathTraversal('/plugin/%252e%252e/etc/passwd')).toBe(true)
    })

    it('rejects mixed encoding traversal', () => {
      expect(hasPathTraversal('/plugin/.%2e/etc/passwd')).toBe(true)
      expect(hasPathTraversal('/plugin/%2e./etc/passwd')).toBe(true)
      expect(validatePluginUrl('/plugin/.%2e/etc/passwd').safe).toBe(false)
    })

    it('rejects deep traversal with multiple levels', () => {
      expect(validatePluginUrl('/plugin/../../../../../../etc/passwd').safe).toBe(false)
    })
  })

  describe('remote host attacks', () => {
    it('rejects arbitrary external domains', () => {
      expect(validatePluginUrl('https://evil.com/plugin/payload.js').safe).toBe(false)
      expect(validatePluginUrl('https://malware.example.org/plugin/page').safe).toBe(false)
    })

    it('rejects arbitrary public IP addresses', () => {
      expect(validatePluginUrl('https://8.8.8.8/plugin/page').safe).toBe(false)
    })

    it('rejects localhost-like domains that are not actually localhost', () => {
      expect(validatePluginUrl('https://localhost.evil.com/plugin/page').safe).toBe(false)
    })
  })

  describe('entry URL specific attacks', () => {
    it('rejects remote entry scripts', () => {
      expect(validatePluginEntryUrl('https://cdn.evil.com/plugin.js').safe).toBe(false)
    })

    it('allows dev-mode localhost entry scripts', () => {
      expect(validatePluginEntryUrl('http://localhost:5173/plugin/entry.js').safe).toBe(true)
    })

    it('rejects inline script via javascript: protocol', () => {
      expect(validatePluginEntryUrl('javascript:eval("evil")').safe).toBe(false)
    })
  })

  describe('iframe sandbox bypass detection', () => {
    it('detects allow-scripts + allow-same-origin combination', () => {
      expect(isSandboxBypassRisk('allow-scripts allow-same-origin')).toBe(true)
      expect(isSandboxBypassRisk('allow-same-origin allow-scripts allow-forms')).toBe(true)
      expect(isSandboxBypassRisk('allow-scripts allow-same-origin allow-popups')).toBe(true)
    })

    it('passes safe sandbox configurations', () => {
      expect(isSandboxBypassRisk('allow-scripts')).toBe(false)
      expect(isSandboxBypassRisk('allow-scripts allow-forms allow-popups')).toBe(false)
      expect(isSandboxBypassRisk('')).toBe(false)
    })
  })

  describe('null/empty/whitespace attacks', () => {
    it('rejects empty URL', () => {
      expect(validatePluginUrl('').safe).toBe(false)
    })

    it('rejects whitespace-only URL', () => {
      expect(validatePluginUrl('   ').safe).toBe(false)
    })

    it('rejects null byte injection', () => {
      expect(validatePluginUrl('/plugin/index.html\x00.js').safe).toBe(false)
    })
  })

  describe('style URL validation', () => {
    it('rejects remote style URLs', () => {
      expect(validatePluginStyleUrl('https://evil.com/evil.css').safe).toBe(false)
    })

    it('allows local style URLs', () => {
      expect(validatePluginStyleUrl('/plugin/test/style.css').safe).toBe(true)
    })
  })
})

describe('pluginUIManifest - malicious manifest attacks', () => {
  describe('manifest structure attacks', () => {
    it('rejects null input', () => {
      const result = validateManifest(null)
      expect(result.valid).toBe(false)
    })

    it('rejects array input', () => {
      const result = validateManifest([])
      expect(result.valid).toBe(false)
    })

    it('rejects string input', () => {
      const result = validateManifest('malicious string')
      expect(result.valid).toBe(false)
    })

    it('rejects number input', () => {
      const result = validateManifest(42)
      expect(result.valid).toBe(false)
    })
  })

  describe('version attacks', () => {
    it('rejects unsupported schema_version', () => {
      const result = validateManifest({
        schema_version: 999,
        package: 'test',
        name: 'test',
        version: '1.0.0',
      })
      expect(result.valid).toBe(false)
    })

    it('rejects negative schema_version', () => {
      const result = validateManifest({
        schema_version: -1,
        package: 'test',
        name: 'test',
        version: '1.0.0',
      })
      expect(result.valid).toBe(false)
    })
  })

  describe('package name attacks', () => {
    it('rejects empty package name', () => {
      const result = validateManifest({
        schema_version: PLUGIN_UI_MANIFEST_VERSION,
        package: '',
        name: 'test',
        version: '1.0.0',
      })
      expect(result.valid).toBe(false)
    })

    it('rejects whitespace-only package name', () => {
      const result = validateManifest({
        schema_version: PLUGIN_UI_MANIFEST_VERSION,
        package: '   ',
        name: 'test',
        version: '1.0.0',
      })
      expect(result.valid).toBe(false)
    })
  })

  describe('protected CSS token override', () => {
    it('rejects --ant-color-primary override', () => {
      const result = validateManifest({
        schema_version: PLUGIN_UI_MANIFEST_VERSION,
        package: 'test',
        name: 'test',
        version: '1.0.0',
        theme_resources: [
          {
            id: 'malicious',
            label: 'Malicious Theme',
            tokens: { '--ant-color-primary': '#ff0000' },
          },
        ],
      })
      expect(result.valid).toBe(false)
    })

    it('rejects --v6-color-window override', () => {
      const result = validateManifest({
        schema_version: PLUGIN_UI_MANIFEST_VERSION,
        package: 'test',
        name: 'test',
        version: '1.0.0',
        theme_resources: [
          {
            id: 'malicious',
            label: 'Malicious Theme',
            tokens: { '--v6-color-window': '#000' },
          },
        ],
      })
      expect(result.valid).toBe(false)
    })
  })

  describe('element_tag injection', () => {
    it('rejects invalid element_tag without hyphen', () => {
      const result = validateManifest({
        schema_version: PLUGIN_UI_MANIFEST_VERSION,
        package: 'test',
        name: 'test',
        version: '1.0.0',
        pages: [
          {
            id: 'page',
            path: '/page',
            title: 'Page',
            renderer: 'custom-element',
            element_tag: 'NoHyphen',
          },
        ],
      })
      expect(result.valid).toBe(false)
    })

    it('rejects element_tag starting with number', () => {
      const result = validateManifest({
        schema_version: PLUGIN_UI_MANIFEST_VERSION,
        package: 'test',
        name: 'test',
        version: '1.0.0',
        pages: [
          {
            id: 'page',
            path: '/page',
            title: 'Page',
            renderer: 'custom-element',
            element_tag: '1-bad-tag',
          },
        ],
      })
      expect(result.valid).toBe(false)
    })
  })
})
