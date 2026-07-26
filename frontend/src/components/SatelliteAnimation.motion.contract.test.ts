import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  fileURLToPath(new URL('./SatelliteAnimation.vue', import.meta.url)),
  'utf8'
)

describe('SatelliteAnimation motion contract', () => {
  it('keeps the satellite scene mounted while respecting low-performance and reduced-motion modes', () => {
    expect(source).toContain("from '@/composables/useLowPerfMode'")
    expect(source).toContain("window.matchMedia('(prefers-reduced-motion: reduce)')")
    expect(source).toContain('const motionAllowed = computed')
    expect(source).toContain('revealCardsImmediately()')
    expect(source).toContain(
      'animationFrameId = motionAllowed.value ? requestAnimationFrame(animate) : null'
    )
  })

  it('removes the media-query listener and animation frames during teardown', () => {
    expect(source).toContain("removeEventListener?.('change', syncReducedMotion)")
    expect(source).toContain('cancelAnimationFrame(animationFrameId)')
    expect(source).toContain('cancelAnimationFrame(appearAnimationFrameId)')
  })

  // 自适应契约：轨道半径/画布尺寸随容器推导，禁止回退到固定像素方案
  it('derives orbit radii and canvas size from the container instead of fixed pixels', () => {
    // 不允许再出现固定容器高度/固定轨道半径常量
    expect(source).not.toContain('containerHeight')
    expect(source).not.toContain('height: 400px')
    expect(source).not.toMatch(/orbitRadiusX:\s*\d/)
    expect(source).not.toMatch(/orbitRadiusY:\s*\d/)

    // 布局由容器尺寸计算：轨道、卡片比例、浮动幅度均来自 layout
    expect(source).toContain('function computeLayout(')
    expect(source).toContain('layout = computeLayout(')
    expect(source).toContain('Math.cos(angle) * layout.orbitRadiusX')
    expect(source).toContain('Math.sin(angle) * layout.orbitRadiusY')
    expect(source).toContain('layout.cardScale')

    // 容器高度跟随卡片（flex），resize 经 ResizeObserver（含 window 回退）驱动
    expect(source).toContain('flex: 1 1 auto')
    expect(source).toContain('new ResizeObserver(() => handleResize())')
    expect(source).toContain("window.addEventListener('resize', handleResize)")
  })

  it('rescales the scene on resize while keeping the low-performance render path', () => {
    // resize 后同步轨道椭圆与卡片比例；低性能模式下手动补一帧渲染
    expect(source).toContain('orbitLine?.scale.set(layout.orbitRadiusX, layout.orbitRadiusY, 1)')
    expect(source).toContain('if (cardsRevealed) revealCardsImmediately()')
    expect(source).toContain('if (!motionAllowed.value) animate()')
  })
})
