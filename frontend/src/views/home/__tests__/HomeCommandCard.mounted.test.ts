import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  if (typeof (globalThis as { document?: unknown }).document === 'undefined') {
    ;(globalThis as { document: unknown }).document = {
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
  if (typeof (globalThis as { window?: unknown }).window === 'undefined') {
    ;(globalThis as { window: unknown }).window = {}
  }
})

import * as vue from 'vue'
import { defineComponent, h, ref, type App } from 'vue'
import { fileURLToPath } from 'url'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import {
  compileSfcComponent,
  createDom,
  installDomStub,
  mountComponent,
  uninstallDomStub,
  type FakeElement,
} from '@/views/scripts/__tests__/mountHelpers'

const testDir = fileURLToPath(new URL('.', import.meta.url))
const IconStub = defineComponent({
  setup() {
    return () => h('span')
  },
})
const mockIsLowPerf = ref(false)
const EncryptedTextStub = defineComponent({
  props: {
    text: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    return () => h('span', { 'data-testid': 'encrypted-title' }, `加密动画：${props.text}`)
  },
})
const HomeCommandCard = compileSfcComponent(
  '../components/HomeCommandCard.vue',
  {
    vue,
    '@ant-design/icons-vue': { PlayCircleOutlined: IconStub },
    '@/api/models/TaskCreateIn': { TaskCreateIn },
    '@/components/inspira/EncryptedText.vue': EncryptedTextStub,
    '@/composables/useLowPerfMode': {
      useLowPerfMode: () => ({ isLowPerf: mockIsLowPerf }),
    },
  },
  testDir
)

const PassthroughStub = defineComponent({
  inheritAttrs: false,
  props: {
    message: {
      type: String,
      default: '',
    },
  },
  setup(props, { attrs, slots }) {
    return () => h('section', attrs, [props.message, slots.default?.(), slots.action?.()])
  },
})

const ButtonStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('button', attrs, slots.default?.())
  },
})

const SelectStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs }) {
    return () => h('select', attrs)
  },
})

const findButton = (root: FakeElement, label: string): FakeElement | null => {
  const walk = (node: FakeElement): FakeElement | null => {
    for (const child of node.childNodes as FakeElement[]) {
      if (child.tagName === 'BUTTON' && child.textContent.includes(label)) {
        return child
      }
      const nested = walk(child)
      if (nested) return nested
    }
    return null
  }
  return walk(root)
}

describe('HomeCommandCard mounted', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    mockIsLowPerf.value = false
    installDomStub(createDom())
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('真实挂载失败态并把重试按钮连接到 retry-start 事件', () => {
    const retryStart = vi.fn()
    const mounted = mountComponent(
      HomeCommandCard,
      {
        commandTitle: '脚本正在运行',
        bootstrapping: false,
        taskOptions: [{ label: '任务 A', value: 'task-a' }],
        modeOptions: [{ label: '自动代理', value: TaskCreateIn.mode.AUTO_PROXY }],
        tasksLoading: false,
        tasksError: null,
        starting: false,
        startError: '调度服务不可用',
        selectedTaskId: 'task-a',
        selectedMode: TaskCreateIn.mode.AUTO_PROXY,
        onRetryStart: retryStart,
      },
      {
        'a-card': PassthroughStub,
        'a-alert': PassthroughStub,
        'a-button': ButtonStub,
        'a-select': SelectStub,
      }
    )
    mountedApp = mounted.app

    expect(mounted.container.textContent).toContain('调度服务不可用')
    const retryButton = findButton(mounted.container, '重试启动')
    expect(retryButton).not.toBeNull()

    retryButton?.dispatchEvent('click')
    expect(retryStart).toHaveBeenCalledTimes(1)
  })

  it('正常性能模式使用 EncryptedText 展示随机业务文案', () => {
    const mounted = mountComponent(
      HomeCommandCard,
      {
        commandTitle: '好东西就要来了',
        bootstrapping: false,
        taskOptions: [],
        modeOptions: [],
        tasksLoading: false,
        tasksError: null,
        starting: false,
        startError: null,
        selectedTaskId: null,
        selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      },
      {
        'a-card': PassthroughStub,
        'a-alert': PassthroughStub,
        'a-button': ButtonStub,
        'a-select': SelectStub,
      }
    )
    mountedApp = mounted.app

    expect(mounted.container.textContent).toContain('加密动画：好东西就要来了')
  })

  it('低性能模式保留文案但禁用 EncryptedText 动画', () => {
    mockIsLowPerf.value = true
    const mounted = mountComponent(
      HomeCommandCard,
      {
        commandTitle: '请稍候，系统正在处理。',
        bootstrapping: false,
        taskOptions: [],
        modeOptions: [],
        tasksLoading: false,
        tasksError: null,
        starting: false,
        startError: null,
        selectedTaskId: null,
        selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      },
      {
        'a-card': PassthroughStub,
        'a-alert': PassthroughStub,
        'a-button': ButtonStub,
        'a-select': SelectStub,
      }
    )
    mountedApp = mounted.app

    expect(mounted.container.textContent).toContain('请稍候，系统正在处理。')
    expect(mounted.container.textContent).not.toContain('加密动画：')
  })

  it('系统要求减少动效时保留文案但禁用 EncryptedText 动画', async () => {
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })
    const mounted = mountComponent(
      HomeCommandCard,
      {
        commandTitle: '正在应用专属脚本设置。',
        bootstrapping: false,
        taskOptions: [],
        modeOptions: [],
        tasksLoading: false,
        tasksError: null,
        starting: false,
        startError: null,
        selectedTaskId: null,
        selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      },
      {
        'a-card': PassthroughStub,
        'a-alert': PassthroughStub,
        'a-button': ButtonStub,
        'a-select': SelectStub,
      }
    )
    mountedApp = mounted.app
    await vue.nextTick()

    expect(mounted.container.textContent).toContain('正在应用专属脚本设置。')
    expect(mounted.container.textContent).not.toContain('加密动画：')
  })
})
