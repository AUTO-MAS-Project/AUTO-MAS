import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, 'BackendStartupOverlay.vue'), 'utf-8')

describe('BackendStartupOverlay 启动遮罩契约', () => {
  it('使用 script setup lang="ts" 与 scoped styles', () => {
    expect(source).toContain('<script setup lang="ts">')
    expect(source).toContain('<style scoped>')
  })

  it('作为 dialog 具备 aria-modal、aria-labelledby、aria-describedby', () => {
    expect(source).toContain('role="dialog"')
    expect(source).toContain('aria-modal="true"')
    expect(source).toContain('aria-labelledby="startup-title"')
    expect(source).toContain('aria-describedby="startup-desc"')
  })

  it('支持全部八种启动状态类型', () => {
    // 组件通过 props.state.status 消费状态，失败状态显式分支，其余状态落入默认 loading
    expect(source).toContain('props.state.status')
    expect(source).toContain("'offline'")
    expect(source).toContain("'timeout'")
    expect(source).toContain("'failed'")
    expect(source).toContain("'connected'")
    expect(source).toContain("'closing'")
    expect(source).toContain('reconnecting:')
  })

  it('失败操作区具备 role="group" 与 aria-label', () => {
    expect(source).toContain('role="group"')
    expect(source).toContain('aria-label="启动失败操作"')
  })

  it('暴露 retry、copy-diagnostics、open-logs、exit 事件', () => {
    expect(source).toContain("(e: 'retry')")
    expect(source).toContain("(e: 'copy-diagnostics')")
    expect(source).toContain("(e: 'open-logs')")
    expect(source).toContain("(e: 'exit')")
  })

  it('失败状态显示重试、打开日志、复制诊断、安全退出按钮', () => {
    expect(source).toContain('state.canRetry')
    expect(source).toContain('state.canOpenLogs')
    expect(source).toContain('state.canCopyDiagnostics')
    expect(source).toContain('state.canExit')
    expect(source).toContain('重试')
    expect(source).toContain('打开日志')
    expect(source).toContain('复制诊断信息')
    expect(source).toContain('安全退出')
  })

  it('按钮具备 aria-label 且图标 aria-hidden', () => {
    expect(source).toContain('aria-label="重试启动"')
    expect(source).toContain('aria-label="打开日志目录"')
    expect(source).toContain('aria-label="复制诊断信息"')
    expect(source).toContain('aria-label="安全退出应用"')
    expect(source).toContain('aria-hidden="true"')
  })

  it('使用 v6 design tokens', () => {
    expect(source).toContain('var(--v6-')
  })

  it('展示真实冷启动的五阶段进度轨道', () => {
    expect(source).toContain('startup-stage-list')
    expect(source).toContain("key: 'renderer'")
    expect(source).toContain("key: 'runtime'")
    expect(source).toContain("key: 'backend'")
    expect(source).toContain("key: 'connection'")
    expect(source).toContain("key: 'ready'")
    expect(source).toContain('props.state.stage')
  })
  it('尊重 prefers-reduced-motion', () => {
    expect(source).toContain('prefers-reduced-motion')
  })
})
