import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

// Vue runtime-dom 在模块加载时捕获 document；必须在 import 'vue' 之前提供可变的 document 桩。
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

const __testDir = fileURLToPath(new URL('.', import.meta.url))

/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

// 模拟 vuedraggable：在测试中可以调用 el.__stub.simulateReorder(newOrder) 触发
// start / update:modelValue / end 事件序列。
const DraggableStub = defineComponent({
  name: 'DraggableStub',
  props: ['modelValue', 'itemKey', 'disabled', 'ghostClass', 'chosenClass', 'dragClass', 'handle'],
  emits: ['start', 'end', 'update:modelValue'],
  setup(props: any, { emit, slots }: any) {
    const startDrag = () => emit('start')
    const updateOrder = (newOrder: unknown[]) => emit('update:modelValue', newOrder)
    const endDrag = () => emit('end')
    const simulateReorder = (newOrder: unknown[]) => {
      startDrag()
      updateOrder(newOrder)
      endDrag()
    }

    const setRoot = (el: any) => {
      if (el) {
        el.__stub = { startDrag, updateOrder, endDrag, simulateReorder }
      }
    }

    return () =>
      h(
        'div',
        { ref: setRoot, class: 'draggable-stub' },
        (props.modelValue ?? []).map((element: any, index: number) =>
          slots.item?.({ element, index })
        )
      )
  },
})

// 轻量 ScriptCard 桩：仅渲染 script.id 标识，并暴露 finishUserReorder。
// 在根 DOM 元素上挂 __stub，方便测试调用组件级 emit。
const ScriptCardStub = defineComponent({
  name: 'ScriptCardStub',
  props: ['script', 'activeConnections', 'copyingScriptId', 'searchActive'],
  emits: [
    'edit',
    'delete',
    'copy',
    'addUser',
    'editUser',
    'deleteUser',
    'startSrcConfig',
    'startMaaEndConfig',
    'toggleUserStatus',
    'passCheckUser',
    'toggleCollapsed',
    'userReorder',
  ],
  setup(props: any, { emit, expose }: any) {
    const finishUserReorder = (_success: boolean) => {
      // ScriptCard 真实实现通过 expose 提供 finishUserReorder；桩中无需 emit。
    }
    const simulateUserReorder = (
      scriptId: string,
      userIds: string[],
      previousUserIds: string[]
    ) => {
      emit('userReorder', scriptId, userIds, previousUserIds)
    }

    expose({ finishUserReorder, simulateUserReorder })

    return () =>
      h(
        'div',
        {
          class: 'script-card-stub',
          'data-script-id': props.script.id,
          ref: (el: any) => {
            if (el) {
              el.__stub = { finishUserReorder, simulateUserReorder }
            }
          },
        },
        props.script.name
      )
  },
})

const makeScript = (id: string, name: string) => ({
  id,
  name,
  type: 'M9A',
  available: true,
  users: [],
})

const makeMessage = () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() })

describe('ScriptTable drag reorder', () => {
  let reorderScripts: ReturnType<typeof vi.fn>
  let reorderUsers: ReturnType<typeof vi.fn>
  let messageMock: ReturnType<typeof makeMessage>

  beforeEach(() => {
    const dom = createDom()
    installDomStub(dom)
    reorderScripts = vi.fn()
    reorderUsers = vi.fn()
    messageMock = makeMessage()
  })

  afterEach(() => {
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  const mountTable = (props: Record<string, unknown> = {}) => {
    const ScriptTable = compileSfcComponent(
      '../../../components/ScriptTable.vue',
      {
        vue,
        'ant-design-vue': { message: messageMock },
        vuedraggable: { default: DraggableStub },
        '@/views/scripts/components/ScriptCard.vue': { default: ScriptCardStub },
        '@/composables/useScriptRegistryApi': {
          useScriptRegistryApi: () => ({ reorderScripts, reorderUsers }),
        },
        '@/views/scripts/scriptPageSearch': {
          normalizeScriptSearchQuery: (q: string) => q.trim().toLowerCase(),
        },
        '@/views/scripts/reorderHelpers': {
          isSameOrder: (a: string[], b: string[]) =>
            a.length === b.length && a.every((id, i) => id === b[i]),
          restoreItemOrder: <T extends { id: string }>(
            previousIds: string[],
            sourceOfTruth: T[]
          ): T[] => {
            const map = new Map(sourceOfTruth.map(item => [item.id, item]))
            const restored: T[] = []
            for (const id of previousIds) {
              const item = map.get(id)
              if (item) restored.push(item)
            }
            for (const item of sourceOfTruth) {
              if (!previousIds.includes(item.id)) restored.push(item)
            }
            return restored
          },
        },
      },
      __testDir
    )

    return mountComponent(ScriptTable, {
      scripts: [],
      activeConnections: new Map(),
      ...props,
    })
  }

  it('renders scripts in the order provided by props', async () => {
    const scripts = [makeScript('s1', 'A'), makeScript('s2', 'B'), makeScript('s3', 'C')]
    const { container } = mountTable({ scripts })
    await flush()

    const stubs = findAllByClass(container, 'script-card-stub')
    expect(stubs.map((s: any) => s.attrs['data-script-id'])).toEqual(['s1', 's2', 's3'])
  })

  it('calls reorder API and emits scriptsReordered on successful script drag', async () => {
    const scripts = [makeScript('s1', 'A'), makeScript('s2', 'B'), makeScript('s3', 'C')]
    reorderScripts.mockResolvedValue(undefined)

    const emitted: any[] = []
    const { container } = mountTable({
      scripts,
      onScriptsReordered: (list: any[]) => emitted.push(list.map(s => s.id)),
    })
    await flush()

    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.simulateReorder([scripts[2], scripts[1], scripts[0]])
    await flush()

    expect(reorderScripts).toHaveBeenCalledOnce()
    expect(reorderScripts).toHaveBeenCalledWith(['s3', 's2', 's1'])
    expect(emitted).toEqual([['s3', 's2', 's1']])
  })

  it('keeps the drag DOM order when props refresh between drag start and end', async () => {
    const initial = [makeScript('s1', 'A'), makeScript('s2', 'B'), makeScript('s3', 'C')]
    const refreshed = initial.map(script => ({ ...script, name: `${script.name} refreshed` }))
    reorderScripts.mockResolvedValue(undefined)

    const parentScripts = vue.ref(initial)
    const ScriptTable = compileSfcComponent(
      '../../../components/ScriptTable.vue',
      {
        vue,
        'ant-design-vue': { message: messageMock },
        vuedraggable: { default: DraggableStub },
        '@/views/scripts/components/ScriptCard.vue': { default: ScriptCardStub },
        '@/composables/useScriptRegistryApi': {
          useScriptRegistryApi: () => ({ reorderScripts, reorderUsers }),
        },
        '@/views/scripts/scriptPageSearch': {
          normalizeScriptSearchQuery: (q: string) => q.trim().toLowerCase(),
        },
        '@/views/scripts/reorderHelpers': {
          isSameOrder: (a: string[], b: string[]) =>
            a.length === b.length && a.every((id, i) => id === b[i]),
          restoreItemOrder: <T extends { id: string }>(
            previousIds: string[],
            sourceOfTruth: T[]
          ): T[] => {
            const map = new Map(sourceOfTruth.map(item => [item.id, item]))
            return [
              ...previousIds.flatMap(id => {
                const item = map.get(id)
                return item ? [item] : []
              }),
              ...sourceOfTruth.filter(item => !previousIds.includes(item.id)),
            ]
          },
        },
      },
      __testDir
    )
    const Parent = defineComponent({
      setup() {
        return () =>
          h(ScriptTable, {
            scripts: parentScripts.value,
            activeConnections: new Map(),
            onScriptsReordered: (ordered: any[]) => {
              parentScripts.value = [...ordered]
            },
          })
      },
    })

    const { container } = mountComponent(Parent)
    await flush()
    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.startDrag()
    draggable.__stub.updateOrder([initial[2], initial[1], initial[0]])
    parentScripts.value = refreshed
    await flush()

    expect(
      findAllByClass(container, 'script-card-stub').map((stub: any) => stub.attrs['data-script-id'])
    ).toEqual(['s3', 's2', 's1'])

    draggable.__stub.endDrag()
    await flush()

    expect(reorderScripts).toHaveBeenCalledWith(['s3', 's2', 's1'])
    expect(parentScripts.value.map(script => script.id)).toEqual(['s3', 's2', 's1'])
    expect(parentScripts.value.map(script => script.name)).toEqual([
      'C refreshed',
      'B refreshed',
      'A refreshed',
    ])
  })

  it('restores original order and shows error when reorder API fails', async () => {
    const scripts = [makeScript('s1', 'A'), makeScript('s2', 'B'), makeScript('s3', 'C')]
    reorderScripts.mockRejectedValue(new Error('network error'))

    const { container } = mountTable({ scripts })
    await flush()

    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.simulateReorder([scripts[2], scripts[1], scripts[0]])
    await flush()

    expect(messageMock.error).toHaveBeenCalledWith(expect.stringContaining('脚本排序失败'))
    const stubs = findAllByClass(container, 'script-card-stub')
    expect(stubs.map((s: any) => s.attrs['data-script-id'])).toEqual(['s1', 's2', 's3'])
  })

  it('ignores concurrent drag attempts while a script reorder is in flight', async () => {
    const scripts = [makeScript('s1', 'A'), makeScript('s2', 'B')]
    let resolveReorder: (() => void) | null = null
    reorderScripts.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          resolveReorder = resolve
        })
    )

    const { container } = mountTable({ scripts })
    await flush()

    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.simulateReorder([scripts[1], scripts[0]])
    await flush()

    // 第一次请求尚未完成，第二次重复顺序拖拽应被忽略
    draggable.__stub.simulateReorder([scripts[1], scripts[0]])
    await flush()

    expect(reorderScripts).toHaveBeenCalledTimes(1)
    ;(resolveReorder as (() => void) | null)?.()
    await flush()

    // 第一次完成后，再次拖拽回原始顺序可以触发新请求
    draggable.__stub.simulateReorder([scripts[0], scripts[1]])
    await flush()
    expect(reorderScripts).toHaveBeenCalledTimes(2)
  })

  it('does not call API when the order is unchanged', async () => {
    const scripts = [makeScript('s1', 'A'), makeScript('s2', 'B')]
    reorderScripts.mockResolvedValue(undefined)

    const { container } = mountTable({ scripts })
    await flush()

    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.simulateReorder([scripts[0], scripts[1]])
    await flush()

    expect(reorderScripts).not.toHaveBeenCalled()
  })

  it('calls reorderUsers when a ScriptCard emits userReorder', async () => {
    const userA = { id: 'u1', name: 'A' }
    const userB = { id: 'u2', name: 'B' }
    const scripts = [{ ...makeScript('s1', 'S'), users: [userA, userB] }]
    reorderUsers.mockResolvedValue(undefined)

    const { container } = mountTable({ scripts })
    await flush()

    const card = findByClass(container, 'script-card-stub')
    card.__stub.simulateUserReorder('s1', ['u2', 'u1'], ['u1', 'u2'])
    await flush()

    expect(reorderUsers).toHaveBeenCalledOnce()
    expect(reorderUsers).toHaveBeenCalledWith('s1', ['u2', 'u1'])
  })

  it('shows user reorder error and restores user order via finishUserReorder(false)', async () => {
    const userA = { id: 'u1', name: 'A' }
    const userB = { id: 'u2', name: 'B' }
    const scripts = [{ ...makeScript('s1', 'S'), users: [userA, userB] }]
    reorderUsers.mockRejectedValue(new Error('user reorder failed'))

    const finished: [string, boolean][] = []
    // 用临时桩捕获 finishUserReorder 调用，并继续挂载 __stub 供测试触发 userReorder
    const InstrumentedStub = defineComponent({
      name: 'InstrumentedScriptCardStub',
      props: ['script', 'activeConnections', 'copyingScriptId', 'searchActive'],
      emits: [
        'edit',
        'delete',
        'copy',
        'addUser',
        'editUser',
        'deleteUser',
        'startSrcConfig',
        'startMaaEndConfig',
        'toggleUserStatus',
        'passCheckUser',
        'toggleCollapsed',
        'userReorder',
      ],
      setup(props: any, { emit, expose }: any) {
        const finishUserReorder = (success: boolean) => {
          finished.push([props.script.id, success])
        }
        const simulateUserReorder = (
          scriptId: string,
          userIds: string[],
          previousUserIds: string[]
        ) => {
          emit('userReorder', scriptId, userIds, previousUserIds)
        }
        expose({ finishUserReorder, simulateUserReorder })
        return () =>
          h(
            'div',
            {
              class: 'script-card-stub',
              'data-script-id': props.script.id,
              ref: (el: any) => {
                if (el) {
                  el.__stub = { finishUserReorder, simulateUserReorder }
                }
              },
            },
            props.script.name
          )
      },
    })

    const ScriptTable = compileSfcComponent(
      '../../../components/ScriptTable.vue',
      {
        vue,
        'ant-design-vue': { message: makeMessage() },
        vuedraggable: { default: DraggableStub },
        '@/views/scripts/components/ScriptCard.vue': { default: InstrumentedStub },
        '@/composables/useScriptRegistryApi': {
          useScriptRegistryApi: () => ({ reorderScripts, reorderUsers }),
        },
        '@/views/scripts/scriptPageSearch': {
          normalizeScriptSearchQuery: (q: string) => q.trim().toLowerCase(),
        },
        '@/views/scripts/reorderHelpers': {
          isSameOrder: (a: string[], b: string[]) =>
            a.length === b.length && a.every((id, i) => id === b[i]),
          restoreItemOrder: <T extends { id: string }>(
            previousIds: string[],
            sourceOfTruth: T[]
          ): T[] => {
            const map = new Map(sourceOfTruth.map(item => [item.id, item]))
            const restored: T[] = []
            for (const id of previousIds) {
              const item = map.get(id)
              if (item) restored.push(item)
            }
            for (const item of sourceOfTruth) {
              if (!previousIds.includes(item.id)) restored.push(item)
            }
            return restored
          },
        },
      },
      __testDir
    )

    const { container } = mountComponent(ScriptTable, { scripts, activeConnections: new Map() })
    await flush()

    const card = findByClass(container, 'script-card-stub')
    card.__stub.simulateUserReorder('s1', ['u2', 'u1'], ['u1', 'u2'])
    await flush()

    expect(reorderUsers).toHaveBeenCalledOnce()
    expect(finished).toEqual([['s1', false]])
  })
})
