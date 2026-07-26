import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, 'App.vue'), 'utf-8')
const updateCheckerSource = readFileSync(
  resolve(__dirname, 'composables/useUpdateChecker.ts'),
  'utf-8'
)

describe('App.vue 启动状态机集成契约', () => {
  it('集成 useAppStartup composable', () => {
    expect(source).toContain('import { useAppStartup }')
  })

  it('将 startupState 传入 BackendStartupOverlay', () => {
    expect(source).toContain(':state="startupState"')
  })

  it('监听并处理 retry、copy-diagnostics、open-logs、exit 事件', () => {
    expect(source).toContain('@retry="handleStartupRetry"')
    expect(source).toContain('@copy-diagnostics="handleCopyDiagnostics"')
    expect(source).toContain('@open-logs="handleOpenLogs"')
    expect(source).toContain('@exit="handleStartupExit"')
  })

  it('根据启动状态控制遮罩可见性', () => {
    expect(source).toContain(':visible="isStartupOverlayVisible"')
    expect(source).toContain('isStartupOverlayVisible')
  })

  it('监听 isBootstrapping 以更新启动状态', () => {
    expect(source).toContain('watch(isBootstrapping')
  })

  it('实现启动超时检测', () => {
    expect(source).toContain('STARTUP_TIMEOUT_MS')
    expect(source).toContain("setStatus('timeout'")
  })

  it('处理启动错误事件', () => {
    expect(source).toContain('onStartupError')
    expect(source).toContain("setStatus('failed'")
  })

  it('重试时递增 generation 并真正重启后端与重连 WebSocket', () => {
    expect(source).toContain('handleStartupRetry')
    expect(source).toContain('performStartupRetry')
    expect(source).toContain('beginRetry')
    expect(source).toContain('backendRestart')
    expect(source).toContain('backendWaitReady')
    expect(source).toContain('connectWithRetry')
    expect(source).toContain('isCurrentGeneration')
  })

  it('重试时停止旧 WebSocket 重连、启动超时 timer 并隔离旧 Promise', () => {
    expect(source).toContain('stopReconnect')
    expect(source).toContain('stopStartupTimeout')
    expect(source).toContain('resetInitializationStatus')
    expect(source).toContain('beginBootstrap')
  })

  it('打开日志目录并提供导出兜底', () => {
    expect(source).toContain("getAppPath('logs')")
    expect(source).toContain('showItemInFolder')
    expect(source).toContain('exportLogs')
  })

  it('安全退出调用 closeApp', () => {
    expect(source).toContain('handleStartupExit')
    expect(source).toContain('closeApp')
  })

  it('由 App 显式清理全局更新轮询，不在普通异步入口注册组件生命周期', () => {
    expect(source).toContain('useUpdateChecker, useUpdateModal')
    expect(source).toContain('stopUpdatePolling()')
    expect(updateCheckerSource).not.toContain('onUnmounted')
  })

  it('独立日志窗口不进入主应用初始化流程，也不挂载主 WebSocket 全局组件', () => {
    expect(source).toContain(
      '!isInitializationPage.value && !isStandalonePage.value && !isInitialized.value'
    )
    expect(source).toContain(
      '!isInitializationPage.value && !isStandalonePage.value && isInitialized.value'
    )
    expect(source).toContain('<template v-if="isInitialized && !isStandalonePage">')
  })
})
