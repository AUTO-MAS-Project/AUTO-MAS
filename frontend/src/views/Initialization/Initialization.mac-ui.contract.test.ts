import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')
const stepPanelSource = readFileSync(new URL('./components/StepPanel.vue', import.meta.url), 'utf8')
const backendStepSource = readFileSync(
  new URL('./components/BackendStartStep.vue', import.meta.url),
  'utf8'
)

describe('Initialization mac UI contract', () => {
  it('uses the shared mac page primitives', () => {
    expect(source).toContain("import MacPageHeader from '@/components/mac/PageHeader.vue'")
    expect(source).toContain("import MacSection from '@/components/mac/Section.vue'")
    expect(source).toContain("import MacStatePanel from '@/components/mac/StatePanel.vue'")
    expect(source).toContain('<MacPageHeader')
    expect(source).toContain('<MacSection')
    expect(source).toContain('<MacStatePanel')
  })

  it('keeps the real seven-stage initialization flow', () => {
    for (const key of [
      'python',
      'pip',
      'git',
      'repository',
      'dependency',
      'plugin-bootstrap',
      'backend',
    ]) {
      expect(source).toContain(`key: '${key}'`)
    }
    expect(source).toContain('startInitialization(startFromIndex)')
  })

  it('keeps all stages visible and separates execution from history browsing', () => {
    expect(source).toContain('class="stage-rail"')
    expect(source).toContain('v-for="(step, index) in steps"')
    expect(source).toContain('const viewedStepIndex = ref(0)')
    expect(source).toContain('const isViewingHistory = computed')
    expect(source).toContain('function selectViewedStep(index: number)')
    expect(source).toContain('function setCurrentStep(index: number)')
    expect(source).toContain('v-if="isViewingHistory"')
    expect(source).toContain('返回当前阶段')
    expect(source).not.toMatch(/currentStepIndex\.value\s*=\s*i(?:\s|$)/)
  })

  it('keeps mirror selection, retry, skip and backend completion events wired', () => {
    expect(source).toContain('@update:selected-mirror="handleMirrorSelect"')
    expect(source).toContain('@retry="handleRetry"')
    expect(source).toContain('@skip="handleSkip"')
    expect(source).toContain('@complete="handleBackendComplete"')
    expect(source).toContain('@error="handleBackendError"')
    expect(source).toContain('@update:status="handleBackendStatus"')
  })

  it('keeps skip boundaries explicit and force entry behind confirmation', () => {
    expect(source).toContain("{ key: 'repository', title: '源码拉取', canSkip: true }")
    expect(source).toContain("{ key: 'dependency', title: '依赖安装', canSkip: true }")
    expect(source).toContain("{ key: 'backend', title: '后端启动', canSkip: true }")
    expect(source).toContain("{ key: 'plugin-bootstrap', title: '插件安装', canSkip: false }")
    expect(source).toContain('v-model:open="forceEnterVisible"')
    expect(source).toContain('@ok="handleForceEnterConfirm"')
  })

  it('preserves production IPC operations and progress listeners', () => {
    for (const operation of [
      'installPython',
      'installPip',
      'installGit',
      'pullRepository',
      'installDependencies',
      'installPluginBootstrap',
      'onBackendStatus',
    ]) {
      expect(source).toContain(`.${operation}`)
    }
  })

  it('uses v6 tokens instead of creating page-specific colors', () => {
    expect(source).toContain('var(--v6-color-window)')
    expect(source).toContain('var(--v6-content-padding-inline)')
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(source).not.toContain('var(--ant-color-')
  })

  // 2026-07 真机反馈：整页蓝→紫高饱和渐变废弃，改为 macOS 风格中性背景。
  // 页面背景 = 窗口灰 token + 极轻的顶部到底部明度渐变；hero 文字随主题（浅色深字/深色浅字）。
  it('uses a neutral macOS-style background with theme-following hero text', () => {
    expect(source).toContain('background-color: var(--v6-color-window)')
    expect(source).toMatch(
      /\.initialization-page\s*\{[^}]*linear-gradient\(\s*180deg,\s*color-mix\(in srgb, var\(--v6-color-surface\)/s
    )
    expect(source).not.toContain('radial-gradient')
    expect(source).not.toContain('135deg')
    expect(source).not.toContain('color: rgb(255 255 255 / 94%)')
    expect(source).not.toContain('rgb(71 190 255')
    expect(source).not.toContain('rgb(217 96 189')
    expect(source).toMatch(/\.initialization-brand h1\s*\{[^}]*color: var\(--v6-color-text\)/s)
    expect(source).toMatch(
      /\.initialization-subtitle\s*\{[^}]*color: var\(--v6-color-text-secondary\)/s
    )
    expect(source).not.toContain('color: var(--v6-color-text-inverse)')
    expect(source).not.toContain('color: rgb(32 33 36 / 62%)')
    expect(source).toMatch(/\.stage-heading p\s*\{[^}]*color: var\(--v6-color-text-secondary\)/s)
    expect(source).toContain('@media (max-width: 900px)')
  })

  // 卡片在中性背景上的层级：token 表面 + 发丝线边框 + token 阴影，不再用毛玻璃透明表面。
  it('keeps cards on token surfaces with hairline borders and token shadows', () => {
    expect(source).toMatch(
      /\.stage-rail\s*\{[^}]*border: 1px solid var\(--v6-color-border\)[^}]*background: var\(--v6-color-surface\)[^}]*box-shadow: var\(--v6-shadow-card\)/s
    )
    expect(source).toMatch(
      /\.init-stage-card\s*\{[^}]*border: 1px solid var\(--v6-color-border\)[^}]*background: var\(--v6-color-surface\)[^}]*box-shadow: var\(--v6-shadow-md\)/s
    )
    expect(source).not.toContain('backdrop-filter')
    expect(source).not.toContain('rgb(12 22 80')
    expect(source).not.toContain('rgb(4 26 97')
  })

  // 2026-07 追加：阶段指示改为顶部横向 stepper（标题区之下、内容卡之上），窄屏横向滚动。
  it('places the stage stepper above the content card as a horizontal rail', () => {
    expect(source.indexOf('class="stage-rail"')).toBeGreaterThan(-1)
    expect(source.indexOf('class="stage-rail"')).toBeLessThan(source.indexOf('init-stage-card'))
    expect(source).toMatch(/\.initialization-content\s*\{[^}]*flex-direction: column/s)
    expect(source).not.toContain('grid-template-columns: 230px')
    expect(source).toMatch(
      /\.stage-list\s*\{[^}]*flex-direction: row[^}]*overflow-x: auto[^}]*scroll-snap-type: x proximity/s
    )
    expect(source).toMatch(/\.stage-list li\s*\{[^}]*min-width: 140px/s)
  })

  it('keeps the nested step content quiet and avoids duplicate card/title chrome', () => {
    expect(stepPanelSource).not.toContain('<h3>{{ title }}</h3>')
    expect(backendStepSource).not.toContain('<h3>启动应用</h3>')
    expect(backendStepSource).not.toContain('<a-card')
    expect(backendStepSource).not.toContain('rgb-text')
    expect(backendStepSource).not.toMatch(/linear-gradient/)
    expect(backendStepSource).toContain('role="status"')
    expect(backendStepSource).toContain('aria-label="后端启动日志"')
  })
})
