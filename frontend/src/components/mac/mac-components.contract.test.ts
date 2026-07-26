import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentDir = __dirname

const readComponent = (name: string): string => {
  return readFileSync(resolve(componentDir, name), 'utf-8')
}

const containsPerfMode = (source: string): boolean =>
  source.includes("[data-perf-mode='low']") || source.includes('[data-perf-mode="low"]')

describe('macOS-style layout components contract', () => {
  describe('PageHeader.vue', () => {
    const source = readComponent('PageHeader.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-color-')
    })

    it('supports title and subtitle props', () => {
      expect(source).toContain('title')
      expect(source).toContain('subtitle')
    })

    it('supports bordered, transparent, compact modes', () => {
      expect(source).toContain('bordered')
      expect(source).toContain('transparent')
      expect(source).toContain('compact')
    })

    it('provides title, subtitle, actions slots', () => {
      expect(source).toContain('name="title"')
      expect(source).toContain('name="subtitle"')
      expect(source).toContain('name="actions"')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })

    it('uses TypeScript script setup', () => {
      expect(source).toContain('<script setup lang="ts">')
    })
  })

  describe('Section.vue', () => {
    const source = readComponent('Section.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-radius-')
    })

    it('supports collapsible mode with chevron indicator', () => {
      expect(source).toContain('collapsible')
      expect(source).toContain('defaultCollapsed')
    })

    it('emits update:collapsed for v-model', () => {
      expect(source).toContain('update:collapsed')
    })

    it('supports bordered, rounded, padding options', () => {
      expect(source).toContain('bordered')
      expect(source).toContain('rounded')
      expect(source).toContain('padding')
    })

    it('provides header, actions, footer slots', () => {
      expect(source).toContain('name="header"')
      expect(source).toContain('name="actions"')
      expect(source).toContain('name="footer"')
    })

    it('includes ARIA expanded state for collapsible sections', () => {
      expect(source).toContain('aria-expanded')
      expect(source).toContain('aria-controls')
    })

    it('respects prefers-reduced-motion for collapse animation', () => {
      expect(source).toContain('prefers-reduced-motion')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })

    it('uses TypeScript script setup', () => {
      expect(source).toContain('<script setup lang="ts">')
    })
  })

  describe('Toolbar.vue', () => {
    const source = readComponent('Toolbar.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-space-')
    })

    it('supports compact mode', () => {
      expect(source).toContain('compact')
    })

    it('supports configurable border position (top/bottom/both/none)', () => {
      expect(source).toContain('position')
      expect(source).toContain("'top'")
      expect(source).toContain("'bottom'")
      expect(source).toContain("'both'")
      expect(source).toContain("'none'")
    })

    it('provides leading and trailing slots', () => {
      expect(source).toContain('name="leading"')
      expect(source).toContain('name="trailing"')
    })

    it('supports transparency/vibrancy', () => {
      expect(source).toContain('transparent')
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })

    it('uses TypeScript script setup', () => {
      expect(source).toContain('<script setup lang="ts">')
    })
  })

  describe('StatePanel.vue', () => {
    const source = readComponent('StatePanel.vue')

    it('uses v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
      expect(source).toContain('--v6-color-')
    })

    it('supports five status types (info/success/warning/error/neutral)', () => {
      expect(source).toContain("'info'")
      expect(source).toContain("'success'")
      expect(source).toContain("'warning'")
      expect(source).toContain("'error'")
      expect(source).toContain("'neutral'")
    })

    it('has colored status indicator', () => {
      expect(source).toMatch(/indicator|status-bar|border/)
    })

    it('supports closable mode with close button', () => {
      expect(source).toContain('closable')
      expect(source).toContain("'close'")
    })

    it('provides icon, title, actions slots', () => {
      expect(source).toContain('name="icon"')
      expect(source).toContain('name="title"')
      expect(source).toContain('name="actions"')
    })

    it('supports compact mode', () => {
      expect(source).toContain('compact')
    })

    it('handles low-performance mode or respects reduced motion', () => {
      expect(containsPerfMode(source) || source.includes('prefers-reduced-motion')).toBe(true)
    })

    it('uses scoped styles', () => {
      expect(source).toContain('<style scoped>')
    })

    it('uses TypeScript script setup', () => {
      expect(source).toContain('<script setup lang="ts">')
    })
  })
})

describe('mac components design token compliance', () => {
  const macComponents = ['PageHeader.vue', 'Section.vue', 'Toolbar.vue', 'StatePanel.vue']

  for (const comp of macComponents) {
    it(`${comp} uses <script setup lang="ts"> and scoped styles`, () => {
      const source = readComponent(comp)
      expect(source).toContain('<script setup lang="ts">')
      expect(source).toContain('<style scoped>')
    })
  }
})
