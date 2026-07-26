import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// vi.hoisted 回调在所有 import 之前执行。Vue 的 runtime-dom 在模块加载时
// 捕获 document 引用；若此时 document 为 undefined，则捕获 null，后续所有
// createElement 调用都会失败。这里先设置可变空对象，beforeEach 中填充真实方法。
vi.hoisted(() => {
  if (typeof (globalThis as any).document === 'undefined') {
    ;(globalThis as any).document = {
      createElement: () => ({ innerHTML: '', content: { appendChild: () => {} } }),
      createElementNS: () => ({ innerHTML: '', content: { appendChild: () => {} } }),
      createTextNode: () => ({}),
      createComment: () => ({}),
      documentElement: {},
      head: {},
      body: {},
      querySelector: () => null,
      querySelectorAll: () => [],
    }
  }
  if (typeof (globalThis as any).window === 'undefined') {
    ;(globalThis as any).window = {}
  }
})

import { createApp, h, markRaw, nextTick, ref } from 'vue'
import * as realVue from 'vue'
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { resolve as resolvePath, dirname } from 'path'
import { fileURLToPath } from 'url'

// ===== 通过 Node 原生 require 绕过 Vite alias 加载 @vue/compiler-sfc =====
const nodeRequire = createRequire(import.meta.url)
const sfcCompiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')
const __testDir = dirname(fileURLToPath(import.meta.url))

// ===== 手动编译 .vue 文件（client transform）=====
function compileSfcComponent(filename: string, modules: Record<string, unknown>): any {
  const source = readFileSync(resolvePath(__testDir, filename), 'utf-8')
  const { descriptor, errors } = sfcCompiler.parse(source, { filename })
  if (errors && errors.length) {
    throw new Error(`SFC parse errors in ${filename}: ${errors.map(String).join('; ')}`)
  }

  const compiled = sfcCompiler.compileScript(descriptor, {
    id: filename.replace(/[^a-zA-Z0-9]/g, '-'),
    inlineTemplate: true,
    templateOptions: { ssr: false },
  })

  const rawCode: string = compiled.content || (compiled as any).code || ''
  const esbuild = nodeRequire('esbuild')
  let code: string = esbuild.transformSync(rawCode, { loader: 'ts' }).code

  code = code.replace(
    /import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_m, imports: string, from: string) => {
      const specs = imports
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean)
      return specs
        .map((spec: string) => {
          const m = spec.match(/^(\w+)\s+as\s+(\w+)$/)
          if (m) {
            return `const ${m[2]} = __modules__[${JSON.stringify(from)}][${JSON.stringify(m[1])}];`
          }
          return `const ${spec} = __modules__[${JSON.stringify(from)}][${JSON.stringify(spec)}];`
        })
        .join('\n')
    }
  )
  code = code.replace(
    /import\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_m, name: string, from: string) =>
      `const ${name} = (__modules__[${JSON.stringify(from)}] && __modules__[${JSON.stringify(from)}].default) || __modules__[${JSON.stringify(from)}];`
  )
  code = code.replace(
    /import\s+\*\s+as\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_m, name: string, from: string) => `const ${name} = __modules__[${JSON.stringify(from)}];`
  )

  code = code.replace(/export\s+default\s+/g, 'return ')
  code = code.replace(/export\s+\{[^}]*\}\s*;?/g, '')
  code = code.replace(/^export\s+/gm, '')

  if (!/return\s+_sfc_main/.test(code) && !/return\s+__sfc__/.test(code)) {
    code += '\nreturn typeof _sfc_main !== "undefined" ? _sfc_main : __sfc__;'
  }

  const factory = new Function('__modules__', code)
  const result = factory(modules)
  if (!result) {
    throw new Error(`compileSfcComponent(${filename}): factory returned ${result}`)
  }
  return result
}

// ===== 功能性桩 DOM =====
class FakeNode {
  nodeType = 0
  nodeValue: string | null = null
  textContent = ''
  parentNode: any = null
  nextSibling: any = null
  childNodes: any[] = []
}

class FakeText extends FakeNode {
  nodeType = 3
  constructor(text: string) {
    super()
    this.nodeValue = text
    this.textContent = text
  }
}

class FakeComment extends FakeNode {
  nodeType = 8
  constructor(text: string) {
    super()
    this.nodeValue = text
    this.textContent = text
  }
}

class FakeElement extends FakeNode {
  nodeType = 1
  tagName: string
  attrs: Record<string, string> = {}
  className = ''
  dataset: Record<string, string> = {}
  private _listeners = new Map<string, Set<Function>>()
  private _styleMap = new Map<string, string>()
  content: FakeElement | null = null
  innerHTML = ''

  constructor(tagName: string) {
    super()
    this.tagName = tagName.toUpperCase()
    if (this.tagName === 'TEMPLATE') {
      this.content = new FakeElement('DOCUMENT-FRAGMENT')
    }
  }

  style = new Proxy(this._styleMap, {
    get: (t, k: string) => {
      if (k === 'setProperty') return (key: string, val: any) => t.set(key, String(val))
      if (k === 'getPropertyValue') return (key: string) => t.get(key) ?? ''
      if (k === 'removeProperty')
        return (key: string) => {
          t.delete(key)
        }
      if (k === 'cssText')
        return Array.from(t.entries())
          .map(([k, v]) => `${k}: ${v}`)
          .join('; ')
      return t.get(k) ?? ''
    },
    set: (t, k: string, val: any) => {
      t.set(k, String(val))
      return true
    },
    has: (t, k: string) => t.has(k),
  })

  setAttribute(k: string, v: any) {
    this.attrs[k] = v == null ? '' : String(v)
  }
  getAttribute(k: string) {
    return this.attrs[k] ?? null
  }
  removeAttribute(k: string) {
    delete this.attrs[k]
  }
  hasAttribute(k: string) {
    return k in this.attrs
  }

  appendChild(c: any) {
    c.parentNode = this
    this.childNodes.push(c)
    this._relink()
    return c
  }
  insertBefore(c: any, anchor: any) {
    c.parentNode = this
    if (anchor) {
      const idx = this.childNodes.indexOf(anchor)
      if (idx < 0) this.childNodes.push(c)
      else this.childNodes.splice(idx, 0, c)
    } else {
      this.childNodes.push(c)
    }
    this._relink()
    return c
  }
  removeChild(c: any) {
    const i = this.childNodes.indexOf(c)
    if (i >= 0) this.childNodes.splice(i, 1)
    c.parentNode = null
    c.nextSibling = null
    this._relink()
    return c
  }
  private _relink() {
    for (let i = 0; i < this.childNodes.length; i++) {
      this.childNodes[i].nextSibling = this.childNodes[i + 1] || null
    }
  }
  addEventListener(type: string, handler: Function) {
    if (!this._listeners.has(type)) this._listeners.set(type, new Set())
    this._listeners.get(type)!.add(handler)
  }
  removeEventListener(type: string, handler: Function) {
    this._listeners.get(type)?.delete(handler)
  }
  dispatchEvent(type: string, ev: any = {}) {
    for (const handler of this._listeners.get(type) || []) {
      handler({ type, target: this, currentTarget: this, ...ev })
    }
    return true
  }
  remove() {
    this.parentNode?.removeChild(this)
  }
  querySelector() {
    return null
  }
  querySelectorAll() {
    return []
  }
  cloneNode() {
    return new FakeElement(this.tagName)
  }
}

interface DomStub {
  document: any
  window: any
}

function createDom(): DomStub {
  const documentElement = new FakeElement('HTML')
  const head = new FakeElement('HEAD')
  const body = new FakeElement('BODY')
  const documentStub = {
    documentElement,
    head,
    body,
    createElement: (tag: string) => markRaw(new FakeElement(tag)),
    createElementNS: (_ns: string, tag: string) => markRaw(new FakeElement(tag)),
    createTextNode: (text: string) => markRaw(new FakeText(String(text))),
    createComment: (text: string) => markRaw(new FakeComment(String(text))),
    querySelector: () => null,
    querySelectorAll: () => [],
  }

  return { document: documentStub, window: {} }
}

function findByClass(root: any, cls: string): any {
  const walk = (n: any): any => {
    if (!n) return null
    for (const c of n.childNodes || []) {
      const clsVal =
        (c.attrs && c.attrs['class']) || (typeof c.className === 'string' && c.className) || ''
      if (clsVal && String(clsVal).includes(cls)) return c
      const f = walk(c)
      if (f) return f
    }
    return null
  }
  return walk(root)
}

// ===== mock 状态 =====
interface TestStartupState {
  status: string
  message: string
  detail?: string
  canRetry: boolean
  canCopyDiagnostics: boolean
  canExit: boolean
  canOpenLogs: boolean
}

const startupState = ref<TestStartupState>({
  status: 'initializing',
  message: '正在初始化应用...',
  canRetry: false,
  canCopyDiagnostics: false,
  canExit: true,
  canOpenLogs: false,
})
const isFailureState = ref(false)
const isRunningState = ref(true)
const currentGeneration = ref(0)
const retryCount = ref(0)

const isInitialized = ref(false)
const isBootstrapping = ref(false)
const isAppReady = ref(false)

const isClosing = ref(false)

const routerPushes: string[] = []

const electronMocks = {
  backendRestart: vi.fn(),
  backendWaitReady: vi.fn(),
  backendStatus: vi.fn(),
  backendStart: vi.fn(),
  backendStop: vi.fn(),
  getAppPath: vi.fn(),
  showItemInFolder: vi.fn(),
  exportLogs: vi.fn(),
  getLogger: vi.fn(() => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() })),
  onStartupError: vi.fn(),
  removeStartupErrorListener: vi.fn(),
}

const lifecycleMocks = {
  connectWithRetry: vi.fn(),
  closeApp: vi.fn(),
}

const connectionMocks = {
  stopReconnect: vi.fn(),
}

function createStartupComposable() {
  return {
    state: startupState,
    setStatus: (status: string, options?: { message?: string; detail?: string }) => {
      const messages: Record<string, string> = {
        initializing: '正在初始化应用...',
        'backend-starting': '正在启动后端服务...',
        connected: '连接成功',
        offline: '后端离线',
        reconnecting: '正在重新连接后端...',
        timeout: '启动超时',
        failed: '启动失败',
        closing: '正在关闭应用...',
      }
      startupState.value = {
        ...startupState.value,
        status,
        message: options?.message ?? messages[status] ?? status,
        detail: options?.detail,
        canRetry: ['offline', 'timeout', 'failed'].includes(status),
        canCopyDiagnostics: ['offline', 'timeout', 'failed'].includes(status),
        canOpenLogs: ['offline', 'timeout', 'failed'].includes(status),
        canExit: status !== 'connected' && status !== 'closing',
      }
      isFailureState.value = ['offline', 'timeout', 'failed'].includes(status)
      isRunningState.value = ['initializing', 'backend-starting', 'reconnecting'].includes(status)
    },
    reset: () => {
      currentGeneration.value++
      retryCount.value = 0
      startupState.value = {
        status: 'initializing',
        message: '正在初始化应用...',
        canRetry: false,
        canCopyDiagnostics: false,
        canExit: true,
        canOpenLogs: false,
      }
      isFailureState.value = false
      isRunningState.value = true
    },
    beginRetry: () => {
      currentGeneration.value++
      retryCount.value++
      startupState.value = {
        status: 'reconnecting',
        message: '正在重新连接后端...',
        canRetry: false,
        canCopyDiagnostics: false,
        canExit: true,
        canOpenLogs: false,
      }
      isFailureState.value = false
      isRunningState.value = true
    },
    isFailure: isFailureState,
    isRunning: isRunningState,
    currentGeneration,
    retryCount,
  }
}

const App = compileSfcComponent('App.vue', {
  vue: realVue,
  'ant-design-vue': {
    ConfigProvider: {
      setup(_props: any, { slots }: any) {
        return () => h('div', { class: 'config-provider' }, slots.default?.())
      },
    },
  },
  './composables/useTheme.ts': {
    useTheme: () => ({
      antdTheme: ref({}),
      initTheme: vi.fn(),
    }),
  },
  './composables/useUpdateChecker.ts': {
    useUpdateChecker: () => ({
      stopPolling: vi.fn(),
    }),
    useUpdateModal: () => ({
      updateVisible: ref(false),
      updateData: ref(null),
      latestVersion: ref(''),
      onUpdateConfirmed: vi.fn(),
    }),
  },
  './composables/useAppClosing.ts': {
    useAppClosing: () => ({
      isClosing,
    }),
  },
  './composables/useAudioPlayer.ts': {
    useAudioPlayer: () => ({
      playSound: vi.fn(),
    }),
  },
  './composables/useAppInitialization.ts': {
    useAppInitialization: () => ({
      isInitialized,
      isBootstrapping,
      isAppReady,
    }),
    beginBootstrap: () => {
      isBootstrapping.value = true
      isAppReady.value = true
    },
    finishBootstrap: () => {
      isBootstrapping.value = false
    },
    markAsInitialized: () => {
      isInitialized.value = true
      isAppReady.value = true
    },
    resetInitializationStatus: () => {
      isInitialized.value = false
      isBootstrapping.value = false
      isAppReady.value = false
    },
  },
  './composables/useAppStartup.ts': {
    useAppStartup: createStartupComposable,
  },
  './composables/useAppLifecycle.ts': {
    closeApp: lifecycleMocks.closeApp,
    connectWithRetry: lifecycleMocks.connectWithRetry,
  },
  './services/websocket/connection.ts': {
    stopReconnect: connectionMocks.stopReconnect,
  },
  './components/AppLayout.vue': {
    setup() {
      return () => h('div', { class: 'app-layout' }, 'AppLayout')
    },
  },
  './components/TitleBar.vue': {
    setup() {
      return () => h('div', { class: 'title-bar' }, 'TitleBar')
    },
  },
  './components/UpdateModal.vue': {
    setup() {
      return () => h('div', { class: 'update-modal' }, 'UpdateModal')
    },
  },
  './components/DevDebugPanel.vue': {
    setup() {
      return () => h('div', { class: 'dev-debug-panel' }, 'DevDebugPanel')
    },
  },
  './components/GlobalPowerCountdown.vue': {
    setup() {
      return () => h('div', { class: 'global-power-countdown' }, 'GlobalPowerCountdown')
    },
  },
  './components/WebSocketMessageListener.vue': {
    setup() {
      return () => h('div', { class: 'ws-message-listener' }, 'WSListener')
    },
  },
  './components/AppClosingOverlay.vue': {
    props: ['visible'],
    setup(props: any) {
      return () => (props.visible ? h('div', { class: 'app-closing-overlay' }, 'Closing') : null)
    },
  },
  './components/BackendStartupOverlay.vue': {
    props: ['visible', 'state'],
    emits: ['retry', 'copy-diagnostics', 'open-logs', 'exit'],
    setup(props: any, { emit }: any) {
      return () =>
        props.visible
          ? h('div', { class: 'backend-startup-overlay' }, [
              h('div', { class: 'startup-status' }, props.state.status),
              h('div', { class: 'startup-message' }, props.state.message),
              props.state.canRetry
                ? h('button', { class: 'retry-button', onClick: () => emit('retry') }, '重试')
                : null,
              props.state.canExit
                ? h('button', { class: 'exit-button', onClick: () => emit('exit') }, '退出')
                : null,
            ])
          : null
    },
  },
  'vue-router': {
    useRoute: () =>
      ref({
        path: '/initialization',
        name: 'Initialization',
        fullPath: '/initialization',
      }).value,
    useRouter: () => ({
      push: (path: string) => {
        routerPushes.push(path)
        return Promise.resolve()
      },
      replace: () => Promise.resolve(),
    }),
  },
  'ant-design-vue/es/locale/zh_CN': {},
})

// ===== 测试夹具 =====
let dom: DomStub
let currentApp: any

function mountApp() {
  const app = createApp(App)
  const container = dom.document.createElement('div')
  app.mount(container)
  return { app, container }
}

beforeEach(() => {
  dom = createDom()
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  Object.assign(docTarget, dom.document)
  dom.document = docTarget

  vi.stubGlobal('SVGElement', class SVGElement {})
  vi.stubGlobal('MathMLElement', class MathMLElement {})
  vi.stubGlobal('Element', class Element {})
  vi.stubGlobal('HTMLElement', class HTMLElement {})
  vi.stubGlobal(
    'Node',
    class Node {
      static ELEMENT_NODE = 1
      static TEXT_NODE = 3
      static COMMENT_NODE = 8
    }
  )

  // 重置共享状态
  startupState.value = {
    status: 'initializing',
    message: '正在初始化应用...',
    canRetry: false,
    canCopyDiagnostics: false,
    canExit: true,
    canOpenLogs: false,
  }
  isFailureState.value = false
  isRunningState.value = true
  currentGeneration.value = 0
  retryCount.value = 0
  isInitialized.value = false
  isBootstrapping.value = false
  isAppReady.value = false
  isClosing.value = false
  routerPushes.length = 0

  // 重置 mock
  vi.clearAllMocks()
  electronMocks.backendRestart.mockResolvedValue({ success: true })
  electronMocks.backendWaitReady.mockResolvedValue({ ready: true })
  lifecycleMocks.connectWithRetry.mockResolvedValue(true)
  lifecycleMocks.closeApp.mockResolvedValue(undefined)

  const winTarget = globalThis.window as any
  winTarget.electronAPI = electronMocks
  winTarget.location = { origin: 'http://localhost:5173', href: 'http://localhost:5173/' }
  winTarget.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
  winTarget.performance = { now: () => 0 }
  winTarget.setTimeout = (fn: Function, ms?: number, ...rest: any[]) =>
    (globalThis as any).setTimeout(fn, ms, ...rest)
  winTarget.clearTimeout = (id?: any) => (globalThis as any).clearTimeout(id)
})

afterEach(() => {
  if (currentApp) {
    currentApp.unmount()
    currentApp = null
  }
  vi.useRealTimers()
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('App.vue 启动重试与状态机', () => {
  it('启动进行中不再全屏遮罩，失败时才显示遮罩', async () => {
    // 真机反馈：启动检查全屏遮罩与主界面分阶段加载重复。
    // 新行为：界面就绪即进入主界面，initializing/backend-starting/reconnecting
    // 均不显示全屏遮罩；仅 offline/timeout/failed/closing 展示。
    const { app, container } = mountApp()
    currentApp = app
    await nextTick()

    expect(findByClass(container, 'backend-startup-overlay')).toBeNull()

    const startup = createStartupComposable()
    startup.setStatus('backend-starting')
    await nextTick()
    expect(findByClass(container, 'backend-startup-overlay')).toBeNull()

    startup.setStatus('failed', { detail: '模拟失败' })
    await nextTick()
    expect(findByClass(container, 'backend-startup-overlay')).not.toBeNull()
  })

  it('重试时真正重启后端、等待就绪并重连 WebSocket', async () => {
    const { app, container } = mountApp()
    currentApp = app
    await nextTick()

    // 让遮罩进入失败状态以显示重试按钮
    const startup = createStartupComposable()
    startup.setStatus('failed', { detail: '模拟失败' })
    await nextTick()

    const retryBtn = findByClass(container, 'retry-button')
    expect(retryBtn).not.toBeNull()

    retryBtn.dispatchEvent('click')
    await nextTick()
    await Promise.resolve()

    expect(connectionMocks.stopReconnect).toHaveBeenCalled()
    expect(electronMocks.backendRestart).toHaveBeenCalled()

    await Promise.resolve()
    await nextTick()

    expect(electronMocks.backendWaitReady).toHaveBeenCalled()

    await Promise.resolve()
    await nextTick()

    expect(lifecycleMocks.connectWithRetry).toHaveBeenCalled()

    await Promise.resolve()
    await nextTick()

    expect(startupState.value.status).toBe('connected')
    expect(isInitialized.value).toBe(true)
    expect(routerPushes).toContain('/home')
  })

  it('后端重启失败时退出永久 spinner 并显示失败原因', async () => {
    electronMocks.backendRestart.mockResolvedValue({
      success: false,
      error: '后端进程无法启动',
    })

    const { app, container } = mountApp()
    currentApp = app
    await nextTick()

    const startup = createStartupComposable()
    startup.setStatus('failed', { detail: '模拟失败' })
    await nextTick()

    const retryBtn = findByClass(container, 'retry-button')
    retryBtn.dispatchEvent('click')
    await nextTick()
    await Promise.resolve()
    await nextTick()

    expect(startupState.value.status).toBe('failed')
    expect(startupState.value.detail).toContain('后端进程无法启动')
    expect(isBootstrapping.value).toBe(false)
  })

  it('连续重试时旧 Promise 结果不会覆盖新状态', async () => {
    let resolveFirstBackendRestart!: (value: { success: boolean }) => void
    electronMocks.backendRestart.mockImplementation(
      () =>
        new Promise<{ success: boolean }>(resolve => {
          resolveFirstBackendRestart = resolve
        })
    )

    const { app, container } = mountApp()
    currentApp = app
    await nextTick()

    const startup = createStartupComposable()
    startup.setStatus('failed', { detail: '模拟失败' })
    await nextTick()

    const retryBtn = findByClass(container, 'retry-button')

    // 第一次点击，启动一个长时 backendRestart
    retryBtn.dispatchEvent('click')
    await nextTick()

    const genAfterFirst = currentGeneration.value

    // 新遮罩策略下重试进行中遮罩会隐藏；模拟本轮重试超时后
    // 用户从失败遮罩再次点击重试，应该递增 generation，使第一次结果失效
    const startupForSecond = createStartupComposable()
    startupForSecond.setStatus('timeout', { detail: '模拟超时' })
    await nextTick()

    const secondRetryBtn = findByClass(container, 'retry-button')
    expect(secondRetryBtn).not.toBeNull()
    secondRetryBtn.dispatchEvent('click')
    await nextTick()

    expect(currentGeneration.value).toBe(genAfterFirst + 1)

    // 第一次 backendRestart 现在才 resolve，不应覆盖当前状态
    resolveFirstBackendRestart({ success: true })
    await Promise.resolve()
    await nextTick()

    // 当前仍在第二次重试流程中，不应变成 connected
    expect(startupState.value.status).not.toBe('connected')
  })

  it('启动超时后状态变为 timeout', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })

    const { app, container } = mountApp()
    currentApp = app
    await nextTick()

    const startup = createStartupComposable()
    startup.setStatus('failed', { detail: '模拟失败' })
    await nextTick()

    const retryBtn = findByClass(container, 'retry-button')
    retryBtn.dispatchEvent('click')
    await nextTick()

    // 推进 30 秒触发超时
    vi.advanceTimersByTime(31000)
    await nextTick()

    expect(startupState.value.status).toBe('timeout')
    expect(startupState.value.detail).toContain('30')
  })

  it('退出按钮触发 closeApp', async () => {
    const { app, container } = mountApp()
    currentApp = app
    await nextTick()

    const startup = createStartupComposable()
    startup.setStatus('failed', { detail: '模拟失败' })
    await nextTick()

    const exitBtn = findByClass(container, 'exit-button')
    expect(exitBtn).not.toBeNull()

    exitBtn.dispatchEvent('click')
    await nextTick()
    await Promise.resolve()
    await nextTick()

    expect(lifecycleMocks.closeApp).toHaveBeenCalled()
    expect(startupState.value.status).toBe('closing')
  })
})
