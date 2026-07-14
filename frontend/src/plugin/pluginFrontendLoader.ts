import { OpenAPI } from '@/api'
import type { PageDeclaration } from '@/router/pageDeclarations'
import type { PluginFrontendElementDescriptor } from '@/types/pluginFrontend'
import * as VueRuntime from 'vue'

const logger = window.electronAPI.getLogger('插件前端加载器')

const loadedEntries = new Map<string, Promise<void>>()
const loadedStyles = new Map<string, Promise<void>>()

function toAbsoluteUrl(rawUrl: string): string {
  if (/^https?:\/\//i.test(rawUrl)) {
    return rawUrl
  }
  if (import.meta.env.DEV && rawUrl.startsWith('/@fs/')) {
    return `${window.location.origin}${rawUrl}`
  }
  const base = (OpenAPI.BASE || 'http://localhost:36163').replace(/\/+$/, '')
  const path = rawUrl.startsWith('/') ? rawUrl : `/${rawUrl}`
  return `${base}${path}`
}

function ensureStyle(url: string): Promise<void> {
  const existing = loadedStyles.get(url)
  if (existing) {
    return existing
  }
  const task = new Promise<void>((resolve, reject) => {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = url
    link.dataset.pluginStyle = url
    link.onload = () => resolve()
    link.onerror = () => {
      loadedStyles.delete(url)
      link.remove()
      reject(new Error(`插件前端样式加载失败: ${url}`))
    }
    document.head.appendChild(link)
  })
  loadedStyles.set(url, task)
  return task
}

function loadEntryScript(url: string, cacheKey: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.type = 'module'
    script.async = true
    script.src = url
    script.dataset.pluginEntry = cacheKey
    script.onload = () => resolve()
    script.onerror = () => {
      reject(
        new Error(
          `插件前端入口脚本加载失败: ${url}。如果这是开发入口，请确认主前端 Vite 正在运行，且 vite.config.ts 允许访问插件源码目录。`
        )
      )
    }
    document.head.appendChild(script)
  })
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

export async function ensurePluginFrontendElement(
  descriptor: PluginFrontendElementDescriptor
): Promise<void> {
  if (!descriptor.frontend_plugin) {
    throw new Error('插件前端扩展缺少 frontend_plugin')
  }
  if (!descriptor.entry_asset_url) {
    throw new Error('插件前端扩展缺少 entry_asset_url')
  }
  if (!descriptor.element_tag) {
    throw new Error('插件前端扩展缺少 element_tag')
  }
  if (descriptor.dev_frontend_error) {
    throw new Error(descriptor.dev_frontend_error)
  }

  const entryUrl = toAbsoluteUrl(descriptor.entry_asset_url)
  ;(window as any).__AUTO_MAS_PLUGIN_VUE__ = VueRuntime
  await Promise.all(
    descriptor.style_asset_urls.map(styleUrl => ensureStyle(toAbsoluteUrl(styleUrl)))
  )

  const isDevEntry =
    import.meta.env.DEV &&
    (/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|::1)(:|\/)/i.test(entryUrl) ||
      entryUrl.includes('/@fs/'))
  const cacheKey = isDevEntry
    ? `${descriptor.frontend_plugin}:dev:${entryUrl}`
    : `${descriptor.frontend_plugin}:${descriptor.manifest_version || 0}:${entryUrl}`
  let loadingTask = loadedEntries.get(cacheKey)
  if (!loadingTask) {
    loadingTask = loadEntryScript(entryUrl, cacheKey).catch(error => {
      loadedEntries.delete(cacheKey)
      throw error
    })
    loadedEntries.set(cacheKey, loadingTask)
  }

  logger.info(`加载插件前端扩展: ${cacheKey}`)
  await loadingTask
  await waitForElement(descriptor.element_tag)
}

export async function ensurePluginFrontendPage(page: PageDeclaration): Promise<void> {
  if (page.renderer !== 'custom-element') {
    return
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
  await ensurePluginFrontendElement({
    frontend_plugin: page.frontend_plugin,
    element_tag: page.element_tag,
    entry_asset_url: page.entry_asset_url,
    style_asset_urls: page.style_asset_urls,
    manifest_version: page.manifest_version,
    dev_frontend_command: page.dev_frontend_command,
    dev_frontend_error: page.dev_frontend_error,
  })
}
