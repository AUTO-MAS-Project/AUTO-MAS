/* eslint-disable vue/one-component-per-file, vue/require-default-prop -- test-only component stubs intentionally share this harness */
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

import { createApp, h, markRaw, nextTick, ref, type Ref } from 'vue'
import * as realVue from 'vue'
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { resolve as resolvePath, dirname } from 'path'
import { fileURLToPath } from 'url'

import type { PageDeclaration } from '@/router/pageDeclarations'

// ===== 通过 Node 原生 require 绕过 Vite alias 加载 @vue/compiler-sfc =====
const nodeRequire = createRequire(import.meta.url)
const sfcCompiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')
const __testDir = dirname(fileURLToPath(import.meta.url))

// ===== mock 句柄 =====
const state = {
  isDark: null as Ref<boolean> | null,
  themeColor: null as Ref<string> | null,
  uiScale: null as Ref<number> | null,
  bgCssVars: null as Ref<Record<string, string>> | null,
}

// 可控 Promise：每次 ensurePluginFrontendPage 被调用时创建新的 Promise，
// resolve/reject 存入 pendingResolvers 队列，测试中按需出队。
const pendingResolvers: Array<{
  resolve: (release?: () => void) => void
  reject: (e: Error) => void
}> = []
const ensurePluginFrontendPageMock = vi.fn(
  () =>
    new Promise<() => void>((resolve, reject) => {
      pendingResolvers.push({
        resolve: release => resolve(release ?? (() => {})),
        reject,
      })
    })
)
const setPluginPageContextMock = vi.fn()

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

// ===== 编译 PluginElementHost.vue =====
const ReloadOutlinedStub = { name: 'ReloadOutlined', render: () => null }
const PluginElementHost = compileSfcComponent('PluginElementHost.vue', {
  vue: realVue,
  '@ant-design/icons-vue': {
    ReloadOutlined: ReloadOutlinedStub,
    default: { ReloadOutlined: ReloadOutlinedStub },
  },
  '@/router/pageDeclarations': {},
  '@/plugin/pluginFrontendLoader': {
    ensurePluginFrontendPage: ensurePluginFrontendPageMock,
  },
  '@/plugin/pluginPageContext': {
    setPluginPageContext: setPluginPageContextMock,
  },
  '@/composables/useAppBackground': {
    useAppBackground: () => ({ cssVars: state.bgCssVars }),
  },
  '@/composables/useTheme': {
    useTheme: () => ({
      isDark: state.isDark,
      themeColor: state.themeColor,
      uiScale: state.uiScale,
      antdTheme: { value: {} },
      themeColors: {},
    }),
  },
  '@/plugins/ui/pluginSecurity': {
    validatePluginEntryUrl: (url: string) => ({
      safe: true,
      sanitizedUrl: /^https?:\/\//i.test(url)
        ? url
        : `http://localhost:36163/${url.replace(/^\/+/, '')}`,
    }),
  },
  '@/plugins/ui/pluginUIManifest': {
    isManifestVersionSupported: () => true,
    getSupportedManifestVersion: () => '1',
  },
  '@/plugins/ui/PluginErrorBoundary.vue': {
    default: {
      name: 'PluginErrorBoundary',
      props: ['extensionId', 'pluginName'],
      emits: ['disable', 'retry'],
      setup:
        (_props: unknown, { slots }: { slots: Record<string, () => unknown> }) =>
        () =>
          slots.default?.(),
    },
  },
})

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
    for (const handler of this._listeners.get(type) || []) handler({ type, ...ev })
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

  const win: any = {
    electronAPI: {
      getLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
    },
    location: { origin: 'http://localhost:5173', href: 'http://localhost:5173/' },
    matchMedia: vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
    performance: { now: () => 0 },
    customElements: { get: () => undefined, define: vi.fn() },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    setTimeout: (fn: Function, ms?: number, ...rest: any[]) =>
      (globalThis as any).setTimeout(fn, ms, ...rest),
    clearTimeout: (id?: any) => (globalThis as any).clearTimeout(id),
    setInterval: (fn: Function, ms?: number, ...rest: any[]) =>
      (globalThis as any).setInterval(fn, ms, ...rest),
    clearInterval: (id?: any) => (globalThis as any).clearInterval(id),
  }

  return { document: documentStub, window: win }
}

function collectText(node: any): string {
  if (!node) return ''
  if (node.nodeType === 3 || node.nodeType === 8) return node.nodeValue || ''
  const kids = node.childNodes || []
  if (kids.length) return kids.map(collectText).join('')
  return typeof node.textContent === 'string' ? node.textContent : ''
}

function findByTag(root: any, tag: string): any {
  const upper = tag.toUpperCase()
  const walk = (n: any): any => {
    if (!n) return null
    for (const c of n.childNodes || []) {
      if (c.tagName === upper) return c
      const f = walk(c)
      if (f) return f
    }
    return null
  }
  return walk(root)
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

function getStyleAttr(root: any, prop: string): string | undefined {
  const walk = (n: any): string | undefined => {
    if (!n) return undefined
    for (const c of n.childNodes || []) {
      if (c._styleMap && c._styleMap.get && c._styleMap.get(prop)) return c._styleMap.get(prop)
      const f = walk(c)
      if (f !== undefined) return f
    }
    return undefined
  }
  return walk(root)
}

// ===== 测试夹具 =====
let dom: DomStub
let currentApp: any

const basePage = (over: Partial<PageDeclaration> = {}): PageDeclaration =>
  ({
    id: 'p1',
    path: '/p1',
    title: '测试页面',
    menu_label: '测试',
    icon: 'app',
    component: 'PluginElement',
    renderer: 'custom-element',
    url: null,
    frontend_plugin: 'demo',
    element_tag: 'demo-plugin-page',
    entry_asset_url: '/static/demo.js',
    style_asset_urls: [],
    manifest_version: 1,
    dev_frontend_command: null,
    dev_frontend_error: null,
    section: 'main',
    order: 10,
    visible: true,
    dev_only: false,
    source: 'test',
    ...over,
  }) as PageDeclaration

function registerStubs(app: any) {
  app.component('ASpin', {
    props: { size: String, tip: String },
    setup(props: any) {
      return () => h('div', { class: 'a-spin' }, props.tip ?? '')
    },
  })
  app.component('AResult', {
    props: { status: String, title: String, subTitle: String },
    setup(props: any, { slots }: any) {
      return () =>
        h('div', { class: 'a-result' }, [
          props.title ?? '',
          props.subTitle ?? '',
          slots.extra?.() ?? [],
        ])
    },
  })
  app.component('AButton', {
    props: { type: String },
    emits: ['click'],
    setup(_props: any, { slots, emit }: any) {
      return () =>
        h('button', { class: 'a-button', onClick: () => emit('click') }, slots.default?.() ?? [])
    },
  })
  app.component('ReloadOutlined', ReloadOutlinedStub)
}

async function mountHost(page: PageDeclaration) {
  const app = createApp(PluginElementHost, { page })
  registerStubs(app)
  const container = dom.document.createElement('div')
  app.mount(container)
  await nextTick()
  return { app, container }
}

beforeEach(() => {
  dom = createDom()
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  Object.assign(docTarget, dom.document)
  dom.document = docTarget

  const winTarget = globalThis.window as any
  for (const k of Object.keys(winTarget)) delete winTarget[k]
  Object.assign(winTarget, dom.window)
  dom.window = winTarget

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
  state.isDark = ref(true)
  state.themeColor = ref('blue')
  state.uiScale = ref(1)
  state.bgCssVars = ref({ '--app-background-image': 'none' })

  pendingResolvers.length = 0
  ensurePluginFrontendPageMock.mockClear()
  setPluginPageContextMock.mockClear()
})

afterEach(() => {
  if (currentApp) {
    currentApp.unmount()
    currentApp = null
  }
  vi.useRealTimers()
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  const winTarget = globalThis.window as any
  for (const k of Object.keys(winTarget)) delete winTarget[k]
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// 辅助：resolve 当前 pending 的 ensurePluginFrontendPage Promise
function resolveCurrentLoad(release?: () => void) {
  const p = pendingResolvers.shift()
  if (p) p.resolve(release)
}

function rejectCurrentLoad(error: Error) {
  const p = pendingResolvers.shift()
  if (p) p.reject(error)
}

describe('PluginElementHost custom element 宿主', () => {
  it('初始挂载时 loading=true 渲染 a-spin 且调用 ensurePluginFrontendPage', async () => {
    const { container, app } = await mountHost(basePage())
    currentApp = app

    // loadPage 在 onMounted 中启动，await ensurePluginFrontendPage 挂起，loading 仍为 true
    expect(ensurePluginFrontendPageMock).toHaveBeenCalledTimes(1)
    expect(ensurePluginFrontendPageMock).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'p1', element_tag: 'demo-plugin-page' })
    )
    const spin = findByClass(container, 'a-spin')
    expect(spin).not.toBeNull()
    expect(collectText(container)).toContain('正在加载插件页面')
  })

  it('ensurePluginFrontendPage 成功后 loading=false 且渲染 custom element', async () => {
    const { container, app } = await mountHost(basePage({ element_tag: 'demo-plugin-page' }))
    currentApp = app

    resolveCurrentLoad()
    await nextTick()
    await nextTick()

    // loading=false 后渲染 <component :is="demo-plugin-page">
    const customEl = findByTag(container, 'DEMO-PLUGIN-PAGE')
    expect(customEl).not.toBeNull()
    expect(customEl.getAttribute('data-page-id')).toBe('p1')
    expect(customEl.getAttribute('data-plugin-id')).toBe('demo')
    expect(customEl.getAttribute('data-theme')).toBe('dark')
    expect(collectText(container)).not.toContain('正在加载插件页面')
  })

  it('ensurePluginFrontendPage 失败时渲染错误提示和重试按钮', async () => {
    const { container, app } = await mountHost(basePage())
    currentApp = app

    rejectCurrentLoad(new Error('脚本加载失败'))
    await nextTick()
    await nextTick()

    const text = collectText(container)
    expect(text).toContain('插件页面加载失败')
    expect(text).toContain('脚本加载失败')
    const btn = findByClass(container, 'a-button')
    expect(btn).not.toBeNull()
  })

  it('element_tag 为空且加载成功后渲染"缺少入口"提示', async () => {
    const { container, app } = await mountHost(
      basePage({ element_tag: null, renderer: 'component' })
    )
    currentApp = app

    resolveCurrentLoad()
    await nextTick()
    await nextTick()

    const text = collectText(container)
    expect(text).toContain('插件页面缺少入口')
    expect(text).toContain('custom element')
  })

  it('retryLoad 触发后重新调用 ensurePluginFrontendPage', async () => {
    const { container, app } = await mountHost(basePage())
    currentApp = app

    // 第一次加载失败
    rejectCurrentLoad(new Error('首次失败'))
    await nextTick()
    await nextTick()
    expect(collectText(container)).toContain('首次失败')
    expect(ensurePluginFrontendPageMock).toHaveBeenCalledTimes(1)

    // 点击重试
    const btn = findByClass(container, 'a-button')
    expect(btn).not.toBeNull()
    btn.dispatchEvent('click')
    await nextTick()

    // 第二次 loadPage 启动，ensurePluginFrontendPage 被再次调用
    expect(ensurePluginFrontendPageMock).toHaveBeenCalledTimes(2)

    // 第二次加载成功
    resolveCurrentLoad()
    await nextTick()
    await nextTick()

    const customEl = findByTag(container, 'DEMO-PLUGIN-PAGE')
    expect(customEl).not.toBeNull()
    expect(collectText(container)).not.toContain('首次失败')
  })

  it('页面切换时忽略旧加载的晚到结果并释放其资源', async () => {
    const { container, app } = await mountHost(basePage())
    currentApp = app
    const oldLoad = pendingResolvers[0]
    const oldRelease = vi.fn()
    const activeRelease = vi.fn()

    app._instance!.props.page = basePage({
      id: 'p2',
      path: '/p2',
      title: '第二页',
      element_tag: 'second-plugin-page',
    })
    await nextTick()
    expect(ensurePluginFrontendPageMock).toHaveBeenCalledTimes(2)
    const activeLoad = pendingResolvers[1]

    activeLoad.resolve(activeRelease)
    await nextTick()
    await nextTick()
    expect(findByTag(container, 'SECOND-PLUGIN-PAGE')).not.toBeNull()

    oldLoad.resolve(oldRelease)
    await nextTick()
    await nextTick()

    expect(oldRelease).toHaveBeenCalledTimes(1)
    expect(activeRelease).not.toHaveBeenCalled()
    expect(findByTag(container, 'SECOND-PLUGIN-PAGE')).not.toBeNull()
    expect(findByTag(container, 'DEMO-PLUGIN-PAGE')).toBeNull()
  })

  it('卸载后加载结果晚到时立即释放且不恢复页面状态', async () => {
    const { app } = await mountHost(basePage())
    currentApp = null
    const pendingLoad = pendingResolvers[0]
    const release = vi.fn()

    app.unmount()
    pendingLoad.resolve(release)
    await nextTick()

    expect(release).toHaveBeenCalledTimes(1)
    expect(setPluginPageContextMock).toHaveBeenLastCalledWith(null)
  })

  it('onBeforeUnmount 调用 setPluginPageContext(null)', async () => {
    const { app } = await mountHost(basePage())
    currentApp = null

    // setPluginPageContext 在 loadPage 中以页面上下文调用
    expect(setPluginPageContextMock).toHaveBeenCalledWith(
      expect.objectContaining({ pageId: 'p1', elementTag: 'demo-plugin-page' })
    )

    app.unmount()

    // 卸载后清除上下文
    expect(setPluginPageContextMock).toHaveBeenCalledWith(null)
    const lastCall =
      setPluginPageContextMock.mock.calls[setPluginPageContextMock.mock.calls.length - 1]
    expect(lastCall[0]).toBeNull()
  })

  it('hostStyle 包含正确的 v6 token（dark/theme-name/ui-scale/surface-host）', async () => {
    state.isDark!.value = true
    state.themeColor!.value = 'red'
    state.uiScale!.value = 1.5
    const { container, app } = await mountHost(basePage())
    currentApp = app

    // host 容器（div.plugin-element-host）的 style 应包含 v6 token
    expect(getStyleAttr(container, '--v6-color-is-dark')).toBe('1')
    expect(getStyleAttr(container, '--v6-color-theme-name')).toBe('red')
    expect(getStyleAttr(container, '--v6-ui-scale-host')).toBe('1.5')
    expect(getStyleAttr(container, '--v6-color-surface-host')).toBe('var(--v6-color-surface)')
    expect(getStyleAttr(container, '--v6-color-text-host')).toBe('var(--v6-color-text)')
    expect(getStyleAttr(container, '--v6-color-border-host')).toBe('var(--v6-color-border)')
  })

  it('syncPageContext 传递正确的页面上下文字段', async () => {
    const page = basePage({
      id: 'ctx-test',
      path: '/ctx',
      title: '上下文测试',
      renderer: 'custom-element',
      source: 'manifest',
      frontend_plugin: 'ctx-plugin',
      element_tag: 'ctx-element',
    })
    const { app } = await mountHost(page)
    currentApp = app

    // loadPage → syncPageContext → setPluginPageContext 被调用
    expect(setPluginPageContextMock).toHaveBeenCalledWith(
      expect.objectContaining({
        pageId: 'ctx-test',
        path: '/ctx',
        title: '上下文测试',
        renderer: 'custom-element',
        source: 'manifest',
        pluginId: 'ctx-plugin',
        elementTag: 'ctx-element',
      })
    )
  })
})
