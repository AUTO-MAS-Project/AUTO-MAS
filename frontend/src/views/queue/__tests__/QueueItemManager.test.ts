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
  if (typeof (globalThis as any).window === 'undefined') (globalThis as any).window = {}
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
} from '../../scripts/__tests__/mountHelpers'

const testDir = fileURLToPath(new URL('.', import.meta.url))
const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }
const messageMock = { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() }
const serviceMock = {
  getScriptComboxApiInfoComboxScriptPost: vi.fn(),
  updateItemApiQueueItemUpdatePost: vi.fn(),
  addItemApiQueueItemAddPost: vi.fn(),
  deleteItemApiQueueItemDeletePost: vi.fn(),
  reorderItemApiQueueItemOrderPost: vi.fn(),
}

/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

const DraggableStub = defineComponent({
  name: 'DraggableStub',
  props: ['modelValue'],
  emits: ['start', 'end', 'update:modelValue'],
  setup(props: any, { emit, slots }: any) {
    const controls = {
      start: () => emit('start'),
      update: (items: unknown[]) => emit('update:modelValue', items),
      end: (oldIndex = 0, newIndex = 1) => emit('end', { oldIndex, newIndex }),
    }
    return () =>
      h(
        'div',
        {
          class: 'draggable-stub',
          ref: (element: any) => element && (element.__stub = controls),
        },
        (props.modelValue ?? []).map((element: any, index: number) =>
          slots.item?.({ element, index })
        )
      )
  },
})

const CardStub = defineComponent({
  name: 'ACard',
  setup(_props: any, { slots }: any) {
    return () => h('section', { class: 'ant-card' }, [slots.extra?.(), slots.default?.()])
  },
})
const SpaceStub = defineComponent({
  name: 'ASpace',
  setup(_props: any, { slots }: any) {
    return () => h('span', { class: 'ant-space' }, slots.default?.())
  },
})
const TagStub = defineComponent({
  name: 'ATag',
  setup(_props: any, { slots }: any) {
    return () => h('span', { class: 'ant-tag' }, slots.default?.())
  },
})
const ButtonStub = defineComponent({
  name: 'AButton',
  props: ['disabled', 'loading'],
  emits: ['click'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'button',
        { class: 'ant-btn', disabled: props.disabled, onClick: () => emit('click') },
        slots.default?.()
      )
  },
})
const PopconfirmStub = defineComponent({
  name: 'APopconfirm',
  setup(_props: any, { slots }: any) {
    return () => h('span', { class: 'ant-popconfirm' }, slots.default?.())
  },
})
const SelectStub = defineComponent({
  name: 'ASelect',
  props: ['value', 'disabled', 'options'],
  emits: ['change'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'button',
        {
          class: 'select-stub',
          disabled: props.disabled,
          ref: (element: any) =>
            element && (element.__stub = { change: (value: unknown) => emit('change', value) }),
        },
        [String(props.value ?? ''), slots.default?.()]
      )
  },
})
const SelectOptionStub = defineComponent({
  name: 'ASelectOption',
  setup(_props: any, { slots }: any) {
    return () => h('span', slots.default?.())
  },
})
const SwitchStub = defineComponent({
  name: 'ASwitch',
  props: ['checked', 'disabled'],
  emits: ['change'],
  setup(props: any, { emit }: any) {
    return () =>
      h(
        'button',
        {
          class: 'switch-stub',
          disabled: props.disabled,
          ref: (element: any) =>
            element && (element.__stub = { change: (value: unknown) => emit('change', value) }),
        },
        String(Boolean(props.checked))
      )
  },
})
const InputStub = defineComponent({
  name: 'AInput',
  props: ['value', 'disabled'],
  emits: ['blur'],
  setup(props: any, { emit }: any) {
    return () =>
      h('input', {
        class: 'input-stub',
        value: props.value,
        disabled: props.disabled,
        ref: (element: any) =>
          element &&
          (element.__stub = {
            blur: (value: string) => emit('blur', { target: { value } }),
          }),
      })
  },
})
const InputNumberStub = defineComponent({
  name: 'AInputNumber',
  props: ['value', 'disabled'],
  emits: ['change'],
  setup(props: any, { emit }: any) {
    return () =>
      h(
        'button',
        {
          class: 'input-number-stub',
          disabled: props.disabled,
          ref: (element: any) =>
            element && (element.__stub = { change: (value: unknown) => emit('change', value) }),
        },
        String(props.value)
      )
  },
})
const CheckboxGroupStub = defineComponent({
  name: 'ACheckboxGroup',
  props: ['value', 'disabled'],
  emits: ['change'],
  setup(props: any, { emit }: any) {
    return () =>
      h(
        'button',
        {
          class: 'checkbox-group-stub',
          disabled: props.disabled,
          ref: (element: any) =>
            element && (element.__stub = { change: (value: unknown) => emit('change', value) }),
        },
        (props.value ?? []).join(',')
      )
  },
})
const IconStub = defineComponent({ setup: () => () => h('span') })

const makeItem = (overrides: Record<string, unknown> = {}) => ({
  id: 'item-a',
  script: 'script-a',
  scheduleEnabled: true,
  scheduleMode: 'interval',
  scheduleDays: ['Monday'],
  scheduleTime: '08:15',
  intervalMinutes: 30,
  intervalAnchor: 'finish',
  nextRunAt: '2026-07-25 09:00:00',
  lastCycleStartedAt: '2026-07-25 08:00:00',
  lastCycleFinishedAt: '2026-07-25 08:20:00',
  cycleRunId: '12345678-1234-1234-1234-123456789abc',
  cycleState: 'succeeded',
  cycleRevision: 2,
  cycleResult: 'success',
  cycleError: '',
  cycleUpdatedAt: '2026-07-25 08:20:00',
  ...overrides,
})

const mountManager = (props: Record<string, unknown> = {}) => {
  const component = compileSfcComponent(
    '../components/QueueItemManager.vue',
    {
      vue,
      '@/api': { Service: serviceMock },
      'ant-design-vue': { message: messageMock },
      '@ant-design/icons-vue': { DeleteOutlined: IconStub, PlusOutlined: IconStub },
      vuedraggable: { default: DraggableStub },
    },
    testDir
  )
  const components = {
    Draggable: DraggableStub,
    ACard: CardStub,
    ASpace: SpaceStub,
    ATag: TagStub,
    AButton: ButtonStub,
    APopconfirm: PopconfirmStub,
    ASelect: SelectStub,
    ASelectOption: SelectOptionStub,
    ASwitch: SwitchStub,
    AInput: InputStub,
    AInputNumber: InputNumberStub,
    ACheckboxGroup: CheckboxGroupStub,
  }
  Object.assign((component as any).components ?? ((component as any).components = {}), components)
  return mountComponent(
    component,
    {
      queueId: 'queue-a',
      queueItems: [makeItem()],
      cycleEnabled: true,
      ...props,
    },
    components
  )
}

describe('QueueItemManager mounted interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const dom = createDom()
    installDomStub(dom)
    Object.assign(globalThis.window as any, {
      electronAPI: { getLogger: () => logger },
    })
    serviceMock.getScriptComboxApiInfoComboxScriptPost.mockResolvedValue({
      code: 200,
      data: [{ label: '脚本 A', value: 'script-a' }],
    })
    serviceMock.updateItemApiQueueItemUpdatePost.mockResolvedValue({ code: 200 })
    serviceMock.reorderItemApiQueueItemOrderPost.mockResolvedValue({ code: 200 })
  })

  afterEach(() => {
    uninstallDomStub()
  })

  it('渲染规范 Schedule/Data 字段并按 Schedule 根保存', async () => {
    const { container } = mountManager()
    await flush()

    expect(container.textContent).toContain('interval')
    expect(container.textContent).toContain('30')
    expect(container.textContent).toContain('2026-07-25 08:20:00')
    expect(container.textContent).toContain('上次成功')

    const cycleSwitch = findByClass(container, 'switch-stub')
    cycleSwitch.__stub.change(false)
    await flush()
    await flush()

    expect(serviceMock.updateItemApiQueueItemUpdatePost).toHaveBeenCalledWith({
      queueId: 'queue-a',
      queueItemId: 'item-a',
      data: { Schedule: { Enabled: false } },
    })
  })

  it('展示持久化的运行中标识和失败摘要', async () => {
    const running = mountManager({
      queueItems: [
        makeItem({
          cycleState: 'running',
          cycleError: '',
          lastCycleFinishedAt: '2000-01-01 00:00:00',
        }),
      ],
    })
    await flush()

    expect(running.container.textContent).toContain('运行中')
    expect(running.container.textContent).toContain('运行 ID 12345678')
    running.app.unmount()

    const failed = mountManager({
      queueItems: [
        makeItem({
          cycleState: 'failed',
          cycleError: 'InterruptedError: 宿主上次退出时运行未完成',
        }),
      ],
    })
    await flush()

    expect(failed.container.textContent).toContain('上次失败')
    expect(failed.container.textContent).toContain('宿主上次退出时运行未完成')
  })

  it('脚本保存失败时保留原显示和值', async () => {
    serviceMock.updateItemApiQueueItemUpdatePost.mockResolvedValue({
      code: 409,
      message: '队列运行中',
    })
    const { container } = mountManager()
    await flush()

    const scriptSelect = findAllByClass(container, 'select-stub')[0]
    expect(scriptSelect.textContent).toContain('script-a')
    scriptSelect.__stub.change('script-b')
    await flush()
    await flush()

    expect(serviceMock.updateItemApiQueueItemUpdatePost).toHaveBeenCalledWith({
      queueId: 'queue-a',
      queueItemId: 'item-a',
      data: { Info: { ScriptId: 'script-b' } },
    })
    expect(findAllByClass(container, 'select-stub')[0].textContent).toContain('script-a')
  })

  it('拖拽期间忽略父刷新，排序失败后恢复深快照', async () => {
    serviceMock.reorderItemApiQueueItemOrderPost.mockResolvedValue({
      code: 500,
      message: '排序失败',
    })
    const itemA = makeItem()
    const itemB = makeItem({ id: 'item-b', script: 'script-b' })
    const mounted = mountManager({ queueItems: [itemA, itemB] })
    await flush()

    const draggable = findByClass(mounted.container, 'draggable-stub')
    draggable.__stub.start()
    mounted.app._instance!.props.queueItems = [makeItem({ id: 'item-x', script: 'script-x' })]
    await flush()
    expect(findAllByClass(mounted.container, 'select-stub')[0].textContent).toContain('script-a')

    draggable.__stub.update([itemB, itemA])
    draggable.__stub.end(0, 1)
    await flush()
    await flush()

    expect(serviceMock.reorderItemApiQueueItemOrderPost).toHaveBeenCalledWith({
      queueId: 'queue-a',
      indexList: ['item-b', 'item-a'],
    })
    const scripts = findAllByClass(mounted.container, 'select-stub')
      .map(element => element.textContent)
      .filter(text => text.includes('script-'))
    expect(scripts[0]).toContain('script-a')
    expect(scripts[1]).toContain('script-b')
  })
})
