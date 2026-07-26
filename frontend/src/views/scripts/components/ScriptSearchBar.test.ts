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
import { h, ref, type Component } from 'vue'
import { fileURLToPath } from 'url'
import {
  compileSfcComponent,
  createDom,
  findByClass,
  flush,
  installDomStub,
  mountComponent,
  uninstallDomStub,
} from '../__tests__/mountHelpers'

const __testDir = fileURLToPath(new URL('.', import.meta.url))

const makeIcon = (name: string): Component => ({
  name,
  setup() {
    return () => h('span', { class: `icon-${name.toLowerCase()}` }, '')
  },
})

const Input: Component = {
  name: 'AInput',
  props: ['value', 'allowClear', 'size', 'placeholder'],
  emits: ['update:value', 'compositionstart', 'compositionend', 'keydown'],
  setup(props: any, { emit, expose }: any) {
    const focused = ref(false)
    expose({
      focus: () => {
        focused.value = true
      },
    })
    return () =>
      h('input', {
        class: 'ant-input script-search-input',
        value: props.value ?? '',
        onInput: (e: any) => emit('update:value', e.target.value),
        onCompositionstart: () => emit('compositionstart'),
        onCompositionend: () => emit('compositionend'),
        onKeydown: (e: any) => emit('keydown', e),
        'data-focused': focused.value,
      })
  },
}

const Button: Component = {
  name: 'AButton',
  props: ['type', 'disabled', 'loading', 'size', 'ghost', 'danger'],
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
}

const Tooltip: Component = {
  name: 'ATooltip',
  props: ['title'],
  setup(_props: any, { slots }: any) {
    return () => slots.default?.()
  },
}

const ScriptSearchBar = compileSfcComponent(
  './ScriptSearchBar.vue',
  {
    vue,
    'ant-design-vue': { Input, Button, Tooltip },
    '@ant-design/icons-vue': {
      SearchOutlined: makeIcon('SearchOutlined'),
      CloseOutlined: makeIcon('CloseOutlined'),
      UpOutlined: makeIcon('UpOutlined'),
      DownOutlined: makeIcon('DownOutlined'),
      InfoCircleOutlined: makeIcon('InfoCircleOutlined'),
    },
    '@/views/scripts/scriptPageSearch': {
      getScriptSearchEnterDirection: (event: KeyboardEvent) => {
        if (event.key !== 'Enter' || (event as any).isComposing) return null
        return event.shiftKey ? -1 : 1
      },
    },
  },
  __testDir
)

const antdComponents = {
  AInput: Input,
  AButton: Button,
  ATooltip: Tooltip,
  'a-input': Input,
  'a-button': Button,
  'a-tooltip': Tooltip,
}

const mountSearchBar = (props: Record<string, unknown>) =>
  mountComponent(ScriptSearchBar, props, antdComponents)

describe('ScriptSearchBar component interactions', () => {
  beforeEach(() => {
    const dom = createDom()
    installDomStub(dom)
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn() } })
  })

  afterEach(() => {
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('mounts with initial keyword and emits update:modelValue on input', async () => {
    const updates: string[] = []
    const { container } = mountSearchBar({
      modelValue: 'hsr',
      summary: '1 / 2 个匹配项',
      matchCount: 2,
      dragDisabled: false,
      'onUpdate:modelValue': (v: string) => updates.push(v),
    })
    await flush()

    const input = findByClass(container, 'script-search-input')
    expect(input).not.toBeNull()
    expect(input.attrs.value).toBe('hsr')

    input.dispatchEvent('input', { target: { value: 'ark' } })
    await flush()
    expect(updates).toEqual(['ark'])
  })

  it('buffers IME composition and only emits final value after compositionend', async () => {
    const updates: string[] = []
    const { container } = mountSearchBar({
      modelValue: '',
      summary: '0 个匹配项',
      matchCount: 0,
      dragDisabled: false,
      'onUpdate:modelValue': (v: string) => updates.push(v),
    })
    await flush()

    const input = findByClass(container, 'script-search-input')

    // IME 组合中：输入不应触发 modelValue 更新
    input.dispatchEvent('compositionstart')
    input.dispatchEvent('input', { target: { value: 'にほん' } })
    await flush()
    expect(updates).toEqual([])

    // 组合结束：应发送最终值
    input.dispatchEvent('compositionend')
    await flush()
    expect(updates).toEqual(['にほん'])
  })

  it('emits navigate(1) on Enter and navigate(-1) on Shift+Enter', async () => {
    const navigations: number[] = []
    const { container } = mountSearchBar({
      modelValue: 'daily',
      summary: '1 / 3',
      matchCount: 3,
      dragDisabled: false,
      onNavigate: (dir: number) => navigations.push(dir),
    })
    await flush()

    const input = findByClass(container, 'script-search-input')

    input.dispatchEvent('keydown', { key: 'Enter', shiftKey: false, isComposing: false })
    await flush()
    expect(navigations).toEqual([1])

    input.dispatchEvent('keydown', { key: 'Enter', shiftKey: true, isComposing: false })
    await flush()
    expect(navigations).toEqual([1, -1])
  })

  it('does not navigate while IME is composing', async () => {
    const navigations: number[] = []
    const { container } = mountSearchBar({
      modelValue: '',
      summary: '0 个匹配项',
      matchCount: 0,
      dragDisabled: false,
      onNavigate: (dir: number) => navigations.push(dir),
    })
    await flush()

    const input = findByClass(container, 'script-search-input')
    input.dispatchEvent('keydown', { key: 'Enter', shiftKey: false, isComposing: true })
    await flush()
    expect(navigations).toEqual([])
  })

  it('emits clear when clear button is clicked', async () => {
    const events: string[] = []
    const { container } = mountSearchBar({
      modelValue: 'foo',
      summary: '1 / 1',
      matchCount: 1,
      dragDisabled: false,
      onClear: () => events.push('clear'),
      onClose: () => events.push('close'),
    })
    await flush()

    const buttons = container.childNodes[0].childNodes.filter(
      (n: any) => n.tagName === 'BUTTON'
    ) as any[]
    // 第一个按钮是“清除”链接（modelValue 非空时渲染）
    const clearButton = buttons.find((b: any) =>
      b.childNodes.some((c: any) => c.textContent === '清除')
    )
    expect(clearButton).not.toBeUndefined()
    clearButton.dispatchEvent('click')
    await flush()
    expect(events).toEqual(['clear'])
  })

  it('emits close when close button is clicked', async () => {
    const events: string[] = []
    const { container } = mountSearchBar({
      modelValue: '',
      summary: '共 0 个脚本',
      matchCount: 0,
      dragDisabled: false,
      onClose: () => events.push('close'),
    })
    await flush()

    const buttons = container.childNodes[0].childNodes.filter(
      (n: any) => n.tagName === 'BUTTON'
    ) as any[]
    // 按钮顺序：导航×2、（可选清除）、关闭；关闭按钮始终在最后
    const closeButton = buttons[buttons.length - 1]
    expect(closeButton).not.toBeUndefined()
    closeButton.dispatchEvent('click')
    await flush()
    expect(events).toEqual(['close'])
  })

  it('exposes focus() that delegates to the input', async () => {
    const { app, container } = mountSearchBar({
      modelValue: '',
      summary: '共 0 个脚本',
      matchCount: 0,
      dragDisabled: false,
    })
    await flush()

    const exposed = (app as any)._component?.exposed ?? (app as any)._instance?.exposed
    // 通过组件实例暴露的 focus 方法调用后应标记 input 为 focused
    exposed?.focus()
    await flush()

    const input = findByClass(container, 'script-search-input')
    expect(input.attrs['data-focused']).toBe('true')
  })

  it('no longer renders the removed drag-disabled notice', async () => {
    // 组件已移除 dragDisabled prop 与搜索期间的拖拽提示条,
    // 此断言锁定新行为:传入多余 prop 也不应渲染提示
    const { container } = mountSearchBar({
      modelValue: '',
      summary: '共 0 个脚本',
      matchCount: 0,
      dragDisabled: true,
    })
    await flush()

    const notice = findByClass(container, 'script-search-drag-notice')
    expect(notice).toBeNull()
  })
})
