import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { createRenderer, h, nextTick } from 'vue'
import * as vue from 'vue'

const routeQuery = vi.hoisted(() => ({ tab: 'emulators' }))
vi.hoisted(() => {
  ;(globalThis as Record<string, unknown>).window = {
    electronAPI: {
      getLogger: () => ({
        debug: vi.fn(),
        info: vi.fn(),
        warn: vi.fn(),
        error: vi.fn(),
      }),
    },
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
}))

const nodeRequire = createRequire(import.meta.url)
const compiler: typeof import('@vue/compiler-sfc') = nodeRequire('@vue/compiler-sfc')

function compileGameCenter() {
  const filename = resolve(dirname(fileURLToPath(import.meta.url)), 'index.vue')
  const source = readFileSync(filename, 'utf-8')
  const { descriptor } = compiler.parse(source, { filename })
  const raw = compiler.compileScript(descriptor, {
    id: 'game-center-mounted',
    inlineTemplate: true,
    templateOptions: { ssr: false },
  }).content
  let code: string = nodeRequire('esbuild').transformSync(raw, { loader: 'ts' }).code
  code = code.replace(
    /import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_match, imports: string, from: string) =>
      imports
        .split(',')
        .map(spec => spec.trim())
        .filter(Boolean)
        .map(spec => {
          const alias = spec.match(/^(\w+)\s+as\s+(\w+)$/)
          return alias
            ? `const ${alias[2]} = __modules__[${JSON.stringify(from)}][${JSON.stringify(alias[1])}];`
            : `const ${spec} = __modules__[${JSON.stringify(from)}][${JSON.stringify(spec)}];`
        })
        .join('\n')
  )
  code = code.replace(
    /import\s+(\w+)\s+from\s+['"]([^'"]+)['"]\s*;?/g,
    (_match, name: string, from: string) =>
      `const ${name} = __modules__[${JSON.stringify(from)}].default || __modules__[${JSON.stringify(from)}];`
  )
  code = code.replace(/export\s+default\s+/g, 'return ')
  return new Function('__modules__', code)({
    vue,
    'vue-router': { useRoute: () => ({ query: routeQuery }) },
    '@ant-design/icons-vue': {
      AppstoreOutlined: { render: () => h('span') },
      DesktopOutlined: { render: () => h('span') },
    },
    './GameInstancesTab.vue': { default: { render: () => h('div', 'games') } },
    './EmulatorTab.vue': { default: { render: () => h('div', 'emulators') } },
    '@/components/mac/PageHeader.vue': {
      default: {
        render() {
          const slots = (this as unknown as { $slots: { default?: () => unknown } }).$slots
          return h('header', slots.default?.() as never)
        },
      },
    },
  })
}

interface HostNode {
  children: HostNode[]
  parent: HostNode | null
  props?: Record<string, unknown>
  text?: string
}

const renderer = createRenderer<HostNode, HostNode>({
  patchProp(node, key, _previous, value) {
    node.props ||= {}
    node.props[key] = value
  },
  insert(child, parent) {
    child.parent = parent
    parent.children.push(child)
  },
  remove(child) {
    const index = child.parent?.children.indexOf(child) ?? -1
    if (index >= 0) child.parent?.children.splice(index, 1)
  },
  createElement: () => ({ children: [], parent: null }),
  createText: text => ({ children: [], parent: null, text }),
  createComment: text => ({ children: [], parent: null, text }),
  setText(node, text) {
    node.text = text
  },
  setElementText(node, text) {
    node.text = text
  },
  parentNode: node => node.parent,
  nextSibling: () => null,
  querySelector: () => null,
  setScopeId: () => undefined,
  cloneNode: node => ({ ...node, children: [...node.children] }),
  insertStaticContent: () => {
    const node = { children: [], parent: null }
    return [node, node]
  },
})

const findActiveTab = (node: HostNode): unknown => {
  if (node.props?.value) return node.props.value
  for (const child of node.children) {
    const value = findActiveTab(child)
    if (value) return value
  }
  return undefined
}

describe('GameCenter mounted production page', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mount 后遵循 /game-center?tab=emulators 的生产页签语义', async () => {
    const storage = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    })
    const GameCenter = compileGameCenter()
    const root: HostNode = { children: [], parent: null }
    const app = renderer.createApp(GameCenter)
    app.component('ASegmented', {
      props: { value: { type: String, default: '' } },
      setup(props: { value?: string }) {
        return () => h('div', { value: props.value })
      },
    })
    app.mount(root)
    await nextTick()

    expect(findActiveTab(root)).toBe('emulators')

    app.unmount()
  })
})
