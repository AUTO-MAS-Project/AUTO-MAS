/**
 * Renderer Content Security Policy (CSP) 服务。
 *
 * 开发态：允许 Vite HMR（WebSocket、eval、inline style）所需的宽松策略。
 * 生产态：严格限制脚本、样式、连接、frame 和媒体来源，不允许 unsafe-eval 或任意远程脚本。
 */

import type { Session } from 'electron'

export interface CspPolicyConfig {
  /** 生产态使用的 CSP 指令集（不含 default-src 头部名称）。 */
  productionDirectives: string
  /** 开发态使用的 CSP 指令集。 */
  developmentDirectives: string
}

const DEFAULT_PRODUCTION_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https: http://127.0.0.1:* http://localhost:*",
  "font-src 'self' data:",
  "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:*",
  "frame-src 'self' http://127.0.0.1:* http://localhost:*",
  "object-src 'none'",
  "media-src 'self'",
  "worker-src 'self'",
  "form-action 'self'",
  "base-uri 'self'",
].join('; ')

const DEFAULT_DEVELOPMENT_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https: http:",
  "font-src 'self' data:",
  "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:*",
  "frame-src 'self' http://127.0.0.1:* http://localhost:*",
  "object-src 'none'",
  "media-src 'self'",
  "worker-src 'self' 'unsafe-eval'",
  "form-action 'self'",
  "base-uri 'self'",
].join('; ')

export function buildCspPolicy(config?: Partial<CspPolicyConfig>): CspPolicyConfig {
  return {
    productionDirectives: config?.productionDirectives ?? DEFAULT_PRODUCTION_CSP,
    developmentDirectives: config?.developmentDirectives ?? DEFAULT_DEVELOPMENT_CSP,
  }
}

/**
 * 在 session 的 webRequest 上安装 CSP 响应头。
 *
 * 生产态：严格的 default CSP。
 * 开发态：放宽 'unsafe-eval' / 'unsafe-inline' 以支持 Vite HMR。
 *
 * 仅在开发态或生产构建已加载主页面后调用；不在嵌套 frame 或插件页面中重复安装。
 */
export function installCspHeaders(session: Session, isPackaged: boolean): void {
  const policy = buildCspPolicy()
  const cspValue = isPackaged ? policy.productionDirectives : policy.developmentDirectives

  session.webRequest.onHeadersReceived((details, callback) => {
    // 主窗口仍禁止被嵌入；插件子页面则由渲染层 URL 白名单和 iframe sandbox
    // 共同隔离。若对子 frame 也注入 DENY，合法的本机插件 UI 会在生产包中
    // 被 Electron 自己拦截。
    const frameProtection: Record<string, string[]> =
      details.resourceType === 'subFrame' ? {} : { 'X-Frame-Options': ['DENY'] }

    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [cspValue],
        'X-Content-Type-Options': ['nosniff'],
        ...frameProtection,
        'Referrer-Policy': ['strict-origin-when-cross-origin'],
      },
    })
  })
}
