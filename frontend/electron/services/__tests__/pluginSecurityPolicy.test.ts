import { describe, expect, it } from 'vitest'

import {
  isSafeIframeSandbox,
  isSafePluginUrl,
  hasDangerousScriptInjection,
  validatePluginContent,
} from '../pluginSecurityPolicy'

describe('plugin iframe sandbox policy', () => {
  it('accepts empty or default sandbox attribute', () => {
    expect(isSafeIframeSandbox('')).toBe(true)
    expect(isSafeIframeSandbox('  ')).toBe(true)
  })

  it('rejects allow-scripts + allow-same-origin combination', () => {
    expect(isSafeIframeSandbox('allow-scripts allow-same-origin')).toBe(false)
    expect(isSafeIframeSandbox('allow-same-origin allow-scripts')).toBe(false)
  })

  it('accepts allow-scripts alone', () => {
    expect(isSafeIframeSandbox('allow-scripts')).toBe(true)
  })

  it('accepts allow-same-origin alone', () => {
    expect(isSafeIframeSandbox('allow-same-origin')).toBe(true)
  })

  it('accepts allow-forms and allow-popups', () => {
    expect(isSafeIframeSandbox('allow-forms allow-popups')).toBe(true)
  })

  it('rejects unknown sandbox tokens', () => {
    expect(isSafeIframeSandbox('allow-top-navigation')).toBe(false)
  })
})

describe('plugin URL safety', () => {
  it('rejects javascript: and data: schemes', () => {
    const packaged = true
    expect(isSafePluginUrl('javascript:alert(1)', packaged).safe).toBe(false)
    expect(isSafePluginUrl('data:text/html,<script>alert(1)</script>', packaged).safe).toBe(false)
  })

  it('rejects remote HTTP URLs in production', () => {
    const packaged = true
    expect(isSafePluginUrl('https://evil.example/plugin', packaged).safe).toBe(false)
    expect(isSafePluginUrl('http://attacker.com/payload', packaged).safe).toBe(false)
  })

  it('allows localhost HTTP in development', () => {
    const packaged = false
    expect(isSafePluginUrl('http://127.0.0.1:5173/plugin-page', packaged).safe).toBe(true)
    expect(isSafePluginUrl('http://localhost:3000/plugin', packaged).safe).toBe(true)
  })

  it('rejects non-localhost HTTP in development', () => {
    const packaged = false
    expect(isSafePluginUrl('http://192.168.1.1:8080/plugin', packaged).safe).toBe(false)
  })

  it('rejects file: protocol without configured roots', () => {
    const packaged = true
    expect(isSafePluginUrl('file:///C:/some/plugin/index.html', packaged).safe).toBe(false)
  })

  it('rejects malformed URLs', () => {
    const packaged = true
    expect(isSafePluginUrl('not-a-url', packaged).safe).toBe(false)
    expect(isSafePluginUrl('', packaged).safe).toBe(false)
  })
})

describe('dangerous script injection detection', () => {
  it('detects script tags', () => {
    expect(hasDangerousScriptInjection('<script>alert(1)</script>')).toBe(true)
    expect(hasDangerousScriptInjection('<script src="evil.js">')).toBe(true)
  })

  it('detects inline event handlers', () => {
    expect(hasDangerousScriptInjection('<div onclick="alert(1)">')).toBe(true)
    expect(hasDangerousScriptInjection('<body onload="init()">')).toBe(true)
  })

  it('detects javascript: protocol', () => {
    expect(hasDangerousScriptInjection('<a href="javascript:void(0)">')).toBe(true)
  })

  it('detects iframe/object/embed tags', () => {
    expect(hasDangerousScriptInjection('<iframe src="evil.html">')).toBe(true)
    expect(hasDangerousScriptInjection('<object data="evil.swf">')).toBe(true)
    expect(hasDangerousScriptInjection('<embed src="evil.swf">')).toBe(true)
  })

  it('accepts safe HTML content', () => {
    expect(hasDangerousScriptInjection('<div>Hello World</div>')).toBe(false)
    expect(hasDangerousScriptInjection('<p>Safe content</p>')).toBe(false)
  })
})

describe('validatePluginContent', () => {
  it('reports url and injection violations together', () => {
    const result = validatePluginContent('<script>alert(1)</script>', 'javascript:void(0)', true)
    expect(result.safe).toBe(false)
    expect(result.violations.length).toBe(2)
    expect(result.violations.some(v => v.rule === 'plugin_url_scheme')).toBe(true)
    expect(result.violations.some(v => v.rule === 'dangerous_script_injection')).toBe(true)
  })

  it('passes safe content', () => {
    const result = validatePluginContent('<div>Safe</div>', 'http://127.0.0.1:5173/plugin', false)
    expect(result.safe).toBe(true)
    expect(result.violations.length).toBe(0)
  })
})
