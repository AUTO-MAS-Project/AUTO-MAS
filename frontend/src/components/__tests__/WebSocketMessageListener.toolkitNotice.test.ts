// P1 回归：toolkit.notice 此前全库无订阅者，后端 ArknightsPC 工具连接
// 明日方舟窗口失败（app/MaaFW/ArknightWin32.py, id=ArknightsPCToolkit,
// type=toolkit.notice, data=WSTaskNoticeData）推送后用户"无反应"。
// 本测试验证全局常驻监听组件订阅该消息并按 level 弹出用户可见提示。

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
import { defineComponent, ref, type App } from 'vue'
import { fileURLToPath } from 'url'
import * as wsTypes from '@/services/websocket/types'
import {
  compileSfcComponent,
  createDom,
  installDomStub,
  mountComponent,
  uninstallDomStub,
} from '@/views/scripts/__tests__/mountHelpers'

const testDir = fileURLToPath(new URL('.', import.meta.url))

const NullStub = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }) {
    return () => slots.default?.() ?? null
  },
})

const antMessageMock = {
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
}

interface RecordedSubscription {
  id: string
  filter: { id?: string; type?: string }
  handler: (message: { id?: string; type: string; data?: unknown }) => void
}

let subscriptionCounter = 0
const subscriptions: RecordedSubscription[] = []
const subscribeMock = vi.fn(
  (filter: RecordedSubscription['filter'], handler: RecordedSubscription['handler']) => {
    const id = `sub_${++subscriptionCounter}`
    subscriptions.push({ id, filter, handler })
    return id
  }
)
const unsubscribeMock = vi.fn()

const WebSocketMessageListener = compileSfcComponent(
  '../WebSocketMessageListener.vue',
  {
    vue,
    'ant-design-vue': {
      Modal: NullStub,
      Button: NullStub,
      message: antMessageMock,
    },
    '@/composables/useWebSocket': {
      useWebSocket: () => ({
        subscribe: subscribeMock,
        unsubscribe: unsubscribeMock,
        sendRaw: vi.fn(() => true),
      }),
      normalizeDialogRequestData: () => null,
    },
    '@/composables/useAppLifecycle': {
      useAppLifecycle: () => ({
        initializeAppLifecycle: vi.fn(),
        dialogRequests: ref([]),
        respondDialog: vi.fn(() => true),
      }),
    },
    '@/services/websocket/types': wsTypes,
  },
  testDir
)

const loggerStub = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

const findToolkitSubscription = (): RecordedSubscription | undefined =>
  subscriptions.find(
    subscription =>
      subscription.filter.id === wsTypes.WS_ID_ARKNIGHTS_TOOLKIT &&
      subscription.filter.type === wsTypes.WS_TOOLKIT_NOTICE
  )

describe('WebSocketMessageListener toolkit.notice', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    subscriptions.length = 0
    subscriptionCounter = 0
    installDomStub(createDom())
    ;(globalThis.window as unknown as Record<string, unknown>).electronAPI = {
      getLogger: () => loggerStub,
    }
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
    vi.unstubAllGlobals()
  })

  it('挂载后订阅 ArknightsPCToolkit/toolkit.notice 并把 error 级通知展示给用户', () => {
    const mounted = mountComponent(WebSocketMessageListener)
    mountedApp = mounted.app

    const toolkitSubscription = findToolkitSubscription()
    expect(toolkitSubscription).toBeDefined()

    // 后端真实 payload 形状：WSTaskNoticeData（app/models/schema.py）
    toolkitSubscription!.handler({
      id: wsTypes.WS_ID_ARKNIGHTS_TOOLKIT,
      type: wsTypes.WS_TOOLKIT_NOTICE,
      data: { level: 'error', message: '无法连接明日方舟: 窗口句柄无效' },
    })

    expect(antMessageMock.error).toHaveBeenCalledTimes(1)
    expect(antMessageMock.error).toHaveBeenCalledWith('无法连接明日方舟: 窗口句柄无效')
    expect(antMessageMock.warning).not.toHaveBeenCalled()
    expect(antMessageMock.info).not.toHaveBeenCalled()
  })

  it('warning/info 级按对应样式提示，缺失 message 时使用兜底文案', () => {
    const mounted = mountComponent(WebSocketMessageListener)
    mountedApp = mounted.app

    const toolkitSubscription = findToolkitSubscription()
    expect(toolkitSubscription).toBeDefined()

    toolkitSubscription!.handler({
      id: wsTypes.WS_ID_ARKNIGHTS_TOOLKIT,
      type: wsTypes.WS_TOOLKIT_NOTICE,
      data: { level: 'warning', message: '明日方舟窗口已丢失' },
    })
    expect(antMessageMock.warning).toHaveBeenCalledWith('明日方舟窗口已丢失')

    toolkitSubscription!.handler({
      id: wsTypes.WS_ID_ARKNIGHTS_TOOLKIT,
      type: wsTypes.WS_TOOLKIT_NOTICE,
      data: {},
    })
    expect(antMessageMock.info).toHaveBeenCalledTimes(1)
    expect(antMessageMock.info).toHaveBeenCalledWith('明日方舟工具箱发生未知错误')
    expect(antMessageMock.error).not.toHaveBeenCalled()
  })

  it('卸载时退订工具箱通知，不留下悬挂订阅', () => {
    const mounted = mountComponent(WebSocketMessageListener)
    mountedApp = mounted.app

    const toolkitSubscription = findToolkitSubscription()
    expect(toolkitSubscription).toBeDefined()

    mounted.app.unmount()
    mountedApp = null

    expect(unsubscribeMock).toHaveBeenCalledWith(toolkitSubscription!.id)
  })
})
