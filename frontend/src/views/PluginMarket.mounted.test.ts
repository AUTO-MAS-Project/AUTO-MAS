import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const wsMocks = vi.hoisted(() => ({
  send: vi.fn(),
  request: vi.fn(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  handlers: new Map<string, (message: { type: string; data: unknown }) => void>(),
  state: undefined as import('vue').Ref<string> | undefined,
}))

// 本机版本来自插件网关 plugin_packages（installedVersions.fetchInstalledVersionMap）；
// 默认返回空映射（对应旧行为"版本未上报"），各用例按需覆盖。
const installedVersionsMocks = vi.hoisted(() => ({
  fetchInstalledVersionMap: vi.fn(),
}))

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
  const storage = new Map<string, string>()
  ;(globalThis as { window: unknown }).window = {
    electronAPI: {
      getLogger: () => ({
        debug: vi.fn(),
        info: vi.fn(),
        warn: vi.fn(),
        error: vi.fn(),
      }),
    },
    sessionStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
      clear: () => storage.clear(),
    },
    open: vi.fn(),
  }
  ;(globalThis as { sessionStorage: unknown }).sessionStorage = (
    globalThis as { window: { sessionStorage: unknown } }
  ).window.sessionStorage
})

import * as vue from 'vue'
import * as marketModel from '@/views/plugin-market/marketModel'
import * as marketCache from '@/views/plugin-market/marketCache'
import { defineComponent, h, ref, type App } from 'vue'
import { fileURLToPath } from 'url'
import {
  compileSfcComponent,
  createDom,
  findByClass,
  installDomStub,
  mountComponent,
  uninstallDomStub,
  type FakeElement,
} from '@/views/scripts/__tests__/mountHelpers'

wsMocks.state = ref('open')

const messageMocks = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}

const PassthroughStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('section', attrs, [slots.title?.(), slots.default?.(), slots.extra?.()])
  },
})

const MacLayoutStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () =>
      h('section', attrs, [
        typeof attrs.title === 'string' ? attrs.title : undefined,
        typeof attrs.subtitle === 'string' ? attrs.subtitle : undefined,
        slots.title?.(),
        slots.subtitle?.(),
        slots.header?.(),
        slots.leading?.(),
        slots.default?.(),
        slots.trailing?.(),
        slots.actions?.(),
        slots.footer?.(),
      ])
  },
})

const ButtonStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('button', attrs, slots.default?.())
  },
})

const InputStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs }) {
    return () => h('input', attrs)
  },
})

const PopconfirmStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('div', { class: 'popconfirm-stub', onClick: attrs.onConfirm }, slots.default?.())
  },
})

const PluginErrorBoundaryStub = defineComponent({
  setup(_, { slots }) {
    return () => h('section', { class: 'plugin-error-boundary-stub' }, slots.default?.())
  },
})

const testDir = fileURLToPath(new URL('.', import.meta.url))
const PluginMarket = compileSfcComponent(
  './PluginMarket.vue',
  {
    vue,
    'ant-design-vue': { message: messageMocks },
    '@/composables/useWebSocket': {
      useWebSocket: () => ({
        state: wsMocks.state,
        send: wsMocks.send,
        request: wsMocks.request,
        subscribe: wsMocks.subscribe,
        unsubscribe: wsMocks.unsubscribe,
      }),
    },
    '@/plugins/ui/PluginErrorBoundary.vue': { default: PluginErrorBoundaryStub },
    '@/components/v6/LoadingSkeleton.vue': { default: PassthroughStub },
    '@/components/mac/StatePanel.vue': { default: MacLayoutStub },
    '@/views/plugin-market/marketModel': marketModel,
    '@/views/plugin-market/marketCache': marketCache,
    '@/views/plugin-market/installedVersions': installedVersionsMocks,
    '@/services/websocket/types': {
      WS_ID_PLUGIN_MARKET: 'PluginMarket',
      WS_MARKET_ERROR: 'market.error',
      WS_MARKET_SNAPSHOT_REQUEST: 'market.snapshot.request',
      WS_MARKET_SNAPSHOT_RESPONSE: 'market.snapshot.response',
      WS_PLUGIN_INSTALL_PROGRESS: 'plugin.install.progress',
      WS_PLUGIN_INSTALL_REQUEST: 'plugin.install.request',
      WS_PLUGIN_INSTALL_RESULT: 'plugin.install.result',
      WS_PLUGIN_INSTALLED_SYNC: 'plugin.installed.sync',
      WS_PLUGIN_UNINSTALL_REQUEST: 'plugin.uninstall.request',
      WS_PLUGIN_UNINSTALL_RESULT: 'plugin.uninstall.result',
    },
  },
  testDir
)

const findButtons = (root: FakeElement, label: string): FakeElement[] => {
  const result: FakeElement[] = []
  const walk = (node: FakeElement) => {
    for (const child of node.childNodes as FakeElement[]) {
      if (child.tagName === 'BUTTON' && child.textContent.trim() === label) {
        result.push(child)
      }
      walk(child)
    }
  }
  walk(root)
  return result
}

const snapshotResponse = {
  type: 'market.snapshot.response',
  data: {
    payload: {
      schema_version: 1,
      prefix_tags: ['automas_'],
      fetched_at: '2026-07-25T00:00:00Z',
      items: [
        {
          package: 'automas_installed',
          version: '2.0.0',
          summary: 'installed',
          project_url: '',
          prefix_tag: 'automas_',
        },
        {
          package: 'automas_new',
          version: '1.0.0',
          summary: 'new',
          project_url: '',
          prefix_tag: 'automas_',
        },
      ],
      installed_map: {
        automas_installed: true,
        automas_new: false,
      },
      total: 2,
    },
  },
}

describe('PluginMarket mounted', () => {
  let mountedApp: App<Element> | null = null

  beforeEach(() => {
    installDomStub(createDom())
    wsMocks.handlers.clear()
    wsMocks.send.mockReset().mockReturnValue(true)
    wsMocks.request.mockReset().mockResolvedValue(snapshotResponse)
    installedVersionsMocks.fetchInstalledVersionMap.mockReset().mockResolvedValue({})
    wsMocks.unsubscribe.mockReset()
    wsMocks.subscribe
      .mockReset()
      .mockImplementation(
        (
          filter: { type?: string },
          handler: (message: { type: string; data: unknown }) => void
        ) => {
          if (filter.type) wsMocks.handlers.set(filter.type, handler)
          return `sub-${filter.type || 'all'}`
        }
      )
    if (wsMocks.state) wsMocks.state.value = 'open'
    ;(window.sessionStorage as Storage).clear()
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    uninstallDomStub()
  })

  it('真实挂载并发出安装、升级和卸载请求，成功后刷新快照', async () => {
    // 插件网关上报本机旧版本：应显示真实版本，且"更新到最新版"保持可用
    installedVersionsMocks.fetchInstalledVersionMap.mockResolvedValue({
      automas_installed: '1.9.0',
    })
    const mounted = mountComponent(
      PluginMarket,
      {},
      {
        'a-space': PassthroughStub,
        'a-card': PassthroughStub,
        'a-tag': PassthroughStub,
        'a-alert': PassthroughStub,
        'a-empty': PassthroughStub,
        'a-result': PassthroughStub,
        'a-modal': PassthroughStub,
        'a-form': PassthroughStub,
        'a-form-item': PassthroughStub,
        'a-progress': PassthroughStub,
        'a-button': ButtonStub,
        'a-input': InputStub,
        'a-select': InputStub,
        'a-popconfirm': PopconfirmStub,
      }
    )
    mountedApp = mounted.app
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    await vue.nextTick()

    expect(mounted.container.textContent).toContain('automas_installed')
    expect(mounted.container.textContent).toContain('automas_new')
    expect(findByClass(mounted.container, 'market-shell')).not.toBeNull()
    expect(findByClass(mounted.container, 'market-toolbar')).not.toBeNull()
    expect(findByClass(mounted.container, 'snapshot-bar')).not.toBeNull()
    expect(findByClass(mounted.container, 'connection-pill')).not.toBeNull()
    expect(mounted.container.textContent).toContain('PyPI 仓库')
    expect(mounted.container.textContent).toContain('最新版本2.0.0')
    expect(mounted.container.textContent).toContain('本机版本1.9.0')

    const recommendedTab = findButtons(mounted.container, '推荐')[0]
    const installedTab = findButtons(mounted.container, '已安装')[0]
    expect(recommendedTab?.className).toContain('is-active')
    expect(recommendedTab?.getAttribute('aria-selected')).toBe('true')
    installedTab?.dispatchEvent('click')
    await Promise.resolve()
    expect(installedTab?.className).toContain('is-active')
    expect(installedTab?.getAttribute('aria-selected')).toBe('true')
    expect(recommendedTab?.className || '').not.toContain('is-active')
    recommendedTab?.dispatchEvent('click')
    await Promise.resolve()

    findButtons(mounted.container, '安装')[0]?.dispatchEvent('click')
    findButtons(mounted.container, '更新到最新版')[0]?.dispatchEvent('click')

    expect(wsMocks.send).toHaveBeenCalledWith(
      'PluginMarket',
      'plugin.install.request',
      expect.objectContaining({ package: 'automas_new' })
    )
    expect(wsMocks.send).toHaveBeenCalledWith(
      'PluginMarket',
      'plugin.install.request',
      expect.objectContaining({ package: 'automas_installed' })
    )
    wsMocks.handlers.get('plugin.install.result')?.({
      type: 'plugin.install.result',
      data: {
        status: 'success',
        payload: { package: 'automas_installed', success: true },
      },
    })
    await Promise.resolve()

    expect(wsMocks.request).toHaveBeenCalledTimes(2)

    findByClass(mounted.container, 'popconfirm-stub')?.dispatchEvent('click')
    expect(wsMocks.send).toHaveBeenCalledWith(
      'PluginMarket',
      'plugin.uninstall.request',
      expect.objectContaining({ package: 'automas_installed' })
    )

    wsMocks.handlers.get('plugin.uninstall.result')?.({
      type: 'plugin.uninstall.result',
      data: {
        status: 'success',
        payload: { package: 'automas_installed', success: true },
      },
    })
    await Promise.resolve()

    expect(wsMocks.request).toHaveBeenCalledTimes(3)
  })

  it('本机版本与最新版一致时更新按钮显示"已是最新"并禁用', async () => {
    installedVersionsMocks.fetchInstalledVersionMap.mockResolvedValue({
      automas_installed: '2.0.0',
    })
    const mounted = mountComponent(
      PluginMarket,
      {},
      {
        'a-space': PassthroughStub,
        'a-card': PassthroughStub,
        'a-modal': PassthroughStub,
        'a-form': PassthroughStub,
        'a-form-item': PassthroughStub,
        'a-progress': PassthroughStub,
        'a-button': ButtonStub,
        'a-input': InputStub,
        'a-select': InputStub,
        'a-popconfirm': PopconfirmStub,
      }
    )
    mountedApp = mounted.app
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    await vue.nextTick()

    expect(mounted.container.textContent).toContain('本机版本2.0.0')
    expect(findButtons(mounted.container, '更新到最新版')).toHaveLength(0)
    const upToDateButtons = findButtons(mounted.container, '已是最新')
    expect(upToDateButtons.length).toBeGreaterThanOrEqual(1)
    // 真实 DOM 中 disabled 按钮不会触发点击；这里断言禁用属性已落到按钮上
    for (const button of upToDateButtons) {
      expect(button.getAttribute('disabled')).not.toBeNull()
    }
  })

  it('安装和卸载失败时停止 loading，并保留操作前的安装状态', async () => {
    const mounted = mountComponent(
      PluginMarket,
      {},
      {
        'a-space': PassthroughStub,
        'a-card': PassthroughStub,
        'a-modal': PassthroughStub,
        'a-form': PassthroughStub,
        'a-form-item': PassthroughStub,
        'a-progress': PassthroughStub,
        'a-button': ButtonStub,
        'a-input': InputStub,
        'a-select': InputStub,
        'a-popconfirm': PopconfirmStub,
      }
    )
    mountedApp = mounted.app
    await Promise.resolve()
    await Promise.resolve()

    findButtons(mounted.container, '安装')[0]?.dispatchEvent('click')
    wsMocks.handlers.get('plugin.install.result')?.({
      type: 'plugin.install.result',
      data: {
        status: 'error',
        message: '网络失败',
        payload: { package: 'automas_new', success: false },
      },
    })
    await vue.nextTick()

    expect(mounted.container.textContent).toContain('网络失败')
    expect(mounted.container.textContent).toContain('本机版本未安装')
    expect(findButtons(mounted.container, '安装')).toHaveLength(1)
    expect(wsMocks.request).toHaveBeenCalledTimes(1)

    findByClass(mounted.container, 'popconfirm-stub')?.dispatchEvent('click')
    wsMocks.handlers.get('plugin.uninstall.result')?.({
      type: 'plugin.uninstall.result',
      data: {
        status: 'error',
        message: '卸载失败',
        payload: { package: 'automas_installed', success: false },
      },
    })
    await vue.nextTick()

    expect(mounted.container.textContent).toContain('本机版本版本未上报')
    expect(findButtons(mounted.container, '更新到最新版')).toHaveLength(1)
    expect(wsMocks.request).toHaveBeenCalledTimes(1)
  })

  it('断线时展示最近一次成功快照并明确标记离线缓存', async () => {
    if (wsMocks.state) wsMocks.state.value = 'closed'
    ;(window.sessionStorage as Storage).setItem(
      'auto-mas-plugin-market-cache-v1',
      JSON.stringify({
        snapshot: snapshotResponse.data.payload,
        saved_at: '2026-07-25T00:01:00Z',
      })
    )

    const mounted = mountComponent(
      PluginMarket,
      {},
      {
        'a-space': PassthroughStub,
        'a-card': PassthroughStub,
        'a-modal': PassthroughStub,
        'a-form': PassthroughStub,
        'a-form-item': PassthroughStub,
        'a-progress': PassthroughStub,
        'a-button': ButtonStub,
        'a-input': InputStub,
        'a-select': InputStub,
        'a-popconfirm': PopconfirmStub,
      }
    )
    mountedApp = mounted.app
    await Promise.resolve()
    await Promise.resolve()

    expect(mounted.container.textContent).toContain('automas_installed')
    expect(mounted.container.textContent).toContain('离线缓存')
    expect(mounted.container.textContent).toContain('已加载本地缓存')
    expect(wsMocks.request).not.toHaveBeenCalled()
  })

  it('断线时保留离线状态，并在连接恢复后自动获取快照', async () => {
    if (wsMocks.state) wsMocks.state.value = 'closed'

    const mounted = mountComponent(
      PluginMarket,
      {},
      {
        'a-space': PassthroughStub,
        'a-card': PassthroughStub,
        'a-modal': PassthroughStub,
        'a-form': PassthroughStub,
        'a-form-item': PassthroughStub,
        'a-progress': PassthroughStub,
        'a-button': ButtonStub,
        'a-input': InputStub,
        'a-select': InputStub,
        'a-popconfirm': PopconfirmStub,
      }
    )
    mountedApp = mounted.app
    await Promise.resolve()
    await Promise.resolve()

    expect(mounted.container.textContent).toContain('市场操作已暂时禁用')
    expect(mounted.container.textContent).toContain('等待与后端建立连接后获取市场数据')
    expect(wsMocks.request).not.toHaveBeenCalled()

    if (wsMocks.state) wsMocks.state.value = 'open'
    await vue.nextTick()
    await Promise.resolve()
    await Promise.resolve()

    expect(wsMocks.request).toHaveBeenCalledTimes(1)
    expect(mounted.container.textContent).toContain('automas_installed')
  })
})
