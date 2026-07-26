import { describe, expect, it } from 'vitest'
import {
  PLUGIN_UI_MANIFEST_VERSION,
  validateManifest,
  isManifestVersionSupported,
  getSupportedManifestVersion,
  type PluginUIManifest,
} from '../pluginUIManifest'

function makeManifest(overrides: Partial<PluginUIManifest> = {}): PluginUIManifest {
  return {
    schema_version: PLUGIN_UI_MANIFEST_VERSION,
    package: 'test-plugin',
    name: 'Test Plugin',
    version: '1.0.0',
    ...overrides,
  }
}

describe('pluginUIManifest', () => {
  describe('validateManifest', () => {
    it('validates a minimal valid manifest', () => {
      const result = validateManifest(makeManifest())
      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('rejects non-object input', () => {
      const result = validateManifest(null)
      expect(result.valid).toBe(false)
      expect(result.errors).toHaveLength(1)
      expect(result.errors[0].field).toBe('$')
      expect(result.errors[0].message).toContain('对象')
    })

    it('rejects missing schema_version', () => {
      const result = validateManifest({ package: 'x', name: 'x', version: '1.0.0' })
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.field === 'schema_version')).toBe(true)
    })

    it('rejects unsupported schema_version', () => {
      const result = validateManifest(makeManifest({ schema_version: 999 as never }))
      expect(result.valid).toBe(false)
      expect(
        result.errors.some(e => e.field === 'schema_version' && e.message.includes('支持'))
      ).toBe(true)
    })

    it('rejects empty package', () => {
      const result = validateManifest(makeManifest({ package: '' }))
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.field === 'package')).toBe(true)
    })

    it('rejects empty name', () => {
      const result = validateManifest(makeManifest({ name: '' }))
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.field === 'name')).toBe(true)
    })

    it('rejects invalid semver', () => {
      const result = validateManifest(makeManifest({ version: 'not-semver' }))
      expect(result.valid).toBe(false)
      expect(
        result.errors.some(e => e.field === 'version' && e.message.includes('语义化版本'))
      ).toBe(true)
    })

    it('accepts pre-release semver', () => {
      const result = validateManifest(makeManifest({ version: '2.0.0-alpha.1' }))
      expect(result.valid).toBe(true)
    })

    it('accepts build metadata semver', () => {
      const result = validateManifest(makeManifest({ version: '1.0.0+build.20260724' }))
      expect(result.valid).toBe(true)
    })

    describe('pages validation', () => {
      it('validates valid pages', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main-page',
                path: '/main',
                title: 'Main Page',
                renderer: 'iframe',
                url: '/plugin/test/main',
              },
            ],
          })
        )
        expect(result.valid).toBe(true)
      })

      it('rejects page missing id', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: '',
                path: '/main',
                title: 'Main',
                renderer: 'iframe',
              } as never,
            ],
          })
        )
        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.field === 'pages[0].id')).toBe(true)
      })

      it('rejects page missing path', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main',
                path: '',
                title: 'Main',
                renderer: 'iframe',
              } as never,
            ],
          })
        )
        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.field === 'pages[0].path')).toBe(true)
      })

      it('rejects page missing title', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main',
                path: '/main',
                title: '',
                renderer: 'iframe',
              } as never,
            ],
          })
        )
        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.field === 'pages[0].title')).toBe(true)
      })

      it('rejects invalid renderer', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main',
                path: '/main',
                title: 'Main',
                renderer: 'unknown',
              } as never,
            ],
          })
        )
        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.field === 'pages[0].renderer')).toBe(true)
      })

      it('rejects invalid element_tag format', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main',
                path: '/main',
                title: 'Main',
                renderer: 'custom-element',
                element_tag: 'NoHyphen',
              },
            ],
          })
        )
        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.field === 'pages[0].element_tag')).toBe(true)
      })

      it('accepts valid element_tag with hyphen', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main',
                path: '/main',
                title: 'Main',
                renderer: 'custom-element',
                element_tag: 'my-plugin-main',
              },
            ],
          })
        )
        expect(result.valid).toBe(true)
      })

      it('warns about unknown fields in pages', () => {
        const result = validateManifest(
          makeManifest({
            pages: [
              {
                id: 'main',
                path: '/main',
                title: 'Main',
                renderer: 'iframe',
                evil_hook: 'dangerous',
              } as never,
            ],
          })
        )
        expect(result.valid).toBe(true)
        expect(result.warnings.some(w => w.field === 'pages[0].evil_hook')).toBe(true)
      })
    })

    describe('theme_resources validation', () => {
      it('rejects protected CSS token override', () => {
        const result = validateManifest(
          makeManifest({
            theme_resources: [
              {
                id: 'theme',
                label: 'Custom Theme',
                tokens: {
                  '--ant-color-primary': '#ff0000',
                },
              },
            ],
          })
        )
        expect(result.valid).toBe(false)
        expect(
          result.errors.some(e => e.field === 'theme_resources[0].tokens.--ant-color-primary')
        ).toBe(true)
      })

      it('rejects --v6- prefix override', () => {
        const result = validateManifest(
          makeManifest({
            theme_resources: [
              {
                id: 'theme',
                label: 'Custom Theme',
                tokens: {
                  '--v6-color-window': '#000',
                },
              },
            ],
          })
        )
        expect(result.valid).toBe(false)
      })

      it('rejects --app-background override', () => {
        const result = validateManifest(
          makeManifest({
            theme_resources: [
              {
                id: 'theme',
                label: 'Custom Theme',
                tokens: {
                  '--app-background': 'url(...)',
                },
              },
            ],
          })
        )
        expect(result.valid).toBe(false)
      })

      it('allows custom plugin tokens', () => {
        const result = validateManifest(
          makeManifest({
            theme_resources: [
              {
                id: 'theme',
                label: 'Custom Theme',
                tokens: {
                  '--plugin-accent': '#ff6600',
                  '--plugin-spacing': '16px',
                },
              },
            ],
          })
        )
        expect(result.valid).toBe(true)
      })
    })

    describe('settings validation', () => {
      it('rejects settings that is not an array', () => {
        const result = validateManifest(makeManifest({ settings: 'not-array' as never }))
        expect(result.valid).toBe(false)
        expect(result.errors.some(e => e.field === 'settings')).toBe(true)
      })
    })
  })

  describe('isManifestVersionSupported', () => {
    it('returns true for current version', () => {
      expect(isManifestVersionSupported(PLUGIN_UI_MANIFEST_VERSION)).toBe(true)
    })

    it('returns false for unknown version', () => {
      expect(isManifestVersionSupported(999)).toBe(false)
    })
  })

  describe('getSupportedManifestVersion', () => {
    it('returns current version', () => {
      expect(getSupportedManifestVersion()).toBe(PLUGIN_UI_MANIFEST_VERSION)
    })
  })
})
