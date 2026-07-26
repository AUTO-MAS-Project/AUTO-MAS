/**
 * 插件页面/自定义元素/iframe 安全策略。
 *
 * 防止插件内容通过不安全 URL、任意本地路径、allow-scripts + allow-same-origin 组合
 * 以及主文档脚本注入等方式攻击 Electron 主渲染器。
 */

import * as path from 'path'

/** 插件 iframe 允许的 sandbox 属性组合白名单（不含 allow-scripts + allow-same-origin 组合）。 */
const SAFE_IFRAME_SANDBOX_ATTRIBUTES: readonly string[] = [
  'allow-scripts',
  'allow-same-origin',
  'allow-forms',
  'allow-popups',
  'allow-downloads',
]

/** 插件内容的 URL scheme 白名单。 */
const ALLOWED_PLUGIN_SCHEMES: readonly string[] = ['http:', 'https:', 'file:']

/** 插件内容 loadURL 允许的 hostname 白名单（开发态）。 */
const DEV_PLUGIN_HOSTNAME_ALLOWLIST: readonly string[] = ['127.0.0.1', 'localhost']

/** 插件内容 loadFile 允许的根目录（仅限 app 安装目录下的插件资源）。 */
const PLUGIN_FILE_ROOT_DIRS: readonly string[] = []

/**
 * 检查 iframe sandbox 属性是否安全。
 *
 * 不允许 allow-scripts 与 allow-same-origin 同时出现，因为这会使 iframe 可以
 * 移除自身的 sandbox 属性并绕过同源策略。
 */
export function isSafeIframeSandbox(sandboxAttribute: string): boolean {
  if (!sandboxAttribute || sandboxAttribute.trim() === '') {
    return true // 默认 sandbox 最严格
  }

  const tokens = sandboxAttribute.toLowerCase().split(/\s+/).filter(Boolean)

  const hasScripts = tokens.includes('allow-scripts')
  const hasSameOrigin = tokens.includes('allow-same-origin')

  if (hasScripts && hasSameOrigin) {
    return false
  }

  // 检查所有 token 是否在已知安全白名单中
  return tokens.every(token => SAFE_IFRAME_SANDBOX_ATTRIBUTES.includes(token))
}

/**
 * 验证插件页面 URL 是否安全。
 *
 * - 拒绝任意远程 HTTP URL（除非在开发白名单中，由 Lane 05 统一管理）。
 * - 拒绝任意 file: 路径（必须位于插件资源目录内）。
 * - 拒绝 data: / javascript: / blob: 等危险 scheme。
 */
export function isSafePluginUrl(
  candidateUrl: string,
  isPackaged: boolean,
  pluginFileRoots: readonly string[] = PLUGIN_FILE_ROOT_DIRS
): { safe: boolean; reason?: string } {
  try {
    const candidate = new URL(String(candidateUrl || '').trim())

    if (!ALLOWED_PLUGIN_SCHEMES.includes(candidate.protocol)) {
      return { safe: false, reason: `插件 URL scheme 不允许: ${candidate.protocol}` }
    }

    if (candidate.protocol === 'file:') {
      if (!pluginFileRoots.length) {
        return { safe: false, reason: '未配置插件文件根目录，拒绝 file: 协议' }
      }
      const normalizedPath = path.resolve(
        process.platform === 'win32' ? candidate.pathname.replace(/^\//, '') : candidate.pathname
      )
      const isWithinRoot = pluginFileRoots.some(root => {
        const relative = path.relative(path.resolve(root), normalizedPath)
        return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative)
      })
      if (!isWithinRoot) {
        return { safe: false, reason: '插件文件路径不在允许的根目录内' }
      }
    }

    if (candidate.protocol === 'http:' || candidate.protocol === 'https:') {
      if (!isPackaged && DEV_PLUGIN_HOSTNAME_ALLOWLIST.includes(candidate.hostname)) {
        return { safe: true }
      }
      // 生产态不允许任意远程 HTTP URL
      return { safe: false, reason: '生产态不允许插件加载远程 HTTP 内容' }
    }

    return { safe: true }
  } catch {
    return { safe: false, reason: '无效的 URL 格式' }
  }
}

/**
 * 检查 HTML 内容是否包含危险的主文档脚本注入模式。
 *
 * 拒绝包含以下模式的内容：
 * - <script> 标签（可能执行任意 JS）
 * - onerror/onload 等事件处理器属性
 * - javascript: 协议链接
 */
export function hasDangerousScriptInjection(htmlContent: string): boolean {
  const dangerousPatterns = [
    /<script[\s>]/i,
    /\bon\w+\s*=\s*["']/i,
    /javascript\s*:/i,
    /<iframe[\s>]/i,
    /<object[\s>]/i,
    /<embed[\s>]/i,
  ]
  return dangerousPatterns.some(pattern => pattern.test(htmlContent))
}

/** 插件内容安全校验结果。 */
export interface PluginContentSecurityResult {
  safe: boolean
  violations: Array<{ rule: string; detail: string }>
}

/**
 * 综合校验插件内容安全性。
 */
export function validatePluginContent(
  htmlContent: string,
  pluginUrl: string,
  isPackaged: boolean
): PluginContentSecurityResult {
  const violations: Array<{ rule: string; detail: string }> = []

  const urlResult = isSafePluginUrl(pluginUrl, isPackaged)
  if (!urlResult.safe) {
    violations.push({ rule: 'plugin_url_scheme', detail: urlResult.reason || '未知原因' })
  }

  if (hasDangerousScriptInjection(htmlContent)) {
    violations.push({
      rule: 'dangerous_script_injection',
      detail: '插件内容包含 <script>、事件处理器或危险协议链接',
    })
  }

  return {
    safe: violations.length === 0,
    violations,
  }
}
