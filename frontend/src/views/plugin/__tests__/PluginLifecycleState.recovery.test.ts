/**
 * 插件生命周期状态恢复与边界测试。
 *
 * 覆盖：
 * - discovery → activate → update → deactivate → failed → restart-required 状态转换
 * - 各状态 UI 展示正确性
 * - 错误恢复与重试
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

import { createApp, h, markRaw, nextTick } from 'vue'
import * as realVue from 'vue'
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { resolve as resolvePath, dirname } from 'path'
import { fileURLToPath } from 'url'

const nodeRequire = createRequire(import.meta.url)
const sfcCompiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')
const __testDir = dirname(fileURLToPath(import.meta.url))

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

// ===== Type mocks =====
const STATUS_LABELS: Record<string, string> = {
  active: '运行中',
  loaded: '已加载',
  configured: '待配置',
  discovered: '已发现',
  error: '异常',
  disposed: '已销毁',
  unloaded: '已卸载',
}

const PHASE_LABELS: Record<string, string> = {
  active: '已激活',
  discovered: '已发现',
  loaded: '已加载',
  configured: '已配置',
  on_load: '加载中',
  on_start: '启动中',
  on_stop: '停止中',
  on_unload: '卸载中',
  on_reload_prepare: '重载准备',
  on_reload_commit: '重载提交',
  on_reload_rollback: '重载回滚',
  reload_failed: '重载失败',
  disposed: '已销毁',
  unloaded: '已卸载',
  idle: '空闲',
}

const LIFECYCLE_STATUS_LABELS: Record<string, string> = {
  discovered: '已发现',
  installed: '已安装',
  activating: '激活中',
  active: '运行中',
  update: '更新可用',
  deactivating: '停用中',
  failed: '异常',
  disabled: '已禁用',
  'restart-required': '需重启',
}

const LIFECYCLE_STATUS_COLORS: Record<string, string> = {
  discovered: 'default',
  installed: 'blue',
  activating: 'processing',
  active: 'success',
  update: 'orange',
  deactivating: 'warning',
  failed: 'error',
  disabled: 'default',
  'restart-required': 'purple',
}

// ===== Compile PluginLifecycleState.vue =====
const PluginLifecycleState = compileSfcComponent('../components/PluginLifecycleState.vue', {
  vue: realVue,
  '../types': {
    STATUS_LABELS,
    PHASE_LABELS,
    LIFECYCLE_STATUS_LABELS,
    LIFECYCLE_STATUS_COLORS,
  },
  'ant-design-vue': {},
  '@ant-design/icons-vue': {},
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
  innerHTML = ''

  constructor(tagName: string) {
    super()
    this.tagName = tagName.toUpperCase()
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
    electronAPI: { getLogger: () => ({ error: vi.fn(), warn: vi.fn(), info: vi.fn() }) },
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
  app.component('ATag', {
    props: { color: String },
    setup(props: any, { slots }: any) {
      return () => {
        const color = props.color || ''
        return h('span', { class: 'ant-tag', 'data-tag-color': color }, slots.default?.() ?? [])
      }
    },
  })
  app.component('ADescriptions', {
    props: { column: [Number, Object], size: String, bordered: Boolean },
    setup(_props: any, { slots }: any) {
      return () => h('div', { class: 'ant-descriptions' }, slots.default?.() ?? [])
    },
  })
  app.component('ADescriptionsItem', {
    props: { label: String },
    setup(props: any, { slots }: any) {
      return () =>
        h(
          'div',
          { class: 'ant-descriptions-item', 'data-label': props.label },
          slots.default?.() ?? []
        )
    },
  })
  app.component('AResult', {
    props: { status: String, title: String, subTitle: String },
    setup(props: any, { slots }: any) {
      return () =>
        h('div', { class: 'ant-result', 'data-status': props.status }, [
          props.title ? h('div', { class: 'ant-result-title' }, props.title) : null,
          props.subTitle ? h('div', { class: 'ant-result-subtitle' }, props.subTitle) : null,
          slots.extra?.() ?? [],
        ])
    },
  })
  app.component('AButton', {
    props: { type: String },
    emits: ['click'],
    setup(_props: any, { slots, emit }: any) {
      return () =>
        h('button', { class: 'ant-btn', onClick: () => emit('click') }, slots.default?.() ?? [])
    },
  })
  app.component('ASpace', {
    setup(_props: any, { slots }: any) {
      return () => h('div', { class: 'ant-space' }, slots.default?.() ?? [])
    },
  })
}

interface TestRuntimeState {
  instance_id: string
  plugin: string
  status: string
  generation: number
  lifecycle_phase: string
  reload_count: number
  last_reload_reason?: string | null
  last_error?: string | null
}

function makeRuntimeState(overrides: Partial<TestRuntimeState> = {}): TestRuntimeState {
  return {
    instance_id: 'test-instance',
    plugin: 'test-plugin',
    status: 'active',
    generation: 1,
    lifecycle_phase: 'active',
    reload_count: 0,
    ...overrides,
  }
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
})

afterEach(() => {
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  const winTarget = globalThis.window as any
  for (const k of Object.keys(winTarget)) delete winTarget[k]
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PluginLifecycleState - recovery and edge cases', () => {
  it('shows "update" status for active plugin in reload phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'active',
        lifecycle_phase: 'on_reload_prepare',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('update')
    app.unmount()
  })

  it('shows "restart-required" status for error with reload_failed phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'error',
        lifecycle_phase: 'reload_failed',
        last_error: 'Reload configuration failed',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('restart-required')
    app.unmount()
  })

  it('shows "restart-required" for error with rollback phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'error',
        lifecycle_phase: 'on_reload_rollback',
        last_error: 'Rollback after failed reload',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('restart-required')
    app.unmount()
  })

  it('shows "deactivating" for loaded plugin in stop phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'loaded',
        lifecycle_phase: 'on_stop',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('deactivating')
    app.unmount()
  })

  it('shows "deactivating" for loaded plugin in unload phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'loaded',
        lifecycle_phase: 'on_unload',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('deactivating')
    app.unmount()
  })

  it('shows "activating" for loaded plugin in load phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'loaded',
        lifecycle_phase: 'on_load',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('activating')
    app.unmount()
  })

  it('shows "activating" for loaded plugin in start phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'loaded',
        lifecycle_phase: 'on_start',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('activating')
    app.unmount()
  })

  it('shows "discovered" when no runtimeState', async () => {
    const app = createApp(PluginLifecycleState, { runtimeState: null })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('discovered')
    app.unmount()
  })

  it('shows "active" for active plugin with active phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'active',
        lifecycle_phase: 'active',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('active')
    app.unmount()
  })

  it('shows "failed" for error status without reload phase', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'error',
        lifecycle_phase: 'active',
        last_error: 'Generic plugin error',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('failed')
    expect(collectText(container)).toContain('Generic plugin error')
    app.unmount()
  })

  it('shows "disabled" for disposed status', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'disposed',
        lifecycle_phase: 'disposed',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const root = container.childNodes[0]
    expect(root.attrs['data-status']).toBe('disabled')
    app.unmount()
  })

  it('shows error result with reload and copy buttons for failed state', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'error',
        last_error: 'Critical recovery needed',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const errorEl = findByClass(container, 'lifecycle-error')
    expect(errorEl).toBeTruthy()

    const buttons = findButtons(container)
    const reloadBtn = buttons.find(b => collectText(b).includes('重载'))
    const copyBtn = buttons.find(b => collectText(b).includes('复制'))
    expect(reloadBtn).toBeTruthy()
    expect(copyBtn).toBeTruthy()
    app.unmount()
  })

  it('does not show error result for non-error state', async () => {
    const app = createApp(PluginLifecycleState, {
      runtimeState: makeRuntimeState({
        status: 'active',
        lifecycle_phase: 'active',
      }),
    })
    registerStubs(app)
    const container = dom.document.createElement('div')
    app.mount(container)
    await nextTick()

    const errorEl = findByClass(container, 'lifecycle-error')
    expect(errorEl).toBeNull()
    app.unmount()
  })
})
