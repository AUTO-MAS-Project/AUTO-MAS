// P2 回归：1009/4001 协议级终止性关闭后连接层进入 suspended 挂起态，
// 自动重连停止；此前 manualReconnect 只在 devtools 暴露，主界面没有任何
// 用户可见的恢复入口。本测试验证 HomeStatusCard 在 suspended（以及断开且
// 后端多次恢复失败 error）时显示"重新连接"按钮并调用 manualReconnect。

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
import { defineComponent, h, nextTick, ref, type App } from 'vue'
import { fileURLToPath } from 'url'
import type { WSConnectionState } from '@/services/websocket/types'
import {
  compileSfcComponent,
  createDom,
  installDomStub,
  mountComponent,
  uninstallDomStub,
  findByClass,
  type FakeElement,
} from '@/views/scripts/__tests__/mountHelpers'

const testDir = fileURLToPath(new URL('.', import.meta.url))

const IconStub = defineComponent({
  setup() {
    return () => h('span')
  },
})

const CardStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('section', attrs, slots.default?.())
  },
})

const mockConnectionState = ref<WSConnectionState>('open')
const manualReconnectMock = vi.fn<() => Promise<boolean>>()

const HomeStatusCard = compileSfcComponent(
  '../components/HomeStatusCard.vue',
  {
    vue,
    '@ant-design/icons-vue': { ExclamationCircleOutlined: IconStub },
    '@/composables/useWebSocket': {
      useWebSocket: () => ({
        state: mockConnectionState,
        manualReconnect: manualReconnectMock,
      }),
    },
  },
  testDir
)

const baseProps = {
  wsStatus: '已断开',
  backendStatus: 'running',
  isReady: false,
  hasErrors: false,
  queuedTasks: 0,
  recentResults: 0,
}

const mountCard = (props: Partial<typeof baseProps> = {}) =>
  mountComponent(HomeStatusCard, { ...baseProps, ...props }, { 'a-card': CardStub })

describe('HomeStatusCard manual reconnect entry', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    mockConnectionState.value = 'open'
    manualReconnectMock.mockResolvedValue(true)
    installDomStub(createDom())
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('连接正常（open）时不显示重新连接按钮', () => {
    const mounted = mountCard({ wsStatus: '已连接' })
    mountedApp = mounted.app

    expect(findByClass(mounted.container, 'reconnect-btn')).toBeNull()
    expect(mounted.container.textContent).not.toContain('重新连接')
  })

  it('suspended 挂起态显示按钮，点击调用 manualReconnect 并展示重连中状态', async () => {
    mockConnectionState.value = 'suspended'
    let resolveReconnect: (value: boolean) => void = () => {}
    manualReconnectMock.mockImplementation(
      () => new Promise<boolean>(resolve => (resolveReconnect = resolve))
    )

    const mounted = mountCard()
    mountedApp = mounted.app

    const button = findByClass(mounted.container, 'reconnect-btn') as FakeElement | null
    expect(button).not.toBeNull()
    expect(button!.textContent).toContain('重新连接')

    button!.dispatchEvent('click')
    await nextTick()

    expect(manualReconnectMock).toHaveBeenCalledTimes(1)
    expect(mounted.container.textContent).toContain('重连中')

    // 重连期间重复点击不触发并发重连
    button!.dispatchEvent('click')
    expect(manualReconnectMock).toHaveBeenCalledTimes(1)

    resolveReconnect(true)
    await nextTick()
    await Promise.resolve()
    await nextTick()
    expect(mounted.container.textContent).not.toContain('重连中')
  })

  it('断开且后端多次恢复失败（error）时提供兜底重连入口', () => {
    mockConnectionState.value = 'reconnecting'
    const mounted = mountCard({ backendStatus: 'error' })
    mountedApp = mounted.app

    expect(findByClass(mounted.container, 'reconnect-btn')).not.toBeNull()
  })

  it('普通自动重连过程（后端正常）不显示按钮，避免干扰', () => {
    mockConnectionState.value = 'reconnecting'
    const mounted = mountCard({ wsStatus: '连接中', backendStatus: 'running' })
    mountedApp = mounted.app

    expect(findByClass(mounted.container, 'reconnect-btn')).toBeNull()
  })
})
