import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const tokensCssPath = resolve(__dirname, 'v6-tokens.css')
const tokensCss = readFileSync(tokensCssPath, 'utf-8')

const extractCustomProperties = (css: string): Set<string> => {
  const props = new Set<string>()
  const regex = /--v6-[\w-]+(?=\s*:)/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(css)) !== null) {
    props.add(match[0])
  }
  return props
}

describe('v6 Design Tokens contract', () => {
  const tokens = extractCustomProperties(tokensCss)

  describe('required token categories presence', () => {
    const requiredCategories = {
      'color base': ['--v6-color-window', '--v6-color-surface', '--v6-color-surface-elevated'],
      'color text': [
        '--v6-color-text',
        '--v6-color-text-secondary',
        '--v6-color-text-tertiary',
        '--v6-color-text-quaternary',
      ],
      'color semantic': [
        '--v6-color-success',
        '--v6-color-warning',
        '--v6-color-error',
        '--v6-color-info',
      ],
      'color border': ['--v6-color-border', '--v6-color-border-subtle', '--v6-color-border-strong'],
      'color surface variants': [
        '--v6-color-surface-transparent',
        '--v6-color-titlebar',
        '--v6-color-sidebar',
      ],
      'typography size': [
        '--v6-font-size-xs',
        '--v6-font-size-sm',
        '--v6-font-size-base',
        '--v6-font-size-md',
        '--v6-font-size-lg',
        '--v6-font-size-xl',
        '--v6-font-size-2xl',
        '--v6-font-size-3xl',
      ],
      'typography weight': [
        '--v6-font-weight-normal',
        '--v6-font-weight-medium',
        '--v6-font-weight-semibold',
        '--v6-font-weight-bold',
      ],
      'typography line height': [
        '--v6-line-height-tight',
        '--v6-line-height-normal',
        '--v6-line-height-relaxed',
      ],
      'spacing scale': [
        '--v6-space-0',
        '--v6-space-1',
        '--v6-space-2',
        '--v6-space-3',
        '--v6-space-4',
        '--v6-space-5',
        '--v6-space-6',
        '--v6-space-8',
        '--v6-space-10',
        '--v6-space-12',
      ],
      'radius scale': [
        '--v6-radius-xs',
        '--v6-radius-sm',
        '--v6-radius-control',
        '--v6-radius-md',
        '--v6-radius-card',
        '--v6-radius-lg',
        '--v6-radius-xl',
        '--v6-radius-full',
      ],
      'shadow scale': [
        '--v6-shadow-xs',
        '--v6-shadow-sm',
        '--v6-shadow-card',
        '--v6-shadow-md',
        '--v6-shadow-lg',
        '--v6-shadow-elevated',
        '--v6-shadow-popover',
      ],
      'focus ring': ['--v6-focus-ring', '--v6-shadow-focus-ring'],
      'motion duration': ['--v6-motion-fast', '--v6-motion-base', '--v6-motion-slow'],
      'motion easing': ['--v6-ease-linear', '--v6-ease-in', '--v6-ease-out', '--v6-ease-in-out'],
      'z-index layers': [
        '--v6-z-background',
        '--v6-z-base',
        '--v6-z-content',
        '--v6-z-sidebar',
        '--v6-z-titlebar',
        '--v6-z-dropdown',
        '--v6-z-modal-backdrop',
        '--v6-z-modal',
        '--v6-z-tooltip',
        '--v6-z-toast',
      ],
      'sidebar layout': [
        '--v6-sidebar-width',
        '--v6-sidebar-width-collapsed',
        '--v6-sidebar-nav-icon-size',
      ],
      'titlebar layout': ['--v6-titlebar-height'],
    }

    for (const [category, requiredTokens] of Object.entries(requiredCategories)) {
      it(`exposes all ${category} tokens`, () => {
        for (const token of requiredTokens) {
          expect(tokens.has(token), `Missing token: ${token}`).toBe(true)
        }
      })
    }
  })

  describe('light and dark theme definitions', () => {
    it('defines :root (light) theme variables', () => {
      expect(tokensCss).toContain(':root')
      expect(tokensCss).toContain('--v6-color-window:')
      expect(tokensCss).toContain('--v6-color-text:')
    })

    it('defines dark theme variables', () => {
      expect(tokensCss).toContain('.dark')
    })

    it('defines [data-perf-mode] low-performance overrides', () => {
      expect(tokensCss).toContain('data-perf-mode')
    })
  })

  describe('prefers-reduced-motion support', () => {
    it('includes prefers-reduced-motion media query', () => {
      expect(tokensCss).toContain('prefers-reduced-motion')
      expect(tokensCss).toContain('reduce')
    })
  })

  describe('token value sanity', () => {
    it('defines base spacing as 4px scaled grid', () => {
      expect(tokensCss).toContain('--v6-space-1:')
      expect(tokensCss).toContain('4px')
      expect(tokensCss).toContain('--v6-space-2:')
    })

    it('defines z-index in correct ascending order', () => {
      const zIndexRegex = /--v6-z-([\w-]+):\s*(-?\d+)/g
      const zIndices: Record<string, number> = {}
      let match: RegExpExecArray | null
      while ((match = zIndexRegex.exec(tokensCss)) !== null) {
        zIndices[match[1]] = parseInt(match[2], 10)
      }
      expect(zIndices['background']).toBeLessThan(zIndices['base'])
      expect(zIndices['base']).toBeLessThan(zIndices['sidebar'])
      expect(zIndices['sidebar']).toBeLessThan(zIndices['titlebar'])
      expect(zIndices['dropdown']).toBeLessThan(zIndices['modal-backdrop'])
      expect(zIndices['modal-backdrop']).toBeLessThan(zIndices['modal'])
      expect(zIndices['tooltip']).toBeGreaterThan(zIndices['modal'])
    })
  })

  describe('vibrancy/backdrop tokens', () => {
    it('defines vibrancy variables for both themes', () => {
      const vibrancyTokens = [
        '--v6-vibrancy-sidebar',
        '--v6-vibrancy-titlebar',
        '--v6-vibrancy-toolbar',
        '--v6-vibrancy-content',
        '--v6-vibrancy-popover',
        '--v6-vibrancy-hover',
        '--v6-vibrancy-selected',
      ]
      for (const token of vibrancyTokens) {
        expect(tokens.has(token), `Missing vibrancy token: ${token}`).toBe(true)
      }
    })

    it('defines backdrop filter tokens', () => {
      expect(tokens.has('--v6-backdrop-shell')).toBe(true)
      expect(tokens.has('--v6-backdrop-vibrancy')).toBe(true)
      expect(tokens.has('--v6-backdrop-popover')).toBe(true)
    })
  })

  describe('accessibility tokens', () => {
    it('defines focus ring tokens', () => {
      expect(tokens.has('--v6-focus-ring')).toBe(true)
      expect(tokens.has('--v6-focus-ring-width')).toBe(true)
      expect(tokens.has('--v6-focus-ring-offset')).toBe(true)
    })

    it('defines disabled text color', () => {
      expect(tokens.has('--v6-color-text-disabled')).toBe(true)
    })
  })
})
