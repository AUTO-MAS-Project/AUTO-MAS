import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')

describe('工具页 macOS 外壳契约', () => {
  it('使用单层分段导航并保持两个工具面板挂载', () => {
    expect(source).toContain('<a-segmented')
    expect(source).not.toContain('type="card"')
    expect(source).toContain('v-show="activeKey === \'arknightspc\'"')
    expect(source).toContain('v-show="activeKey === \'gamesign\'"')
  })

  it('使用共享磨砂 token 并为低性能模式降级', () => {
    expect(source).toContain('var(--v6-color-surface)')
    expect(source).toContain('var(--v6-color-border-subtle)')
    expect(source).toContain('var(--v6-backdrop-vibrancy)')
    expect(source).toContain("data-perf-mode='low'")
    expect(source).toContain('prefers-reduced-motion')
  })
})
