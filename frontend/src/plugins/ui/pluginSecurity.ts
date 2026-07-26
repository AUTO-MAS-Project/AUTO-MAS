/**
 * 插件 UI 安全边界：URL 安全校验、路径越界检测、危险 URL 拒绝。
 *
 * 默认禁止：
 * - 任意远程 HTTP/HTTPS（除非在 allowlist 中）
 * - 任意 file: 协议
 * - 路径越界（../ 等）
 * - 危险协议（javascript:, data:, vbscript:）
 * - 主文档直接脚本注入
 */

import { OpenAPI } from '@/api'

// ---- 允许的 URL 模式 ----

const ALLOWED_PROTOCOLS = new Set(['http:', 'https:'])

const ALLOWED_REMOTE_HOSTS = new Set<string>([])

const FORBIDDEN_PROTOCOLS = new Set(['javascript:', 'data:', 'vbscript:', 'file:'])

// ---- URL 校验结果 ----

export interface UrlValidationResult {
  safe: boolean
  reason?: string
  sanitizedUrl?: string
}

// ---- URL 校验函数 ----

function normalizeUrl(url: string): string {
  return String(url || '').trim()
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]'
}

function getBackendOrigin(): string | null {
  try {
    return new URL(OpenAPI.BASE || 'http://127.0.0.1:36163').origin
  } catch {
    return null
  }
}

/**
 * 校验插件扩展 URL 是否安全。
 * 规则：
 * 1. 拒绝 file:、javascript:、data:、vbscript: 协议
 * 2. 仅允许 http: 和 https:
 * 3. 默认拒绝远程域名（除非在 allowlist 中）
 * 4. 允许 localhost 和 127.0.0.1
 * 5. 允许相对于后端的路径
 * 6. 拒绝路径越界（../）
 */
export function validatePluginUrl(url: string): UrlValidationResult {
  const normalized = normalizeUrl(url)
  if (!normalized) {
    return { safe: false, reason: 'URL 不能为空' }
  }

  // 检查危险协议
  for (const proto of FORBIDDEN_PROTOCOLS) {
    if (normalized.toLowerCase().startsWith(proto)) {
      return { safe: false, reason: `禁止使用 ${proto} 协议` }
    }
  }

  // 协议相对 URL（必须在相对路径检查之前，因为 // 也 startsWith('/')）
  if (normalized.startsWith('//')) {
    return { safe: false, reason: '不允许协议相对 URL (//)' }
  }

  if (normalized.includes('\0')) {
    return { safe: false, reason: 'URL 包含空字节' }
  }

  if (hasPathTraversal(normalized)) {
    return { safe: false, reason: 'URL 包含路径越界 (../)' }
  }

  // 相对路径
  if (normalized.startsWith('/') || !normalized.includes('://')) {
    // 相对路径相对于后端，安全
    const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
    const sanitized = normalized.startsWith('/') ? normalized : `/${normalized}`
    return { safe: true, sanitizedUrl: `${base}${sanitized}` }
  }

  // 绝对 URL
  try {
    const parsed = new URL(normalized)
    const protocol = parsed.protocol

    if (!ALLOWED_PROTOCOLS.has(protocol)) {
      return { safe: false, reason: `不允许 ${protocol} 协议，仅允许 http/https` }
    }

    const hostname = parsed.hostname

    // 允许 localhost
    if (isLoopbackHost(hostname)) {
      return { safe: true, sanitizedUrl: normalized }
    }

    // 允许后端同源。即使后端使用局域网 IP，也只放行同 origin 资源。
    if (parsed.origin === getBackendOrigin()) {
      return { safe: true, sanitizedUrl: normalized }
    }

    // 检查 allowlist
    if (ALLOWED_REMOTE_HOSTS.has(hostname)) {
      return { safe: true, sanitizedUrl: normalized }
    }

    return {
      safe: false,
      reason: `不允许远程域名: ${hostname}，插件扩展 URL 仅允许本地和受信任域名`,
    }
  } catch {
    return { safe: false, reason: `无效的 URL: ${normalized}` }
  }
}

/**
 * 校验插件扩展入口脚本 URL。
 * 比普通 URL 校验更严格：不允许远程 HTTP 脚本。
 */
export function validatePluginEntryUrl(url: string): UrlValidationResult {
  const result = validatePluginUrl(url)
  if (!result.safe) return result

  // 入口脚本不允许远程 HTTP
  const sanitized = result.sanitizedUrl || url
  if (/^https?:\/\//i.test(sanitized)) {
    try {
      const parsed = new URL(sanitized)
      if (!isLoopbackHost(parsed.hostname) && parsed.origin !== getBackendOrigin()) {
        return { safe: false, reason: `插件入口脚本不允许加载远程 URL: ${parsed.hostname}` }
      }
    } catch {
      return { safe: false, reason: `插件入口脚本 URL 解析失败: ${sanitized}` }
    }
  }

  return result
}

/**
 * 校验插件样式资源 URL。
 * 允许后端同源；不允许任意远程 CSS。
 */
export function validatePluginStyleUrl(url: string): UrlValidationResult {
  return validatePluginUrl(url)
}

/**
 * 校验插件 iframe URL。
 * 不允许任意远程 URL；必须经过 URL 白名单审核。
 */
export function validatePluginIframeUrl(url: string): UrlValidationResult {
  return validatePluginUrl(url)
}

/**
 * 批量校验 URL 列表。
 */
export function validatePluginUrls(urls: string[]): UrlValidationResult[] {
  return urls.map(url => validatePluginUrl(url))
}

/**
 * 检查是否为危险 URL 组合（iframe sandbox 绕过）。
 * allow-scripts + allow-same-origin 不允许同时出现在 iframe sandbox 中。
 */
export function isSandboxBypassRisk(sandbox: string): boolean {
  const tokens = sandbox.split(/\s+/).map(t => t.trim().toLowerCase())
  return tokens.includes('allow-scripts') && tokens.includes('allow-same-origin')
}

/**
 * 检查是否为路径越界攻击。
 */
export function hasPathTraversal(path: string): boolean {
  let decoded = path
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const next = decodeURIComponent(decoded)
      if (next === decoded) break
      decoded = next
    } catch {
      return true
    }
  }

  const pathname = decoded.replace(/\\/g, '/').split(/[?#]/, 1)[0]
  return pathname.split('/').some(segment => segment === '..')
}
