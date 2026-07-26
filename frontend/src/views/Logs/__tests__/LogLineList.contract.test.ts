import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, '../components/LogLineList.vue'), 'utf-8')

describe('LogLineList component contract', () => {
  it('uses script setup lang="ts"', () => {
    expect(source).toContain('<script setup lang="ts">')
  })

  it('declares virtual scrolling props (lines, lineHeight, keyword, paused, autoScroll)', () => {
    expect(source).toContain('lines: string[]')
    expect(source).toContain('lineHeight?: number')
    expect(source).toContain('keyword?: string')
    expect(source).toContain('paused?: boolean')
    expect(source).toContain('autoScroll?: boolean')
  })

  it('renders a viewport with translateY for virtualization', () => {
    expect(source).toContain('log-line-list__viewport')
    expect(source).toContain('translateY')
    expect(source).toContain('groupOffset')
  })

  it('escapes HTML before applying highlights', () => {
    expect(source).toContain('escapeHtml')
    expect(source).toContain('&amp;')
    expect(source).toContain('&lt;')
    expect(source).toContain('&gt;')
  })

  it('highlights timestamps, log levels and keywords', () => {
    expect(source).toContain('TIMESTAMP_RE')
    expect(source).toContain('LEVEL_RE')
    expect(source).toContain('log-line__token--timestamp')
    expect(source).toContain('log-line__token--level')
    expect(source).toContain('log-line__keyword')
  })

  it('exposes scroll controls for parent components', () => {
    expect(source).toContain('scrollToBottom')
    expect(source).toContain('scrollToTop')
    expect(source).toContain('defineExpose')
  })

  it('respects reduced motion and low performance mode', () => {
    expect(source).toContain('prefers-reduced-motion')
    expect(source).toContain("[data-perf-mode='low']")
  })

  it('uses v6 design tokens exclusively', () => {
    expect(source).toContain('var(--v6-')
    expect(source).toContain('--v6-color-')
    expect(source).toContain('--v6-font-mono')
  })

  it('uses scoped styles', () => {
    expect(source).toContain('<style scoped>')
  })
})
