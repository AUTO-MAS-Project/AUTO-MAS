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

import * as vue from 'vue'
import { defineComponent, h } from 'vue'
import { fileURLToPath } from 'url'
import {
  compileSfcComponent,
  createDom,
  findAllByClass,
  findByClass,
  flush,
  installDomStub,
  mountComponent,
  uninstallDomStub,
} from '../__tests__/mountHelpers'

/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

const testDir = fileURLToPath(new URL('.', import.meta.url))

const DraggableStub = defineComponent({
  props: ['modelValue'],
  emits: ['start', 'end', 'update:modelValue'],
  setup(props: any, { emit, slots }: any) {
    const simulateReorder = (newOrder: unknown[]) => {
      emit('start')
      emit('update:modelValue', newOrder)
      emit('end')
    }
    return () =>
      h(
        'div',
        {
          class: 'draggable-stub',
          ref: (element: any) => {
            if (element) element.__stub = { simulateReorder }
          },
        },
        (props.modelValue ?? []).map((element: unknown, index: number) =>
          slots.item?.({ element, index })
        )
      )
  },
})

const MacLayoutStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () =>
      h('section', attrs, [
        typeof attrs.title === 'string' ? h('h2', attrs.title) : undefined,
        typeof attrs.description === 'string' ? h('p', attrs.description) : undefined,
        slots.header?.(),
        slots.actions?.(),
        slots.default?.(),
      ])
  },
})

const ScriptCardStub = defineComponent({
  props: ['script'],
  setup(props: any, { expose }: any) {
    expose({ finishUserReorder: vi.fn() })
    return () =>
      h(
        'div',
        {
          class: 'script-card-stub',
          'data-script-id': props.script.id,
        },
        props.script.name
      )
  },
})

const IconStub = defineComponent({
  setup() {
    return () => h('span', { class: 'icon-stub' })
  },
})

const isSameOrder = (left: string[], right: string[]) =>
  left.length === right.length && left.every((id, index) => id === right[index])

const restoreItemOrder = <T extends { id: string }>(ids: string[], source: T[]) => {
  const order = new Map(ids.map((id, index) => [id, index]))
  return [...source].sort(
    (left, right) =>
      (order.get(left.id) ?? Number.MAX_SAFE_INTEGER) -
      (order.get(right.id) ?? Number.MAX_SAFE_INTEGER)
  )
}

const makeScript = (id: string, name: string, userIds: string[] = []) => ({
  id,
  name,
  type: 'General',
  displayName: '通用脚本',
  available: true,
  iconUrl: undefined,
  users: userIds.map(userId => ({ id: userId, Info: { Status: true } })),
})

describe('ScriptSplitView', () => {
  let reorderScripts: ReturnType<typeof vi.fn>
  let reorderUsers: ReturnType<typeof vi.fn>

  beforeEach(() => {
    installDomStub(createDom())
    reorderScripts = vi.fn().mockResolvedValue(undefined)
    reorderUsers = vi.fn().mockResolvedValue(undefined)
  })

  afterEach(() => {
    uninstallDomStub()
  })

  const mountSplitView = (props: Record<string, unknown>) => {
    const ScriptSplitView = compileSfcComponent(
      './ScriptSplitView.vue',
      {
        vue,
        'ant-design-vue': {
          message: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
        },
        '@ant-design/icons-vue': { MenuOutlined: IconStub },
        vuedraggable: { default: DraggableStub },
        '@/components/mac/Section.vue': { default: MacLayoutStub },
        '@/components/mac/StatePanel.vue': { default: MacLayoutStub },
        './ScriptCard.vue': { default: ScriptCardStub },
        '@/utils/scriptRegistry': {
          getScriptIcon: (_type: string, url?: string) => url || '/default-script.png',
          handleScriptIconError: vi.fn(),
        },
        '@/composables/useScriptRegistryApi': {
          useScriptRegistryApi: () => ({ reorderScripts, reorderUsers }),
        },
        '@/views/scripts/scriptPageSearch': {
          normalizeScriptSearchQuery: (query: string) => query.trim().toLowerCase(),
          getScriptSearchMatchKey: (scriptId: string) => `script:${scriptId}`,
          getUserSearchMatchKey: (scriptId: string, userId: string) => `user:${scriptId}:${userId}`,
        },
        '@/views/scripts/reorderHelpers': { isSameOrder, restoreItemOrder },
      },
      testDir
    )

    return mountComponent(ScriptSplitView, {
      activeConnections: new Map(),
      scripts: [],
      ...props,
    })
  }

  it('renders a master list and switches the detail script on selection', async () => {
    const scripts = [makeScript('s1', '脚本一'), makeScript('s2', '脚本二')]
    const { container } = mountSplitView({ scripts })
    await flush()

    expect(findAllByClass(container, 'script-master-item')).toHaveLength(2)
    expect(findByClass(container, 'script-card-stub')?.attrs['data-script-id']).toBe('s1')

    findAllByClass(container, 'script-master-item')[1].dispatchEvent('click')
    await flush()

    expect(findByClass(container, 'script-card-stub')?.attrs['data-script-id']).toBe('s2')
  })

  it('renders the registry icon URL in the master list', async () => {
    const script = {
      ...makeScript('plugin-script', '插件脚本'),
      type: 'PluginScript',
      displayName: '插件脚本',
      iconUrl: '/api/script-types/PluginScript/icon',
    }
    const { container } = mountSplitView({ scripts: [script] })
    await flush()

    const icon = findByClass(container, 'script-master-icon-image')
    expect(icon).not.toBeNull()
    expect(icon.attrs.src).toBe('/api/script-types/PluginScript/icon')
    expect(icon.attrs.alt).toBe('插件脚本 图标')
  })

  it('persists script drag order through the registry API', async () => {
    const scripts = [makeScript('s1', '脚本一'), makeScript('s2', '脚本二')]
    const { container } = mountSplitView({ scripts })
    await flush()

    findByClass(container, 'draggable-stub').__stub.simulateReorder([scripts[1], scripts[0]])
    await flush()

    expect(reorderScripts).toHaveBeenCalledWith(['s2', 's1'])
  })

  it('selects the owning script for an active user search match', async () => {
    const scripts = [makeScript('s1', '脚本一', ['u1']), makeScript('s2', '脚本二', ['u2'])]
    const { container } = mountSplitView({
      scripts,
      searchKeyword: 'u2',
      activeSearchMatchKey: 'user:s2:u2',
    })
    await flush()

    expect(findByClass(container, 'script-card-stub')?.attrs['data-script-id']).toBe('s2')
  })
})
