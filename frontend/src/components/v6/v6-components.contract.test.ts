import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentDir = __dirname

const readComponent = (name: string): string => {
  return readFileSync(resolve(componentDir, name), 'utf-8')
}

const containsPerfMode = (source: string): boolean =>
  source.includes("[data-perf-mode='low']") || source.includes('[data-perf-mode="low"]')

describe('v6 common components design token contract', () => {
  describe('LoadingSkeleton.vue', () => {
    const source = readComponent('LoadingSkeleton.vue')

    it('uses v6 CSS variables exclusively for styling', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-space-')
      expect(source).toContain('--v6-radius-')
      expect(source).toContain('--v6-color-')
    })

    it('supports multiple variants (default/list/card/form)', () => {
      expect(source).toContain("'default'")
      expect(source).toContain("'list'")
      expect(source).toContain("'card'")
      expect(source).toContain("'form'")
    })

    it('includes ARIA accessibility attributes', () => {
      expect(source).toContain('aria-busy')
      expect(source).toContain('aria-label')
      expect(source).toContain('role="status"')
      expect(source).toContain('aria-live')
    })

    it('handles low-performance mode by disabling animations', () => {
      expect(containsPerfMode(source)).toBe(true)
    })

    it('respects prefers-reduced-motion', () => {
      expect(source).toContain('prefers-reduced-motion')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })
  })

  describe('EmptyState.vue', () => {
    const source = readComponent('EmptyState.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-color-')
      expect(source).toContain('--v6-space-')
    })

    it('supports icon and action slots', () => {
      expect(source).toContain('name="icon"')
      expect(source).toContain('name="action"')
    })

    it('has compact mode prop', () => {
      expect(source).toContain('compact')
    })

    it('includes accessible label', () => {
      expect(source).toContain('role=')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })
  })

  describe('ErrorState.vue', () => {
    const source = readComponent('ErrorState.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-color-error')
    })

    it('supports error details expansion', () => {
      expect(source).toContain('details')
      expect(source).toContain('aria-expanded')
      expect(source).toContain('aria-controls')
    })

    it('has copy error functionality via navigator.clipboard or execCommand fallback', () => {
      expect(source).toContain('copyError')
      expect(source).toMatch(/clipboard/i)
    })

    it('supports fullscreen mode', () => {
      expect(source).toContain('fullscreen')
    })

    it('handles low-performance mode', () => {
      expect(containsPerfMode(source)).toBe(true)
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })
  })

  describe('OfflineSkeleton.vue', () => {
    const source = readComponent('OfflineSkeleton.vue')

    it('uses v6 design tokens with warning colors', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-color-warning')
    })

    it('supports compact mode', () => {
      expect(source).toContain('compact')
    })

    it('has reconnect countdown', () => {
      expect(source).toContain('reconnect')
      expect(source).toContain('countdown')
    })

    it('emits reconnect event', () => {
      expect(source).toContain('defineEmits')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })
  })

  describe('StatusBadge.vue', () => {
    const source = readComponent('StatusBadge.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-radius-')
    })

    it('supports multiple status types including default/idle', () => {
      expect(source).toContain("'default'")
      expect(source).toContain("'idle'")
      expect(source).toContain("'success'")
      expect(source).toContain("'warning'")
      expect(source).toContain("'error'")
      expect(source).toContain("'info'")
    })

    it('supports size prop', () => {
      expect(source).toContain('size')
      expect(source).toContain("'small'")
      expect(source).toContain("'middle'")
      expect(source).toContain("'large'")
    })

    it('supports dot display options', () => {
      expect(source).toContain('dot')
      expect(source).toContain('dotOnly')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })
  })

  describe('FocusRing.vue', () => {
    const source = readComponent('FocusRing.vue')

    it('uses v6 focus ring tokens', () => {
      expect(source).toContain('--v6-focus-ring')
    })

    it('supports keyboard-only focus detection', () => {
      expect(source).toContain('keyboardOnly')
    })

    it('supports inset mode', () => {
      expect(source).toContain('inset')
    })

    it('respects disabled state', () => {
      expect(source).toContain('disabled')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })
  })
})

describe('v6 components TypeScript setup', () => {
  const components = [
    'LoadingSkeleton.vue',
    'EmptyState.vue',
    'ErrorState.vue',
    'OfflineSkeleton.vue',
    'StatusBadge.vue',
    'FocusRing.vue',
  ]

  for (const comp of components) {
    it(`${comp} uses <script setup lang="ts">`, () => {
      const source = readComponent(comp)
      expect(source).toContain('<script setup lang="ts">')
    })
  }
})
