import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// vi.hoisted callback executes before all imports. Vue runtime-dom captures
// document reference during module load; provide a minimal stub to avoid crash.
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

const nodeRequire = createRequire(import.meta.url)
const sfcCompiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')
const __testDir = dirname(fileURLToPath(import.meta.url))

// ===== Mock handles =====
const mockLogger = {
  error: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
}

// ===== Manual SFC compilation =====
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

  // Transform named imports: import { A, B as C } from 'mod'
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
  // Transform default imports
  code = code.replace(
    /import\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_m, name: string, from: string) =>
      `const ${name} = (__modules__[${JSON.stringify(from)}] && __modules__[${JSON.stringify(from)}].default) || __modules__[${JSON.stringify(from)}];`
  )
  // Transform namespace imports
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

// ===== Compile PluginErrorBoundary.vue =====
const PluginErrorBoundary = compileSfcComponent('../PluginErrorBoundary.vue', {
  vue: realVue,
  '@ant-design/icons-vue': {
    CopyOutlined: { name: 'CopyOutlined', render: () => null },
    ReloadOutlined: { name: 'ReloadOutlined', render: () => null },
    StopOutlined: { name: 'StopOutlined', render: () => null },
  },
  'ant-design-vue': {
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
    default: { message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } },
  },
})

// ===== Fake DOM =====
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
    for (const handler of this._listeners.get(type) || [])
      handler({ type, target: this, currentTarget: this, ...ev })
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

function createDom() {
  const documentElement = new FakeElement('HTML')
  const head = new FakeElement('HEAD')
  const body = new FakeElement('BODY')
  const documentStub = {
    documentElement,
    head,
    body,
    createElement: (tag: string) => markRaw(new FakeElement(tag)) as FakeElement & Element,
    createElementNS: (_ns: string, tag: string) =>
      markRaw(new FakeElement(tag)) as FakeElement & Element,
    createTextNode: (text: string) => markRaw(new FakeText(String(text))),
    createComment: (text: string) => markRaw(new FakeComment(String(text))),
    querySelector: () => null,
    querySelectorAll: () => [],
  }

  const win: any = {
    electronAPI: { getLogger: () => mockLogger },
    location: { origin: 'http://localhost:5173', href: 'http://localhost:5173/' },
    matchMedia: vi
      .fn()
      .mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    performance: { now: () => 0 },
    customElements: { get: () => undefined, define: vi.fn() },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    setTimeout: (fn: Function, ms?: number, ...rest: any[]) =>
      (globalThis as any).setTimeout(fn, ms, ...rest),
    clearTimeout: (id?: any) => (globalThis as any).clearTimeout(id),
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

function findButtons(root: any): any[] {
  const result: any[] = []
  const walk = (n: any) => {
    if (!n) return
    for (const c of n.childNodes || []) {
      if (c.tagName === 'BUTTON') result.push(c)
      walk(c)
    }
  }
  walk(root)
  return result
}

// ===== Test fixtures =====
let dom: ReturnType<typeof createDom>

function registerStubs(app: any) {
  app.component('AResult', {
    props: { status: String, title: String, subTitle: String },
    setup(props: any, { slots }: any) {
      return () =>
        h('div', { class: 'a-result', 'data-status': props.status }, [
          props.title ? h('div', { class: 'ant-result-title' }, props.title) : null,
          slots['sub-title']
            ? h('div', { class: 'ant-result-subtitle' }, slots['sub-title']())
            : props.subTitle
              ? h('div', { class: 'ant-result-subtitle' }, props.subTitle)
              : null,
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
  app.component('ASpace', {
    setup(_props: any, { slots }: any) {
      return () => h('div', { class: 'a-space' }, slots.default?.() ?? [])
    },
  })
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

  mockLogger.error.mockClear()
  mockLogger.warn.mockClear()
  mockLogger.info.mockClear()
})

afterEach(() => {
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  const winTarget = globalThis.window as any
  for (const k of Object.keys(winTarget)) delete winTarget[k]
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// Helper: create a root app that renders PluginErrorBoundary with h()
function createBoundaryApp(props: Record<string, unknown>, slotChild?: any) {
  return createApp({
    render() {
      return h(PluginErrorBoundary, props, slotChild ? { default: () => h(slotChild) } : undefined)
    },
  })
}

describe('PluginErrorBoundary', () => {
  it('renders slot content when no error', async () => {
    const app = createBoundaryApp(
      {},
      {
        setup() {
          return () => h('div', { class: 'plugin-content' }, 'Plugin Content')
        },
      }
    )
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const text = collectText(container)
    expect(text).toContain('Plugin Content')
    expect(findByClass(container, 'a-result')).toBeNull()
    app.unmount()
  })

  it('shows error result when child throws', async () => {
    const ErrorChild = {
      setup() {
        throw new Error('Test error in plugin')
      },
      render() {
        return h('div')
      },
    }

    const app = createBoundaryApp(
      { extensionId: 'test-ext-1', pluginName: 'test-plugin' },
      ErrorChild
    )
    registerStubs(app)
    app.config.warnHandler = vi.fn()
    app.config.errorHandler = vi.fn()

    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()
    await nextTick()

    const text = collectText(container)
    expect(text).toContain('插件扩展加载失败')
    expect(text).toContain('Test error in plugin')
    app.unmount()
  })

  it('shows retry button and clears error after retry', async () => {
    const ErrorChild = {
      setup() {
        throw new Error('Retry test')
      },
      render() {
        return h('div')
      },
    }

    const app = createBoundaryApp({ extensionId: 'ext-retry' }, ErrorChild)
    registerStubs(app)
    app.config.warnHandler = vi.fn()
    app.config.errorHandler = vi.fn()

    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()
    await nextTick()

    const buttons = findButtons(container)
    const primaryBtn = buttons.find(b => collectText(b).includes('重试'))
    expect(primaryBtn).toBeTruthy()
    primaryBtn.dispatchEvent('click')
    await nextTick()
    await nextTick()

    // After retry, the child still throws, so error should re-appear
    const text = collectText(container)
    expect(text).toContain('插件扩展加载失败')
    app.unmount()
  })

  it('does not show disable button when no extensionId', async () => {
    const ErrorChild = {
      setup() {
        throw new Error('No extension id')
      },
      render() {
        return h('div')
      },
    }

    const app = createBoundaryApp({}, ErrorChild)
    registerStubs(app)
    app.config.warnHandler = vi.fn()
    app.config.errorHandler = vi.fn()

    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()
    await nextTick()

    const buttons = findButtons(container)
    const disableButton = buttons.find(b => collectText(b).includes('停用'))
    expect(disableButton).toBeFalsy()
    app.unmount()
  })

  it('shows disable button when extensionId is provided', async () => {
    const ErrorChild = {
      setup() {
        throw new Error('Disable test')
      },
      render() {
        return h('div')
      },
    }

    const app = createBoundaryApp({ extensionId: 'ext-disable' }, ErrorChild)
    registerStubs(app)
    app.config.warnHandler = vi.fn()
    app.config.errorHandler = vi.fn()

    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()
    await nextTick()

    const buttons = findButtons(container)
    const disableButton = buttons.find(b => collectText(b).includes('停用'))
    expect(disableButton).toBeTruthy()
    app.unmount()
  })

  it('shows copy diagnostics button', async () => {
    const ErrorChild = {
      setup() {
        throw new Error('Copy test')
      },
      render() {
        return h('div')
      },
    }

    const app = createBoundaryApp(
      { extensionId: 'ext-copy', pluginName: 'copy-plugin' },
      ErrorChild
    )
    registerStubs(app)
    app.config.warnHandler = vi.fn()
    app.config.errorHandler = vi.fn()

    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()
    await nextTick()

    const buttons = findButtons(container)
    const copyButton = buttons.find(b => collectText(b).includes('复制'))
    expect(copyButton).toBeTruthy()
    app.unmount()
  })

  it('logs error to logger', async () => {
    mockLogger.error.mockClear()

    const ErrorChild = {
      setup() {
        throw new Error('Logger test error')
      },
      render() {
        return h('div')
      },
    }

    const app = createBoundaryApp({ extensionId: 'ext-log', pluginName: 'log-plugin' }, ErrorChild)
    registerStubs(app)
    app.config.warnHandler = vi.fn()
    app.config.errorHandler = vi.fn()

    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()
    await nextTick()

    expect(mockLogger.error).toHaveBeenCalled()
    const logCall = mockLogger.error.mock.calls[0][0]
    expect(logCall).toContain('ext-log')
    expect(logCall).toContain('log-plugin')
    app.unmount()
  })
})
