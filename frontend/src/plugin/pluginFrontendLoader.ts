import { OpenAPI } from '@/api'
import type { PageDeclaration } from '@/router/pageDeclarations'
import * as VueRuntime from 'vue'

const logger = window.electronAPI.getLogger('插件前端加载器')

const PLUGIN_RESOURCE_LOAD_TIMEOUT_MS = 8000
const loadedEntries = new Map<string, Promise<void>>()
const loadedStyles = new Map<string, LoadedStyle>()

interface LoadedStyle {
  link: HTMLLinkElement
  loading: Promise<void>
  references: number
}

export type PluginFrontendPageRelease = () => void

function toAbsoluteUrl(rawUrl: string): string {
  if (/^https?:\/\//i.test(rawUrl)) {
    return rawUrl
  }
  if (import.meta.env.DEV && rawUrl.startsWith('/@fs/')) {
    return `${window.location.origin}${rawUrl}`
  }
  const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
  const path = rawUrl.startsWith('/') ? rawUrl : `/${rawUrl}`
  return `${base}${path}`
}

function releaseStyle(url: string, style: LoadedStyle): void {
  if (style.references > 0) {
    style.references -= 1
  }
  if (style.references > 0 || loadedStyles.get(url) !== style) {
    return
  }

  loadedStyles.delete(url)
  style.link.remove()
}

async function acquireStyle(url: string): Promise<PluginFrontendPageRelease> {
  let style = loadedStyles.get(url)
  if (!style) {
    const link = document.createElement('link')
    const loading = new Promise<void>((resolve, reject) => {
      let settled = false
      const finish = (callback: () => void) => {
        if (settled) {
          return
        }
        settled = true
        window.clearTimeout(timeout)
        link.onload = null
        link.onerror = null
        callback()
      }
      const timeout = window.setTimeout(() => {
        finish(() =>
          reject(new Error(`插件前端样式加载超时（${PLUGIN_RESOURCE_LOAD_TIMEOUT_MS}ms）: ${url}`))
        )
      }, PLUGIN_RESOURCE_LOAD_TIMEOUT_MS)

      link.onload = () => finish(resolve)
      link.onerror = () => finish(() => reject(new Error(`插件前端样式加载失败: ${url}`)))
    })
    style = { link, loading, references: 0 }
    loadedStyles.set(url, style)

    link.rel = 'stylesheet'
    link.href = url
    link.dataset.pluginStyle = url
    document.head.appendChild(link)
  }

  style.references += 1
  const acquiredStyle = style

  try {
    await acquiredStyle.loading
  } catch (error) {
    releaseStyle(url, acquiredStyle)
    throw error
  }

  let released = false
  return () => {
    if (released) {
      return
    }
    released = true
    releaseStyle(url, acquiredStyle)
  }
}

async function acquireStyles(urls: string[]): Promise<PluginFrontendPageRelease> {
  const releases: PluginFrontendPageRelease[] = []
  try {
    for (const url of urls) {
      releases.push(await acquireStyle(url))
    }
  } catch (error) {
    for (const release of releases.reverse()) {
      release()
    }
    throw error
  }

  let released = false
  return () => {
    if (released) {
      return
    }
    released = true
    for (const release of releases.reverse()) {
      release()
    }
  }
}

function removeFailedElement(element: HTMLElement): void {
  if (element.parentNode) {
    element.parentNode.removeChild(element)
  }
}

function loadEntryScript(url: string, cacheKey: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    let settled = false
    const finish = (callback: () => void) => {
      if (settled) {
        return
      }
      settled = true
      window.clearTimeout(timeout)
      script.onload = null
      script.onerror = null
      callback()
    }
    const rejectAndRemove = (error: Error) => {
      removeFailedElement(script)
      finish(() => reject(error))
    }
    const timeout = window.setTimeout(() => {
      rejectAndRemove(
        new Error(`插件前端入口脚本加载超时（${PLUGIN_RESOURCE_LOAD_TIMEOUT_MS}ms）: ${url}`)
      )
    }, PLUGIN_RESOURCE_LOAD_TIMEOUT_MS)

    script.type = 'module'
    script.async = true
    script.src = url
    script.dataset.pluginEntry = cacheKey
    script.onload = () => finish(resolve)
    script.onerror = () => {
      rejectAndRemove(
        new Error(
          `插件前端入口脚本加载失败: ${url}。如果这是开发入口，请确认主前端 Vite 正在运行，且 vite.config.ts 允许访问插件源码目录。`
        )
      )
    }
    document.head.appendChild(script)
  })
}

function exposeVueRuntime(): void {
  const pluginVueKey = '__AUTO_MAS_PLUGIN_VUE__'
  if (pluginVueKey in window) {
    return
  }

  Object.defineProperty(window, pluginVueKey, {
    value: VueRuntime,
    writable: false,
    configurable: false,
    enumerable: false,
  })
}

function combineReleases(releases: PluginFrontendPageRelease[]): PluginFrontendPageRelease {
  let released = false
  return () => {
    if (released) {
      return
    }
    released = true
    for (const release of releases.reverse()) {
      release()
    }
  }
}

async function loadPluginEntry(page: PageDeclaration, entryUrl: string): Promise<void> {
  const isDevEntry =
    import.meta.env.DEV &&
    (/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|::1)(:|\/)/i.test(entryUrl) ||
      entryUrl.includes('/@fs/'))
  const cacheKey = isDevEntry
    ? `${page.frontend_plugin}:dev:${entryUrl}`
    : `${page.frontend_plugin}:${page.manifest_version || 0}:${entryUrl}`

  let loadingTask = loadedEntries.get(cacheKey)
  if (!loadingTask) {
    loadingTask = loadEntryScript(entryUrl, cacheKey).catch(error => {
      loadedEntries.delete(cacheKey)
      throw error
    })
    loadedEntries.set(cacheKey, loadingTask)
  }

  logger.info(`加载插件前端页面: ${cacheKey}`)
  await loadingTask
}

export async function ensurePluginFrontendPage(
  page: PageDeclaration
): Promise<PluginFrontendPageRelease> {
  if (page.renderer !== 'custom-element') {
    return () => {}
  }
  if (!page.frontend_plugin) {
    throw new Error('页面缺少 frontend_plugin')
  }
  if (!page.entry_asset_url) {
    throw new Error('页面缺少 entry_asset_url')
  }
  if (!page.element_tag) {
    throw new Error('页面缺少 element_tag')
  }
  if (page.dev_frontend_error) {
    throw new Error(page.dev_frontend_error)
  }

  exposeVueRuntime()

  const releaseStyles = await acquireStyles(
    page.style_asset_urls.map(styleUrl => toAbsoluteUrl(styleUrl))
  )
  const releasePage = combineReleases([releaseStyles])

  try {
    const entryUrl = toAbsoluteUrl(page.entry_asset_url)
    await loadPluginEntry(page, entryUrl)
    await waitForElement(page.element_tag)
    return releasePage
  } catch (error) {
    releasePage()
    throw error
  }
}

async function waitForElement(tag: string, timeoutMs = 8000): Promise<void> {
  if (customElements.get(tag)) {
    return
  }

  await new Promise<void>((resolve, reject) => {
    const start = window.setTimeout(() => {
      window.clearInterval(timer)
      reject(
        new Error(
          `插件前端入口已加载，但 custom element 未注册: ${tag}。请检查入口文件是否调用 customElements.define('${tag}', ...) 且标签名与 manifest 一致。`
        )
      )
    }, timeoutMs)

    const timer = window.setInterval(() => {
      if (!customElements.get(tag)) {
        return
      }
      window.clearTimeout(start)
      window.clearInterval(timer)
      resolve()
    }, 50)
  })
}
