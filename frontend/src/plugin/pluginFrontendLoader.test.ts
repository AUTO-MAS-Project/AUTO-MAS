import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const dom = vi.hoisted(() => {
  interface FakeElement {
    tagName: string
    dataset: Record<string, string>
    parentNode: FakeHead | null
    onload: (() => void) | null
    onerror: (() => void) | null
    rel?: string
    href?: string
    src?: string
    type?: string
    async?: boolean
    remove: () => void
  }

  interface FakeHead {
    children: FakeElement[]
    appendChild: (element: FakeElement) => FakeElement
    removeChild: (element: FakeElement) => FakeElement
  }

  const head: FakeHead = {
    children: [],
    appendChild(element) {
      element.parentNode = head
      head.children.push(element)
      return element
    },
    removeChild(element) {
      const index = head.children.indexOf(element)
      if (index >= 0) {
        head.children.splice(index, 1)
      }
      element.parentNode = null
      return element
    },
  }
  const document = {
    head,
    createElement(tagName: string): FakeElement {
      const element: FakeElement = {
        tagName: tagName.toUpperCase(),
        dataset: {},
        parentNode: null,
        onload: null,
        onerror: null,
        remove: () => {
          element.parentNode?.removeChild(element)
        },
      }
      return element
    },
  }
  const registeredElements = new Set<string>()
  const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn() }
  const window = {
    location: { origin: 'http://localhost:5173' },
    electronAPI: { getLogger: () => logger },
    setTimeout: (handler: TimerHandler, timeout?: number, ...args: unknown[]) =>
      globalThis.setTimeout(handler, timeout, ...args),
    clearTimeout: (timer: ReturnType<typeof setTimeout>) => globalThis.clearTimeout(timer),
    setInterval: (handler: TimerHandler, timeout?: number, ...args: unknown[]) =>
      globalThis.setInterval(handler, timeout, ...args),
    clearInterval: (timer: ReturnType<typeof setInterval>) => globalThis.clearInterval(timer),
  }

  vi.stubGlobal('document', document)
  vi.stubGlobal('window', window)
  vi.stubGlobal('customElements', {
    get: (tag: string) => (registeredElements.has(tag) ? class {} : undefined),
  })

  return { head, registeredElements }
})

vi.mock('@/api', () => ({
  OpenAPI: { BASE: 'http://localhost:36163' },
}))

import type { PageDeclaration } from '@/router/pageDeclarations'
import { ensurePluginFrontendPage } from './pluginFrontendLoader'

function page(overrides: Partial<PageDeclaration> = {}): PageDeclaration {
  return {
    id: 'test-plugin-page',
    path: '/test-plugin-page',
    title: '测试插件页',
    menu_label: '测试插件页',
    icon: 'app',
    component: 'PluginElement',
    renderer: 'custom-element',
    url: null,
    frontend_plugin: 'test-plugin',
    element_tag: 'test-plugin-element',
    entry_asset_url: '/plugins/test-plugin/entry.js',
    style_asset_urls: ['/plugins/test-plugin/style.css'],
    manifest_version: 1,
    dev_frontend_command: null,
    dev_frontend_error: null,
    section: 'main',
    order: 10,
    visible: true,
    dev_only: false,
    source: 'test',
    ...overrides,
  }
}

function elements(tagName: string) {
  return dom.head.children.filter(element => element.tagName === tagName.toUpperCase())
}

beforeEach(() => {
  dom.head.children.splice(0)
  dom.registeredElements.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('pluginFrontendLoader', () => {
  it('在插入 DOM 前拒绝危险入口 URL 和非法 custom element 标签', async () => {
    await expect(
      ensurePluginFrontendPage(
        page({
          entry_asset_url: 'javascript:alert(1)',
          style_asset_urls: [],
        })
      )
    ).rejects.toThrow('插件入口 URL 安全校验失败')
    expect(elements('script')).toHaveLength(0)

    await expect(
      ensurePluginFrontendPage(
        page({
          element_tag: 'div',
          style_asset_urls: [],
        })
      )
    ).rejects.toThrow('element_tag 格式无效')
    expect(elements('script')).toHaveLength(0)
  })

  it('在插入 link 前拒绝危险样式 URL', async () => {
    await expect(
      ensurePluginFrontendPage(
        page({
          style_asset_urls: ['data:text/css,body{}'],
        })
      )
    ).rejects.toThrow('插件样式 URL 安全校验失败')
    expect(elements('link')).toHaveLength(0)
    expect(elements('script')).toHaveLength(0)
  })

  it('样式失败后移除 link，重试成功后在 release 时卸载样式', async () => {
    const declaration = page()
    const firstAttempt = ensurePluginFrontendPage(declaration)
    const failedLink = elements('link')[0]

    expect(failedLink).toBeDefined()
    failedLink.onerror?.()
    await expect(firstAttempt).rejects.toThrow('插件前端样式加载失败')
    expect(elements('link')).toHaveLength(0)

    const retryAttempt = ensurePluginFrontendPage(declaration)
    const loadedLink = elements('link')[0]
    expect(loadedLink).toBeDefined()
    expect(loadedLink).not.toBe(failedLink)
    loadedLink.onload?.()
    await vi.waitFor(() => expect(elements('script')).toHaveLength(1))
    const script = elements('script')[0]
    dom.registeredElements.add(declaration.element_tag!)
    script.onload?.()

    const release = await retryAttempt
    expect(elements('link')).toHaveLength(1)
    release()
    release()
    expect(elements('link')).toHaveLength(0)
  })

  it('入口脚本失败时移除 script 并允许相同 cache key 重试', async () => {
    const declaration = page({
      id: 'script-retry',
      element_tag: 'script-retry-element',
      entry_asset_url: '/plugins/test-plugin/retry-entry.js',
      style_asset_urls: [],
    })
    const firstAttempt = ensurePluginFrontendPage(declaration)
    await vi.waitFor(() => expect(elements('script')).toHaveLength(1))
    const failedScript = elements('script')[0]

    failedScript.onerror?.()
    await expect(firstAttempt).rejects.toThrow('插件前端入口脚本加载失败')
    expect(elements('script')).toHaveLength(0)

    const retryAttempt = ensurePluginFrontendPage(declaration)
    await vi.waitFor(() => expect(elements('script')).toHaveLength(1))
    const loadedScript = elements('script')[0]
    expect(loadedScript).toBeDefined()
    expect(loadedScript).not.toBe(failedScript)
    dom.registeredElements.add(declaration.element_tag!)
    loadedScript.onload?.()

    const release = await retryAttempt
    expect(release).toBeTypeOf('function')
  })

  it('样式请求永不结束时超时、移除 link，并允许重试', async () => {
    vi.useFakeTimers()
    const declaration = page({
      id: 'style-timeout',
      element_tag: 'style-timeout-element',
      entry_asset_url: '/plugins/test-plugin/style-timeout-entry.js',
      style_asset_urls: ['/plugins/test-plugin/style-timeout.css'],
    })

    const firstAttempt = ensurePluginFrontendPage(declaration)
    const firstRejection = expect(firstAttempt).rejects.toThrow('插件前端样式加载超时')
    const timedOutLink = elements('link')[0]
    expect(timedOutLink).toBeDefined()

    await vi.advanceTimersByTimeAsync(8000)
    await firstRejection
    expect(elements('link')).toHaveLength(0)

    const retryAttempt = ensurePluginFrontendPage(declaration)
    const retryLink = elements('link')[0]
    expect(retryLink).toBeDefined()
    expect(retryLink).not.toBe(timedOutLink)
    retryLink.onerror?.()
    await expect(retryAttempt).rejects.toThrow('插件前端样式加载失败')
  })

  it('入口脚本请求永不结束时超时、移除 script，并清除失败缓存', async () => {
    vi.useFakeTimers()
    const declaration = page({
      id: 'script-timeout',
      element_tag: 'script-timeout-element',
      entry_asset_url: '/plugins/test-plugin/script-timeout-entry.js',
      style_asset_urls: [],
    })

    const firstAttempt = ensurePluginFrontendPage(declaration)
    const firstRejection = expect(firstAttempt).rejects.toThrow('插件前端入口脚本加载超时')
    await vi.waitFor(() => expect(elements('script')).toHaveLength(1))
    const timedOutScript = elements('script')[0]

    await vi.advanceTimersByTimeAsync(8000)
    await firstRejection
    expect(elements('script')).toHaveLength(0)

    const retryAttempt = ensurePluginFrontendPage(declaration)
    await vi.waitFor(() => expect(elements('script')).toHaveLength(1))
    const retryScript = elements('script')[0]
    expect(retryScript).toBeDefined()
    expect(retryScript).not.toBe(timedOutScript)
    retryScript.onerror?.()
    await expect(retryAttempt).rejects.toThrow('插件前端入口脚本加载失败')
  })
})
