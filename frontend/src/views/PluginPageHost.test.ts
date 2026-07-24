/* eslint-disable vue/one-component-per-file, vue/require-default-prop -- test-only component stubs intentionally share this harness */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// vi.hoisted 回调在所有 import 之前执行。Vue 的 runtime-dom 在模块加载时
// 捕获 document 引用；若此时 document 为 undefined，则捕获 null，后续所有
// createElement 调用都会失败。这里先设置可变空对象，beforeEach 中填充真实方法。
vi.hoisted(() => {
  if (typeof (globalThis as any).document === 'undefined') {
    // Vue runtime-dom 在模块加载时调用 document.createElement('template') 创建模板容器，
    // 需要提供最小化方法避免崩溃。beforeEach 会原地替换为 FakeElement 工厂。
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
// vite.config.ts 的 vue alias（字符串键）是前缀匹配，会把 vue/server-renderer、
// vue/compiler-sfc 等子路径重写为不存在的路径。createRequire 使用 Node 原生
// 解析器，走 package.json exports 字段，绕过 alias。
const nodeRequire = createRequire(import.meta.url)
const sfcCompiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')
const __testDir = dirname(fileURLToPath(import.meta.url))

// ===== mock 句柄 =====
// 在 beforeEach 中注入真实 ref；工厂函数在 setup()（mount 时）读取 state.xxx，
// 此时 beforeEach 已执行，ref 已就绪。每个测试获得独立的 ref 实例。
const state = {
  isDark: null as Ref<boolean> | null,
  themeColor: null as Ref<string> | null,
  uiScale: null as Ref<number> | null,
  bgCssVars: null as Ref<Record<string, string>> | null,
  apiBase: 'http://localhost:36163',
}

// ===== 手动编译 .vue 文件（client transform）=====
// vitest node 环境下 @vitejs/plugin-vue 默认以 SSR 变换编译 .vue，生成
//   import { ssrRender* } from "vue/server-renderer"
// vite.config.ts 的 vue alias 前缀匹配把该子路径重写为不存在的路径，vi.mock
// 无法拦截解析失败的路径。这里用 @vue/compiler-sfc 手动编译（ssr:false，client
// render 生成 import { render* } from "vue"），通过 new Function 注入依赖，
// 完全绕过 Vite 模块系统与 alias。
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

  // compileScript 返回 SFCScriptBlock，其代码字段是 content（非 code）。
  const rawCode: string = compiled.content || (compiled as any).code || ''

  // 使用 esbuild 剥离所有 TypeScript 语法（类型注解、泛型参数、as 断言、! 非空断言等）
  // compileScript 只处理 <script setup> 宏和模板内联，不剥离 TypeScript 类型语法；
  // esbuild 的 ts loader 能完整处理这些语法并输出纯 JS。
  const esbuild = nodeRequire('esbuild')
  let code: string = esbuild.transformSync(rawCode, { loader: 'ts' }).code

  // 转换命名导入: import { A, B as C } from 'mod'
  // 拆分为独立的 const 声明，避免在输出中使用 as（后续需要剥离 as 类型断言）
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
  // 转换默认导入: import X from 'mod' → const X = __modules__["mod"].default || __modules__["mod"]
  code = code.replace(
    /import\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_m, name: string, from: string) =>
      `const ${name} = (__modules__[${JSON.stringify(from)}] && __modules__[${JSON.stringify(from)}].default) || __modules__[${JSON.stringify(from)}];`
  )
  // 转换命名空间导入: import * as X from 'mod' → const X = __modules__["mod"]
  code = code.replace(
    /import\s+\*\s+as\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_m, name: string, from: string) => `const ${name} = __modules__[${JSON.stringify(from)}];`
  )

  // 替换 export default 为 return
  code = code.replace(/export\s+default\s+/g, 'return ')
  // 移除剩余 export 声明
  code = code.replace(/export\s+\{[^}]*\}\s*;?/g, '')
  code = code.replace(/^export\s+/gm, '')

  // 确保有 return 语句
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

// ===== 编译 PluginPageHost.vue =====
// 所有依赖通过 __modules__ 注入，不依赖 vi.mock（vi.mock 无法拦截 alias 重写后的路径）。
const ReloadOutlinedStub = { name: 'ReloadOutlined', render: () => null }
const PluginPageHost = compileSfcComponent('PluginPageHost.vue', {
  vue: realVue,
  '@ant-design/icons-vue': {
    ReloadOutlined: ReloadOutlinedStub,
    default: { ReloadOutlined: ReloadOutlinedStub },
  },
  '@/api': {
    OpenAPI: {
      get BASE() {
        return state.apiBase
      },
      set BASE(v: string) {
        state.apiBase = v
      },
    },
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
  '@/router/pageDeclarations': {},
})

// ===== 功能性桩 DOM =====
// vitest 默认 node 环境无 DOM，且仓库未安装 jsdom/happy-dom，
// 这里提供最小可用的 fake DOM 让 vue runtime-dom 完成挂载与渲染。
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
  contentWindow: { postMessage: ReturnType<typeof vi.fn> } | null = null
  innerHTML = ''
  private _src = ''

  constructor(tagName: string) {
    super()
    this.tagName = tagName.toUpperCase()
    if (this.tagName === 'IFRAME') {
      this.contentWindow = { postMessage: vi.fn() }
    }
    if (this.tagName === 'TEMPLATE') {
      this.content = new FakeElement('DOCUMENT-FRAGMENT')
    }
  }

  get src() {
    return this._src
  }
  set src(v: string) {
    this._src = String(v)
    this.attrs['src'] = String(v)
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
    if (k === 'src') this._src = String(v)
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
  winListeners: Map<string, Set<Function>>
  removeMessageSpy: ReturnType<typeof vi.fn>
  logger: { debug: any; info: any; warn: any; error: any }
  dispatchWindowMessage: (event: any) => void
}

function createDom(): DomStub {
  const documentElement = new FakeElement('HTML')
  const head = new FakeElement('HEAD')
  const body = new FakeElement('BODY')
  const documentStub = {
    documentElement,
    head,
    body,
    // markRaw 阻止 Vue 对 FakeElement 创建 reactive proxy。
    // 否则 frameRef.value 是 proxy，frameRef.value.contentWindow 是另一个 proxy，
    // 与 findByTag 返回的原始 FakeElement 的 contentWindow 不是同一引用，
    // 导致 handleThemeMessage 的 event.source !== frameRef.value?.contentWindow 检查失败。
    createElement: (tag: string) => markRaw(new FakeElement(tag)),
    createElementNS: (_ns: string, tag: string) => markRaw(new FakeElement(tag)),
    createTextNode: (text: string) => markRaw(new FakeText(String(text))),
    createComment: (text: string) => markRaw(new FakeComment(String(text))),
    querySelector: () => null,
    querySelectorAll: () => [],
  }

  const winListeners = new Map<string, Set<Function>>()
  const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }
  const removeMessageSpy = vi.fn((type: string, handler: Function) => {
    winListeners.get(type)?.delete(handler)
  })

  const win: any = {
    electronAPI: { getLogger: () => logger },
    location: { origin: 'http://localhost:5173', href: 'http://localhost:5173/' },
    matchMedia: vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
    performance: { now: () => 0 },
    customElements: { get: () => undefined, define: vi.fn() },
    addEventListener: (type: string, handler: Function) => {
      if (!winListeners.has(type)) winListeners.set(type, new Set())
      winListeners.get(type)!.add(handler)
    },
    removeEventListener: removeMessageSpy,
  }
  // setTimeout/clearTimeout 委托到 globalThis，配合 vi.useFakeTimers() 控制时间推进。
  win.setTimeout = (fn: Function, ms?: number, ...rest: any[]) =>
    (globalThis as any).setTimeout(fn, ms, ...rest)
  win.clearTimeout = (id?: any) => (globalThis as any).clearTimeout(id)

  const dispatchWindowMessage = (event: any) => {
    for (const h of winListeners.get('message') || []) h(event)
  }

  return {
    document: documentStub,
    window: win,
    winListeners,
    removeMessageSpy,
    logger,
    dispatchWindowMessage,
  }
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
      // Vue runtime-dom 通过 el.className = val 设置 class（非 setAttribute），
      // 因此既检查 attrs['class']（setAttribute 路径），也检查 className 字段。
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
    component: 'PluginPage',
    renderer: 'iframe',
    url: '/plugin/foo',
    frontend_plugin: 'demo',
    element_tag: null,
    entry_asset_url: null,
    style_asset_urls: [],
    manifest_version: null,
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
  // ReloadOutlined 可能通过 resolveComponent 解析（若编译器未检测为 binding），
  // 注册为全局组件兜底。
  app.component('ReloadOutlined', ReloadOutlinedStub)
}

async function mountHost(page: PageDeclaration) {
  const app = createApp(PluginPageHost, { page })
  registerStubs(app)
  const container = dom.document.createElement('div')
  app.mount(container)
  await nextTick()
  return { app, container }
}

beforeEach(() => {
  dom = createDom()
  // Vue 的 runtime-dom 在模块加载时捕获了 document 引用（vi.hoisted 设置的空对象）。
  // 不能用 vi.stubGlobal 替换引用——Vue 持有的是旧引用；必须原地修改对象属性。
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  Object.assign(docTarget, dom.document)
  dom.document = docTarget

  const winTarget = globalThis.window as any
  for (const k of Object.keys(winTarget)) delete winTarget[k]
  Object.assign(winTarget, dom.window)
  dom.window = winTarget

  // @vue/runtime-dom 在 mount 时用 instanceof 检测 container 命名空间
  // （SVGElement / MathMLElement / Element 等）。node 环境无这些全局类，
  // stub 成空类使 FakeElement 不被识别为 SVG/MathML（返回默认 HTML 命名空间）。
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
  state.apiBase = 'http://localhost:36163'
})

afterEach(() => {
  if (currentApp) {
    currentApp.unmount()
    currentApp = null
  }
  vi.useRealTimers()
  // document/window 通过 vi.hoisted 设置，Vue 持有引用，不能用 unstubAllGlobals 替换。
  // 清除属性即可；beforeEach 会重新填充。
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  const winTarget = globalThis.window as any
  for (const k of Object.keys(winTarget)) delete winTarget[k]
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PluginPageHost iframe 宿主', () => {
  it('page.url 为空时渲染"插件页面缺少入口"提示且不渲染 iframe', async () => {
    const { container } = await mountHost(basePage({ url: null }))
    currentApp = null
    const text = collectText(container)
    expect(text).toContain('插件页面缺少入口')
    expect(findByTag(container, 'IFRAME')).toBeNull()
  })

  it('page.url 为相对路径时拼接 backendBase', async () => {
    state.isDark!.value = false
    const { container } = await mountHost(basePage({ url: '/plugin/foo' }))
    currentApp = null
    const iframe = findByTag(container, 'IFRAME')
    expect(iframe).not.toBeNull()
    expect(iframe.getAttribute('src')).toBe('http://localhost:36163/plugin/foo')
  })

  it('page.url 为绝对 http URL 时直接使用', async () => {
    state.isDark!.value = false
    const { container } = await mountHost(basePage({ url: 'http://example.com/page' }))
    currentApp = null
    const iframe = findByTag(container, 'IFRAME')
    expect(iframe).not.toBeNull()
    const src = iframe.getAttribute('src')
    expect(src).toBe('http://example.com/page')
  })

  it('保留插件 URL 的已有查询和 fragment', async () => {
    state.isDark!.value = true
    state.themeColor!.value = 'red'
    state.uiScale!.value = 1.2
    const { container } = await mountHost(basePage({ url: '/plugin/foo?tab=one#section-two' }))
    currentApp = null
    const iframe = findByTag(container, 'IFRAME')
    expect(iframe.getAttribute('src')).toBe('http://localhost:36163/plugin/foo?tab=one#section-two')
  })

  it('主题变化只发送 postMessage，不改写 src 或重载 iframe', async () => {
    const { container, app } = await mountHost(basePage())
    currentApp = app
    const iframe = findByTag(container, 'IFRAME')
    const initialSrc = iframe.getAttribute('src')
    const post = iframe.contentWindow.postMessage
    post.mockClear()

    state.themeColor!.value = 'red'
    await nextTick()

    expect(findByTag(container, 'IFRAME')).toBe(iframe)
    expect(iframe.getAttribute('src')).toBe(initialSrc)
    expect(post).toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'automas-theme-update', primaryColor: 'red' }),
      '*'
    )
  })

  it('iframe load 事件触发后清除 loadError 并调用 postThemeMessage', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const { container, app } = await mountHost(basePage())
    currentApp = app
    const iframe = findByTag(container, 'IFRAME')
    const post = iframe.contentWindow.postMessage
    post.mockClear()

    iframe.dispatchEvent('load')
    await nextTick()

    // load 触发即视为成功；推进 8s 不应再触发超时
    vi.advanceTimersByTime(8000)
    await nextTick()

    expect(collectText(container)).not.toContain('插件页面加载超时')
    expect(findByTag(container, 'IFRAME')).not.toBeNull()
    expect(post).toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'automas-theme-update' }),
      '*'
    )
  })

  it('iframe error 事件触发后设置 loadError 为 onerror 文案', async () => {
    const { container, app } = await mountHost(basePage())
    currentApp = app
    const iframe = findByTag(container, 'IFRAME')

    iframe.dispatchEvent('error')
    await nextTick()

    const text = collectText(container)
    expect(text).toContain('插件 iframe 加载失败')
    expect(findByTag(container, 'IFRAME')).toBeNull()
  })

  it('8s 未触发 load 事件时设置加载超时错误', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const { container, app } = await mountHost(basePage())
    currentApp = app
    expect(findByTag(container, 'IFRAME')).not.toBeNull()

    vi.advanceTimersByTime(8000)
    await nextTick()

    const text = collectText(container)
    expect(text).toContain('插件页面加载超时')
    expect(findByTag(container, 'IFRAME')).toBeNull()
  })

  it('retryLoad 用查询参数重载并保留已有 fragment', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const { container, app } = await mountHost(basePage({ url: '/plugin/foo?tab=one#section-two' }))
    currentApp = app
    const iframe = findByTag(container, 'IFRAME')
    iframe.dispatchEvent('error')
    await nextTick()
    expect(collectText(container)).toContain('插件 iframe 加载失败')

    // 点击重试按钮
    const btn = findByClass(container, 'a-button')
    expect(btn).not.toBeNull()
    btn.dispatchEvent('click')
    await nextTick()

    const newIframe = findByTag(container, 'IFRAME')
    expect(newIframe).not.toBeNull()
    expect(newIframe.getAttribute('src')).toBe(
      'http://localhost:36163/plugin/foo?tab=one&automas_retry=1#section-two'
    )
    expect(collectText(container)).not.toContain('插件 iframe 加载失败')
  })

  it('重试后忽略旧 iframe 晚到的 load/error 事件', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const { container, app } = await mountHost(basePage())
    currentApp = app
    const oldIframe = findByTag(container, 'IFRAME')

    oldIframe.dispatchEvent('error')
    await nextTick()
    const btn = findByClass(container, 'a-button')
    btn.dispatchEvent('click')
    await nextTick()

    const currentIframe = findByTag(container, 'IFRAME')
    expect(currentIframe).not.toBeNull()
    expect(currentIframe).not.toBe(oldIframe)

    oldIframe.dispatchEvent('load')
    oldIframe.dispatchEvent('error')
    await nextTick()

    expect(findByTag(container, 'IFRAME')).toBe(currentIframe)
    expect(collectText(container)).not.toContain('插件 iframe 加载失败')

    vi.advanceTimersByTime(8000)
    await nextTick()
    expect(collectText(container)).toContain('插件页面加载超时')
  })

  it('onBeforeUnmount 清理 timeout 和 message listener（spy 验证 removeEventListener）', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const { app } = await mountHost(basePage())
    currentApp = null
    expect(dom.winListeners.get('message')?.size ?? 0).toBe(1)

    app.unmount()

    // removeEventListener 被 spy 调用，且 message 监听集合被清空
    expect(dom.removeMessageSpy).toHaveBeenCalled()
    expect(dom.winListeners.get('message')?.size ?? 0).toBe(0)
  })

  it('收到 iframe 的 automas-theme-request 回询时响应主题更新', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const { container, app } = await mountHost(basePage())
    currentApp = app
    const iframe = findByTag(container, 'IFRAME')
    iframe.dispatchEvent('load')
    await nextTick()
    const post = iframe.contentWindow.postMessage
    const before = post.mock.calls.length

    dom.dispatchWindowMessage({
      source: iframe.contentWindow,
      data: { type: 'automas-theme-request' },
    })

    expect(post.mock.calls.length).toBeGreaterThan(before)
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'automas-theme-update' }),
      '*'
    )
  })
})
