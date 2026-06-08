import { OpenAPI } from '@/api'
import type { PageDeclaration } from '@/router/pageDeclarations'
import * as VueRuntime from 'vue'

const logger = window.electronAPI.getLogger('插件前端加载器')

const loadedEntries = new Map<string, Promise<void>>()
const loadedStyles = new Set<string>()

function toAbsoluteUrl(rawUrl: string): string {
  if (/^https?:\/\//i.test(rawUrl)) {
    return rawUrl
  }
  const base = (OpenAPI.BASE || 'http://localhost:36163').replace(/\/+$/, '')
  const path = rawUrl.startsWith('/') ? rawUrl : `/${rawUrl}`
  return `${base}${path}`
}

function ensureStyle(url: string): void {
  if (loadedStyles.has(url)) {
    return
  }
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = url
  link.dataset.pluginStyle = url
  document.head.appendChild(link)
  loadedStyles.add(url)
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
          `插件前端入口脚本加载失败: ${url}。如果这是 Vite 开发入口，请确认插件前端开发服务正在运行。`,
        ),
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
          `插件前端入口已加载，但 custom element 未注册: ${tag}。请检查入口文件是否调用 customElements.define('${tag}', ...) 且标签名与 manifest 一致。`,
        ),
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

  const entryUrl = toAbsoluteUrl(page.entry_asset_url)
  ;(window as any).__AUTO_MAS_PLUGIN_VUE__ = VueRuntime
  for (const styleUrl of page.style_asset_urls) {
    ensureStyle(toAbsoluteUrl(styleUrl))
  }

  const isDevEntry = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|::1)(:|\/)/i.test(entryUrl)
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
  await waitForElement(page.element_tag)
}
