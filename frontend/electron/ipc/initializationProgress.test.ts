import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { i18n } from '@/i18n'
import LaunchStatus from '@/components/LaunchStatus.vue'
import { useInitializationFlow } from '@/views/Initialization/useInitializationFlow'
import { InitializationService } from '../services/initializationService'
import type { InitializationProgress } from '../services/initializationService'
import { RuntimeInitializationService } from '../services/runtimeInitializationService'
import type { RuntimeRunOptions, RuntimeProgressEvent } from '../services/runtime'
import type { RuntimeBinarySyncProgress } from '../services/runtimeBinaryService'
import { registerInitializationHandlers } from './initializationHandlers'

type Handler = (event: IpcMainInvokeEvent, ...args: unknown[]) => unknown
const bridge = vi.hoisted(() => ({
  handlers: new Map<string, Handler>(),
  listeners: new Map<string, Array<(event: unknown, payload: unknown) => void>>(),
  sent: [] as Array<{ channel: string; payload: unknown }>,
  mounted: [] as Array<() => unknown>,
  logs: [] as unknown[][],
  senderDestroyed: false,
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
      isDestroyed: () => bridge.senderDestroyed,
      send: (channel: string, payload: unknown) => {
        // Mirrors Electron: sending to a destroyed WebContents throws.
        if (bridge.senderDestroyed) throw new TypeError('Object has been destroyed')
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
  managesBackendProcess: () => true,
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
  bridge.senderDestroyed = false
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
      loadConfig: async () => ({}),
      getInitializedVersion: async () => '',
    },
  })
  vi.stubGlobal('sessionStorage', { getItem: () => null })
  // 三语动态切换由 useInitializationFlow.test.ts 覆盖；这里验证完整 IPC 连线。
  i18n.global.locale.value = 'en-US'
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Runtime alignment → InitializationService → IPC/preload → Vue display', () => {
  it.each([
    ['installPython', 'python'],
    ['pullRepository', 'repository'],
    ['installDependencies', 'dependency'],
  ] as const)(
    '%s keeps retry separate from rebuild through preload and IPC',
    async (method, stage) => {
      const retry = vi
        .spyOn(InitializationService.prototype, 'retryStageViaRuntime')
        .mockResolvedValue({ success: true })
      await bridge.api![method](false)
      expect(retry).toHaveBeenLastCalledWith(stage, expect.any(Function), 'sync')
      await bridge.api![method](true)
      expect(retry).toHaveBeenLastCalledWith(stage, expect.any(Function), 'rebuild')
    }
  )

  it.each(['initialize', 'installPython'] as const)(
    'preserves download metadata through %s',
    async entry => {
      let emit!: (progress: RuntimeBinarySyncProgress) => void
      let finish!: () => void
      // 预先建立释放句柄，操作尚未进入回调时，finally 也能结束模拟操作。
      const completion = new Promise<void>(resolve => {
        finish = resolve
      })
      const runtime = new RuntimeInitializationService({
        launchConfig: bridge.config,
        alignRuntimeBinary: async options => {
          emit = progress => options.onProgress?.(progress)
          await completion
          return { status: 'cancelled' }
        },
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
      const channel = 'initialization-progress'
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
        await vi.waitFor(() => expect(emit).toBeTypeOf('function'))
        for (const source of [
          { key: 'cnb', name: 'CNB', index: 1, displayName: 'CNB' },
          {
            key: 'github',
            name: 'GitHub 官方',
            index: 5,
            displayName: 'GitHub (official)',
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
          expect(await html()).toContain(
            `Downloading Runtime v0.1.99 from ${source.displayName} (${source.index}/5)`
          )
          expect(bridge.logs).toContainEqual(['info', '初始化流程', `[python] ${input.message}`])
        }
        const legacy = {
          phase: 'download' as const,
          progress: 40,
          item: 'legacy.exe',
          message: 'legacy: 完整原文',
        }
        emit(legacy)
        expect(await html()).toContain(legacy.message)
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

  it.each(['initialize', 'installDependencies'] as const)(
    'keeps dependency source attempts and official fallback visible through %s',
    async entry => {
      let emit!: (
        progress: Pick<RuntimeProgressEvent, 'message' | 'item' | 'source' | 'current' | 'total'>
      ) => void
      let ready!: () => void
      let finish!: () => void
      // 预先建立释放句柄，操作尚未进入回调时，finally 也能结束模拟操作。
      const completion = new Promise<void>(resolve => {
        finish = resolve
      })
      const runtime = new RuntimeInitializationService({
        launchConfig: bridge.config,
        alignRuntimeBinary: async () => ({ status: 'current', target: { version: 'v0.1.99' } }),
        createClient: () =>
          ({
            run: async (_command: string[], options: RuntimeRunOptions) => {
              let sequence = 0
              const common = () => ({
                protocol: 1 as const,
                operationId: 'dependency-source-test',
                sequence: ++sequence,
                timestamp: '2026-11-04T00:00:00Z',
              })
              emit = progress =>
                options.onProgress?.({
                  ...common(),
                  type: 'progress',
                  stage: 'dependencies.sync',
                  status: 'running',
                  ...progress,
                })
              ready = () =>
                options.onState?.({
                  ...common(),
                  type: 'state',
                  stage: 'dependencies.sync',
                  status: 'ready_to_start',
                  message: '运行环境已就绪',
                  details: {},
                })
              await completion
              throw new Error('Controlled Runtime process stopped after assertions')
            },
          }) as never,
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
      vi.clearAllTimers()
      if (entry === 'installDependencies') {
        await flow.handleBackendError('Dependency setup needs retry', {
          code: 'DEPENDENCY_SYNC_FAILED',
        })
      }
      const pending =
        entry === 'initialize'
          ? window.electronAPI.initialize('dev', false)
          : window.electronAPI.installDependencies()
      const channel = 'initialization-progress'
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
        await vi.waitFor(() => expect(emit).toBeTypeOf('function'))
        // Runtime mirrorAttemptProgress reports these facts only in message, with
        // no item/source. The probe ranking cannot identify the active attempt.
        emit({ message: '正在同步锁定依赖' })
        for (const message of [
          '正在从镜像源 aliyun 同步锁定依赖',
          '正在从镜像源 tsinghua 同步锁定依赖',
          '镜像源均不可用，正在从官方源 pypi 按原锁同步依赖',
          'Future source diagnostic: keep this intact',
        ]) {
          emit({ message })
          const sent = bridge.sent.filter(event => event.channel === channel).at(-1)!
            .payload as InitializationProgress
          expect(sent).toMatchObject({
            runtimeStage: 'dependencies.sync',
            runtimeStatus: 'running',
            message,
          })
          expect(sent.source).toBeUndefined()
          expect(sent.item).toBeUndefined()
          expect(await html()).toContain(message)
          expect(bridge.logs).toContainEqual(['info', '初始化流程', `[dependency] ${message}`])
        }
        emit({
          message: '正在下载锁定依赖',
          item: 'package.whl',
          source: 'aliyun',
          current: 1024,
          total: 2048,
        })
        expect(flow.statusTitle.value).toBe(
          i18n.global.t('bootstrap.init.progress.dependenciesSync')
        )
        const details = await html()
        expect(details).toContain('package.whl')
        expect(details).toContain('aliyun')
        expect(details).toContain('1 KB / 2 KB')
        ready()
        expect(flow.statusTitle.value).toBe(i18n.global.t('bootstrap.init.progress.bootstrapReady'))
      } finally {
        finish()
        await pending
      }
    }
  )

  // AUTO-MAS-DESKTOP-16: the Runtime keeps emitting bootstrap progress after the
  // window is closed during quit; sending it must not crash the main process.
  it('drops initialization progress once the renderer is destroyed', async () => {
    let emit!: (progress: RuntimeBinarySyncProgress) => void
    let finish!: () => void
    const completion = new Promise<void>(resolve => {
      finish = resolve
    })
    const runtime = new RuntimeInitializationService({
      launchConfig: bridge.config,
      alignRuntimeBinary: async options => {
        emit = progress => options.onProgress?.(progress)
        await completion
        return { status: 'cancelled' }
      },
      createClient: () => {
        throw new Error('The test must not launch a Runtime process')
      },
    })
    vi.spyOn(InitializationService.prototype, 'getRuntimeService').mockReturnValue(runtime)
    const pending = window.electronAPI.initialize('dev', false)
    try {
      await vi.waitFor(() => expect(emit).toBeTypeOf('function'))
      const progress: RuntimeBinarySyncProgress = {
        phase: 'download',
        progress: 50,
        item: 'runtime.exe',
        message: 'downloading',
      }
      emit(progress)
      const delivered = bridge.sent.length
      expect(delivered).toBeGreaterThan(0)
      bridge.senderDestroyed = true
      expect(() => emit(progress)).not.toThrow()
      expect(bridge.sent).toHaveLength(delivered)
    } finally {
      finish()
      await pending
    }
  })
})
