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

const DraggableStub = defineComponent({
  name: 'DraggableStub',
  props: ['modelValue', 'itemKey', 'disabled', 'ghostClass', 'chosenClass', 'dragClass', 'handle'],
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
        { class: 'draggable-stub', ref: (el: any) => el && (el.__stub = { simulateReorder }) },
        (props.modelValue ?? []).map((element: any, index: number) =>
          slots.item?.({ element, index })
        )
      )
  },
})

const ScriptUserRowStub = defineComponent({
  name: 'ScriptUserRowStub',
  props: ['user', 'operable', 'dragDisabled', 'shouldShow', 'matchKey', 'activeMatch'],
  emits: ['editUser', 'deleteUser', 'toggleUserStatus', 'passCheck'],
  setup(props: any) {
    return () =>
      h(
        'div',
        {
          class: ['user-row-stub', { 'search-match-active': props.activeMatch }],
          'data-user-id': props.user.id,
        },
        props.user.Info?.Name ?? props.user.id
      )
  },
})

const makeIcon = (name: string) =>
  defineComponent({
    name,
    setup() {
      return () => h('span', { class: `icon-${name.toLowerCase()}` }, '')
    },
  })

const ButtonStub = defineComponent({
  name: 'AButton',
  props: ['type', 'disabled', 'loading', 'danger', 'size', 'ghost'],
  emits: ['click'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'button',
        {
          class: `ant-btn ant-btn-${props.type ?? 'default'}`,
          disabled: props.disabled,
          onClick: () => emit('click'),
        },
        slots.default?.()
      )
  },
})

const TagStub = defineComponent({
  name: 'ATag',
  props: ['color'],
  setup(_props: any, { slots }: any) {
    return () => h('span', { class: 'ant-tag' }, slots.default?.())
  },
})

const DropdownStub = defineComponent({
  name: 'ADropdown',
  props: ['trigger'],
  setup(_props: any, { slots }: any) {
    return () => h('div', { class: 'ant-dropdown' }, [slots.default?.(), slots.overlay?.()])
  },
})

const MenuStub = defineComponent({
  name: 'AMenu',
  setup(_props: any, { slots }: any) {
    return () => h('ul', { class: 'ant-menu' }, slots.default?.())
  },
})

const MenuItemStub = defineComponent({
  name: 'AMenuItem',
  props: ['danger'],
  emits: ['click'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'li',
        {
          class: ['ant-menu-item', { 'ant-menu-item-danger': props.danger }],
          onClick: () => emit('click'),
        },
        slots.default?.()
      )
  },
})

const TooltipStub = defineComponent({
  name: 'ATooltip',
  props: ['title'],
  setup(_props: any, { slots }: any) {
    return () => slots.default?.()
  },
})

const SwitchStub = defineComponent({
  name: 'ASwitch',
  props: ['checked', 'disabled'],
  emits: ['click'],
  setup(props: any, { emit }: any) {
    return () =>
      h(
        'button',
        {
          class: 'ant-switch',
          disabled: props.disabled,
          onClick: () => emit('click'),
        },
        props.checked ? '启用' : '禁用'
      )
  },
})

const PopconfirmStub = defineComponent({
  name: 'APopconfirm',
  props: ['title', 'description', 'okText', 'cancelText'],
  emits: ['confirm'],
  setup(_props: any, { slots }: any) {
    return () => h('span', { class: 'ant-popconfirm' }, slots.default?.())
  },
})

const CardStub = defineComponent({
  name: 'ACard',
  props: ['hoverable', 'bodyStyle'],
  setup(_props: any, { slots }: any) {
    return () => h('div', { class: 'ant-card' }, slots.default?.())
  },
})

const EmptyStateStub = defineComponent({
  name: 'EmptyStateStub',
  props: ['title', 'description', 'icon'],
  setup(props: any, { slots }: any) {
    return () =>
      h('div', { class: 'v6-empty-state' }, [
        h('p', { class: 'v6-empty-state__title' }, props.title),
        h('p', { class: 'v6-empty-state__description' }, props.description),
        slots.actions?.(),
      ])
  },
})

const MenuDividerStub = defineComponent({
  name: 'AMenuDivider',
  setup() {
    return () => h('li', { class: 'ant-menu-divider' })
  },
})

const ModalConfirmMocks = {
  confirm: vi.fn(),
}

const makeScript = (overrides: Record<string, unknown> = {}) => ({
  id: 's-1',
  name: 'Test Script',
  type: 'M9A',
  available: true,
  users: [],
  ...overrides,
})

const makeUser = (id: string, name: string) => ({
  id,
  Info: { Name: name, Status: true },
})

describe('ScriptCard component interactions', () => {
  beforeEach(() => {
    const dom = createDom()
    installDomStub(dom)
    ModalConfirmMocks.confirm.mockClear()
  })

  afterEach(() => {
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  const mountCard = (props: Record<string, unknown> = {}) => {
    const antDesignVueStubs = {
      Modal: { confirm: ModalConfirmMocks.confirm },
      Card: CardStub,
      Button: ButtonStub,
      Tag: TagStub,
      Dropdown: DropdownStub,
      Menu: MenuStub,
      MenuItem: MenuItemStub,
      MenuDivider: MenuDividerStub,
      Tooltip: TooltipStub,
      Switch: SwitchStub,
      Popconfirm: PopconfirmStub,
    }

    const ScriptCard = compileSfcComponent(
      './ScriptCard.vue',
      {
        vue,
        'ant-design-vue': antDesignVueStubs,
        '@ant-design/icons-vue': {
          CopyOutlined: makeIcon('CopyOutlined'),
          DeleteOutlined: makeIcon('DeleteOutlined'),
          DownOutlined: makeIcon('DownOutlined'),
          EditOutlined: makeIcon('EditOutlined'),
          EllipsisOutlined: makeIcon('EllipsisOutlined'),
          SettingOutlined: makeIcon('SettingOutlined'),
          UpOutlined: makeIcon('UpOutlined'),
          UserAddOutlined: makeIcon('UserAddOutlined'),
        },
        vuedraggable: { default: DraggableStub },
        '@/utils/scriptRegistry': {
          getScriptIcon: (_type: string, url?: string) => url || '/default.png',
          getScriptTypeTagColor: () => 'blue',
          handleScriptIconError: () => {},
        },
        '@/views/scripts/scriptPageSearch': {
          getScriptSearchMatchKey: (scriptId: string) => `script:${scriptId}`,
          getUserSearchMatchKey: (scriptId: string, userId: string) => `user:${scriptId}:${userId}`,
          matchesScriptOwnSearch: () => true,
          matchesUserSearch: () => true,
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
        '@/components/v6/EmptyState.vue': { default: EmptyStateStub },
        './ScriptUserRow.vue': { default: ScriptUserRowStub },
      },
      __testDir
    )

    // ScriptCard.vue 模板依赖 ant-design-vue 全局组件；在测试环境中通过本地 components 选项注册桩。
    ;(ScriptCard as any).components = {
      ACard: CardStub,
      AButton: ButtonStub,
      ATag: TagStub,
      ADropdown: DropdownStub,
      AMenu: MenuStub,
      AMenuItem: MenuItemStub,
      AMenuDivider: MenuDividerStub,
      ATooltip: TooltipStub,
      ASwitch: SwitchStub,
      APopconfirm: PopconfirmStub,
      'a-card': CardStub,
      'a-button': ButtonStub,
      'a-tag': TagStub,
      'a-dropdown': DropdownStub,
      'a-menu': MenuStub,
      'a-menu-item': MenuItemStub,
      'a-menu-divider': MenuDividerStub,
      'a-tooltip': TooltipStub,
      'a-switch': SwitchStub,
      'a-popconfirm': PopconfirmStub,
    }

    return mountComponent(ScriptCard, {
      script: makeScript(),
      activeConnections: new Map(),
      copyingScriptId: null,
      searchActive: false,
      normalizedSearchKeyword: '',
      activeSearchMatchKey: '',
      collapsed: false,
      registerMatchElement: () => {},
      ...props,
    })
  }

  it('renders script name and type label', async () => {
    const { container } = mountCard({ script: makeScript({ name: 'HSR Daily', type: 'MaaFW' }) })
    await flush()

    expect(container.textContent).toContain('HSR Daily')
    expect(container.textContent).toContain('MaaFW')
  })

  it('emits startSrcConfig when SRC config button is clicked', async () => {
    const events: any[] = []
    const script = makeScript({ type: 'SRC' })
    const { container } = mountCard({
      script,
      onStartSrcConfig: (s: any) => events.push(s),
    })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    const srcButton = buttons.find((b: any) => b.textContent.includes('配置SRC'))
    expect(srcButton).not.toBeUndefined()
    srcButton.dispatchEvent('click')
    await flush()

    expect(events).toEqual([script])
  })

  it('emits startMaaEndConfig when MaaEnd config button is clicked', async () => {
    const events: any[] = []
    const script = makeScript({ type: 'MaaEnd' })
    const { container } = mountCard({
      script,
      onStartMaaEndConfig: (s: any) => events.push(s),
    })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    const maaEndButton = buttons.find((b: any) => b.textContent.includes('配置MaaEnd'))
    expect(maaEndButton).not.toBeUndefined()
    maaEndButton.dispatchEvent('click')
    await flush()

    expect(events).toEqual([script])
  })

  it('emits edit when edit button is clicked', async () => {
    const events: any[] = []
    const script = makeScript()
    const { container } = mountCard({ script, onEdit: (s: any) => events.push(s) })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    const editButton = buttons.find((b: any) => b.textContent.includes('编辑脚本'))
    expect(editButton).not.toBeUndefined()
    editButton.dispatchEvent('click')
    await flush()

    expect(events).toEqual([script])
  })

  it('emits addUser when add user button is clicked', async () => {
    const events: any[] = []
    const script = makeScript()
    const { container } = mountCard({ script, onAddUser: (s: any) => events.push(s) })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    const addButton = buttons.find((b: any) => b.textContent.includes('添加用户'))
    expect(addButton).not.toBeUndefined()
    addButton.dispatchEvent('click')
    await flush()

    expect(events).toEqual([script])
  })

  it('renders a compact Chinese empty state and emits addUser from its primary action', async () => {
    const events: any[] = []
    const script = makeScript({ users: [] })
    const { container } = mountCard({ script, onAddUser: (s: any) => events.push(s) })
    await flush()

    expect(container.textContent).toContain('暂无用户')
    expect(container.textContent).toContain('为此脚本添加首个用户')
    expect(container.textContent).not.toContain('NO DATA')
    const action = findByClass(container, 'empty-users-action')
    expect(action).not.toBeNull()
    action.dispatchEvent('click')
    await flush()

    expect(events).toEqual([script])
  })

  it('shows delete confirm and emits delete on confirmation', async () => {
    let onOkHandler: (() => void) | undefined
    ModalConfirmMocks.confirm.mockImplementation((options: any) => {
      onOkHandler = options.onOk
    })

    const events: any[] = []
    const script = makeScript()
    const { container } = mountCard({ script, onDelete: (s: any) => events.push(s) })
    await flush()

    const menuItems = findAllByClass(container, 'ant-menu-item')
    const deleteItem = menuItems.find((item: any) => item.textContent.includes('删除脚本'))
    expect(deleteItem).not.toBeUndefined()
    deleteItem.dispatchEvent('click')
    await flush()

    expect(ModalConfirmMocks.confirm).toHaveBeenCalledOnce()
    expect(onOkHandler).toBeDefined()
    onOkHandler?.()
    await flush()

    expect(events).toEqual([script])
  })

  it('emits toggleCollapsed when collapse button is clicked', async () => {
    const events: number[] = []
    const { container } = mountCard({ onToggleCollapsed: () => events.push(1) })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    const collapseButton = buttons.find(button => button.attrs['aria-label'] === '收起用户')
    expect(collapseButton).not.toBeUndefined()
    collapseButton.dispatchEvent('click')
    await flush()

    expect(events).toHaveLength(1)
  })

  it('emits userReorder with current and previous user order after drag', async () => {
    const userA = makeUser('u-a', 'A')
    const userB = makeUser('u-b', 'B')
    const script = makeScript({ users: [userA, userB] })

    const events: any[] = []
    const { container } = mountCard({
      script,
      onUserReorder: (scriptId: string, ids: string[], prev: string[]) =>
        events.push({ scriptId, ids, prev }),
    })
    await flush()

    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.simulateReorder([userB, userA])
    await flush()

    expect(events).toEqual([{ scriptId: 's-1', ids: ['u-b', 'u-a'], prev: ['u-a', 'u-b'] }])
  })

  it('does not emit userReorder when user order is unchanged', async () => {
    const userA = makeUser('u-a', 'A')
    const userB = makeUser('u-b', 'B')
    const script = makeScript({ users: [userA, userB] })

    const events: any[] = []
    const { container } = mountCard({
      script,
      onUserReorder: (scriptId: string, ids: string[], prev: string[]) =>
        events.push({ scriptId, ids, prev }),
    })
    await flush()

    const draggable = findByClass(container, 'draggable-stub')
    draggable.__stub.simulateReorder([userA, userB])
    await flush()

    expect(events).toEqual([])
  })

  it('applies search-match-active class when activeSearchMatchKey matches', async () => {
    const { container } = mountCard({
      script: makeScript({ id: 's-active' }),
      activeSearchMatchKey: 'script:s-active',
    })
    await flush()

    const wrapper = findByClass(container, 'script-wrapper')
    expect(wrapper).not.toBeNull()
    const classValue = wrapper.className || wrapper.attrs?.class || ''
    expect(String(classValue)).toContain('search-match-active')
  })

  it('renders the script drag handle with exclusive hot zone', async () => {
    const { container } = mountCard()
    await flush()

    const handle = findByClass(container, 'script-drag-handle')
    expect(handle).not.toBeNull()
    expect(handle.attrs['aria-label']).toBe('拖拽排序')
  })

  it('disables config buttons when script is not available', async () => {
    const script = makeScript({ type: 'SRC', available: false })
    const { container } = mountCard({ script })
    await flush()

    const buttons = findAllByClass(container, 'ant-btn')
    const srcButton = buttons.find((b: any) => b.textContent.includes('配置SRC'))
    expect(srcButton).not.toBeUndefined()
    expect(srcButton.attrs.disabled).toBe('true')
  })
})
