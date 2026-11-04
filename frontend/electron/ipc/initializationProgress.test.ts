import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { i18n } from '@/i18n'
import LaunchStatus from '@/components/LaunchStatus.vue'
import { useInitializationFlow } from '@/views/Initialization/useInitializationFlow'
import { InitializationService } from '../services/initializationService'
import type { InitializationProgress } from '../services/initializationService'
import { RuntimeInitializationService } from '../services/runtimeInitializationService'
import type { RuntimeBinarySyncProgress } from '../services/runtimeBinaryService'
import { registerInitializationHandlers } from './initializationHandlers'

type Handler = (event: IpcMainInvokeEvent, ...args: unknown[]) => unknown
const bridge = vi.hoisted(() => ({
  handlers: new Map<string, Handler>(),
  listeners: new Map<string, Array<(event: unknown, payload: unknown) => void>>(),
  sent: [] as Array<{ channel: string; payload: unknown }>,
  mounted: [] as Array<() => unknown>,
  logs: [] as unknown[][],
  api: undefined as Window['electronAPI'] | undefined,
  config: {
    mode: 'managed' as const,
    runtimePath: '/isolated/runtime.exe',
    appRoot: '/isolated',
    dataRoot: '/isolated',
  },
}))
vi.mock('electron', () => {
  const event = {
    sender: {
      isDestroyed: () => false,
      send: (channel: string, payload: unknown) => {
        // Electron serializes IPC payloads with the structured clone algorithm.
        const cloned = structuredClone(payload)
        bridge.sent.push({ channel, payload: cloned })
        for (const listener of bridge.listeners.get(channel) ?? []) listener({}, cloned)
      },
    },
  } as unknown as IpcMainInvokeEvent
  return {
    app: { getVersion: () => '5.8.0-beta.3', isPackaged: false },
    ipcMain: {
      handle: (channel: string, handler: Handler) => bridge.handlers.set(channel, handler),
    },
    ipcRenderer: {
      invoke: async (channel: string, ...args: unknown[]) => {
        const handler = bridge.handlers.get(channel)
        if (!handler) throw new Error(`Unexpected IPC invocation: ${channel}`)
        return handler(event, ...args)
      },
      on: (channel: string, listener: (event: unknown, payload: unknown) => void) => {
        bridge.listeners.set(channel, [...(bridge.listeners.get(channel) ?? []), listener])
      },
      removeAllListeners: (channel: string) => bridge.listeners.delete(channel),
      send: vi.fn(),
    },
    contextBridge: {
      exposeInMainWorld: (key: string, value: unknown) => {
        if (key === 'electronAPI') bridge.api = value as Window['electronAPI']
      },
    },
  }
})
vi.mock('../services', async () => ({
  InitializationService: (await import('../services/initializationService')).InitializationService,
}))
vi.mock('../services/logger', () => ({
  getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))
vi.mock('../services/mirrorService', () => ({ MirrorService: class {} }))
vi.mock('../services/backendService', () => ({ BackendService: class {} }))
vi.mock('../services/environmentService', () => ({
  getAppRoot: () => bridge.config.appRoot,
}))
vi.mock('../services/runtime', async importOriginal => ({
  ...(await importOriginal<typeof import('../services/runtime')>()),
  resolveRuntimeLaunchConfig: () => bridge.config,
}))
vi.mock('../services/runtimeUpdateService', () => ({
  cancelBackendUpdate: vi.fn(),
  retryBackendUpdate: vi.fn(),
  updateBackendViaRuntime: vi.fn(),
}))
vi.mock('../services/initializationAnalytics', () => ({
  observeInitializationStage: (_stage: string, _mode: string, run: () => unknown) => run(),
}))
vi.mock('vue', async importOriginal => ({
  ...(await importOriginal<typeof import('vue')>()),
  onMounted: (callback: () => unknown) => bridge.mounted.push(callback),
  onUnmounted: vi.fn(),
}))
vi.mock('ant-design-vue', () => ({
  message: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))
vi.mock('@/utils/environment', () => ({
  isDevelopmentEnvironment: false,
  isBrowserDevelopment: () => false,
}))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish: vi.fn() }) }))
vi.mock('@/views/Initialization/finishInitializationEntry', () => ({
  finishInitializationEntry: vi.fn(),
}))
vi.mock('@/composables/useVersionService', () => ({ getBackendVersion: vi.fn() }))

beforeAll(async () => {
  vi.stubGlobal('window', { addEventListener: vi.fn() })
  await import('../preload')
  registerInitializationHandlers({} as BrowserWindow)
  bridge.handlers.set('log:write', (_event, ...args) => {
    bridge.logs.push(args)
  })
})
beforeEach(() => {
  vi.useFakeTimers()
  bridge.mounted.length = 0
  bridge.sent.length = 0
  bridge.logs.length = 0
  bridge.listeners.clear()
  // Only unrelated startup reads are replaced. initialize/installPython and progress
  // subscriptions below are the real API exposed by preload.
  vi.stubGlobal('window', {
    electronAPI: {
      ...bridge.api!,
      getRuntimeInitContext: async () => ({ mode: 'managed' }),
      initMirrors: async () => {},
      getMirrors: async () => [],
      loadConfig: async () => ({}),
      getInitializedVersion: async () => '',
    },
  })
  vi.stubGlobal('sessionStorage', { getItem: () => null })
  i18n.global.locale.value = 'zh-CN'
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Runtime alignment → InitializationService → IPC/preload → Vue display', () => {
  it.each(['initialize', 'installPython'] as const)(
    'preserves download metadata through %s',
    async entry => {
      let emit!: (progress: RuntimeBinarySyncProgress) => void
      let finish!: () => void
      const runtime = new RuntimeInitializationService({
        launchConfig: bridge.config,
        mirrorService: { getMirrors: () => [] },
        alignRuntimeBinary: options =>
          new Promise(resolve => {
            emit = progress => options.onProgress?.(progress)
            finish = () => resolve({ status: 'cancelled' })
          }),
        createClient: () => {
          throw new Error('The test must not launch a Runtime process')
        },
      })
      vi.spyOn(InitializationService.prototype, 'getRuntimeService').mockReturnValue(runtime)
      let flow!: ReturnType<typeof useInitializationFlow>
      const app = createSSRApp({
        setup() {
          flow = useInitializationFlow()
          return () => h('div')
        },
      })
      app.use(i18n)
      await renderToString(app)
      for (const callback of bridge.mounted) await callback()
      // Invoke the actual preload API after subscriptions are installed, without
      // letting the scheduled first-run timer start a second initialization.
      vi.clearAllTimers()
      const api = window.electronAPI
      const pending = entry === 'initialize' ? api.initialize('dev', false) : api.installPython()
      const channel = entry === 'initialize' ? 'initialization-progress' : 'python-progress'
      const html = () =>
        renderToString(
          createSSRApp({
            render: () =>
              h(LaunchStatus, {
                title: flow.statusTitle.value,
                details: flow.statusDetails.value,
                progress: flow.statusProgress.value,
              }),
          })
        )
      try {
        expect(emit).toBeTypeOf('function')
        for (const source of [
          { key: 'cnb', name: 'CNB', index: 1, en: 'CNB', ja: 'CNB' },
          {
            key: 'github',
            name: 'GitHub 官方',
            index: 5,
            en: 'GitHub (official)',
            ja: 'GitHub 公式',
          },
        ]) {
          const input: RuntimeBinarySyncProgress = {
            phase: 'download',
            progress: 30,
            targetVersion: 'v0.1.99',
            source: source.key,
            sourceName: source.name,
            sourceIndex: source.index,
            sourceCount: 5,
            item: 'runtime.exe',
            current: 30,
            total: 100,
            message: `正在从 ${source.name}（${source.index}/5） 下载 Runtime v0.1.99`,
          }
          emit(input)
          const sent = bridge.sent.filter(event => event.channel === channel).at(-1)!
          expect(sent.payload).toMatchObject({
            targetVersion: input.targetVersion,
            sourceName: input.sourceName,
            sourceIndex: input.sourceIndex,
            sourceCount: input.sourceCount,
            source: input.source,
            message: input.message,
            current: input.current,
            total: input.total,
            runtimeStage: 'runtime.download',
            runtimeStatus: 'running',
            runtimeMode: 'managed',
          } satisfies Partial<InitializationProgress>)
          for (const [locale, title] of [
            ['zh-CN', `正在从 ${source.name}（${source.index}/5）下载 Runtime v0.1.99`],
            ['en-US', `Downloading Runtime v0.1.99 from ${source.en} (${source.index}/5)`],
            ['ja-JP', `${source.ja}（${source.index}/5）から Runtime v0.1.99 をダウンロード中`],
          ] as const) {
            i18n.global.locale.value = locale
            await nextTick()
            expect(await html()).toContain(title)
            expect(bridge.logs).toContainEqual(['info', '初始化流程', `[python] ${input.message}`])
          }
        }
        const legacy = {
          phase: 'download' as const,
          progress: 40,
          item: 'legacy.exe',
          message: 'legacy: 完整原文',
        }
        emit(legacy)
        for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
          i18n.global.locale.value = locale
          expect(await html()).toContain(legacy.message)
        }
        // The copied IPC payload retains unknown/missing fields without fabricating metadata.
        const last = bridge.sent.filter(event => event.channel === channel).at(-1)!
          .payload as InitializationProgress
        expect(last.targetVersion).toBeUndefined()
        expect(last.sourceName).toBeUndefined()
        expect(last.sourceIndex).toBeUndefined()
        expect(last.sourceCount).toBeUndefined()
      } finally {
        finish()
        await pending
      }
    }
  )
})
