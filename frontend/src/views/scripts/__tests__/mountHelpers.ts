/**
 * Lane 04 组件测试辅助函数。
 *
 * 由于仓库未安装 @vue/test-utils / jsdom / happy-dom，这里提供一套最小化的
 * Node 环境下 client 编译 + 伪 DOM 渲染能力，用于验证组件交互行为。
 */

import { vi } from 'vitest'
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { resolve as resolvePath, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createApp, markRaw, nextTick, type Component } from 'vue'

const nodeRequire = createRequire(import.meta.url)
const sfcCompiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')

const __testDir = dirname(fileURLToPath(import.meta.url))

export class FakeNode {
  nodeType = 0
  nodeValue: string | null = null
  parentNode: any = null
  nextSibling: any = null
  childNodes: any[] = []

  get textContent(): string {
    return this.childNodes.map(c => c.textContent ?? '').join('')
  }

  set textContent(value: string) {
    this.childNodes = []
    if (value) this.childNodes.push(new FakeText(value))
  }
}

export class FakeText extends FakeNode {
  nodeType = 3
  constructor(text: string) {
    super()
    this.nodeValue = text
  }

  get textContent(): string {
    return this.nodeValue ?? ''
  }
}

export class FakeComment extends FakeNode {
  nodeType = 8
  constructor(text: string) {
    super()
    this.nodeValue = text
  }

  get textContent(): string {
    return this.nodeValue ?? ''
  }
}

export class FakeElement extends FakeNode {
  nodeType = 1
  tagName: string
  attrs: Record<string, string> = {}
  className = ''
  dataset: Record<string, string> = {}
  content: FakeElement | null = null
  innerHTML = ''
  private _listeners = new Map<string, Set<Function>>()
  private _styleMap = new Map<string, string>()

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
    const event = {
      type,
      target: this,
      currentTarget: this,
      preventDefault: () => {},
      stopPropagation: () => {},
      ...ev,
    }
    for (const handler of this._listeners.get(type) || []) {
      handler(event)
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

export interface DomStub {
  document: any
  window: any
}

export function createDom(): DomStub {
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

  return {
    document: documentStub,
    window: {
      matchMedia: () => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      }),
      addEventListener: () => {},
      removeEventListener: () => {},
      getComputedStyle: () => ({}),
    },
  }
}

export function installDomStub(dom: DomStub) {
  // Vue runtime-dom 在 mount 时会用 instanceof 判断容器命名空间（SVG/MathML/HTML），
  // Node 环境缺少这些全局类会导致 "SVGElement is not defined"。这里提供继承 FakeElement
  // 的占位类，既满足 instanceof 检查，又保留测试所需的 DOM 行为。
  const ElementStub = class extends FakeElement {}
  const HTMLElementStub = class extends FakeElement {}
  const SVGElementStub = class extends FakeElement {}
  const MathMLElementStub = class extends FakeElement {}
  vi.stubGlobal('Element', ElementStub)
  vi.stubGlobal('HTMLElement', HTMLElementStub)
  vi.stubGlobal('SVGElement', SVGElementStub)
  vi.stubGlobal('MathMLElement', MathMLElementStub)

  if (typeof globalThis.document === 'undefined') {
    vi.stubGlobal('document', {})
  }
  const docTarget = globalThis.document as any
  for (const k of Object.keys(docTarget)) delete docTarget[k]
  Object.assign(docTarget, dom.document)
  // 让 createElement 返回 HTMLElement 实例，确保 mount 的根容器通过 HTML 分支
  docTarget.createElement = (tag: string) => markRaw(new HTMLElementStub(tag))
  docTarget.createElementNS = (_ns: string, tag: string) => markRaw(new SVGElementStub(tag))

  if (typeof globalThis.window === 'undefined') {
    vi.stubGlobal('window', {})
  }
  const winTarget = globalThis.window as any
  Object.assign(winTarget, dom.window)
}

export function uninstallDomStub() {
  if (typeof globalThis.document !== 'undefined') {
    const docTarget = globalThis.document as any
    for (const k of Object.keys(docTarget)) delete docTarget[k]
  }
}

export function compileSfcComponent(
  filename: string,
  modules: Record<string, unknown>,
  baseDir: string = __testDir
): Component {
  const source = readFileSync(resolvePath(baseDir, filename), 'utf-8')
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
  return result as Component
}

export function findByClass(root: any, cls: string): any {
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

export function findAllByClass(root: any, cls: string): any[] {
  const result: any[] = []
  const walk = (n: any) => {
    if (!n) return
    for (const c of n.childNodes || []) {
      const clsVal =
        (c.attrs && c.attrs['class']) || (typeof c.className === 'string' && c.className) || ''
      if (clsVal && String(clsVal).includes(cls)) result.push(c)
      walk(c)
    }
  }
  walk(root)
  return result
}

export function findByTag(root: any, tag: string): any {
  const upperTag = tag.toUpperCase()
  const walk = (n: any): any => {
    if (!n) return null
    for (const c of n.childNodes || []) {
      if (c.tagName === upperTag) return c
      const f = walk(c)
      if (f) return f
    }
    return null
  }
  return walk(root)
}

export function mountComponent(
  component: Component,
  props: Record<string, any> = {},
  components: Record<string, Component> = {}
) {
  const app = createApp(component, props)
  for (const [name, comp] of Object.entries(components)) {
    app.component(name, comp)
  }
  const container = (globalThis.document as any).createElement('div')
  app.mount(container)
  return { app, container }
}

export async function flush() {
  await nextTick()
  await Promise.resolve()
}
