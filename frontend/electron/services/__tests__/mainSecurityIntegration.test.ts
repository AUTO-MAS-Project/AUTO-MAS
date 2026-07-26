/**
 * main.ts 安全策略集成验证测试。
 *
 * 通过源码分析验证 main.ts 中已正确集成所有安全策略：
 * - CSP 安装
 * - 权限处理器安装
 * - 导航守卫安装
 * - 新窗口拦截
 * - 插件安全 IPC 通道
 * - 启动超时机制
 * - 后端初始化失败通知
 * - sandbox/contextIsolation/nodeIntegration 配置
 */

import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const servicesDirectory = path.dirname(fileURLToPath(import.meta.url))
const mainSourcePath = path.resolve(servicesDirectory, '..', '..', 'main.ts')

function readMainSource(): string {
  return fs.readFileSync(mainSourcePath, 'utf8')
}

describe('main.ts — Electron 安全配置', () => {
  const source = readMainSource()

  it('sandbox 启用', () => {
    expect(source).toContain('sandbox: true')
  })

  it('contextIsolation 启用', () => {
    expect(source).toContain('contextIsolation: true')
  })

  it('nodeIntegration 禁用', () => {
    expect(source).toContain('nodeIntegration: false')
  })

  it('主窗口 webPreferences 中同时设置三项安全配置', () => {
    // 验证这三项安全配置在同一个 webPreferences 块中
    const webPrefsSection = source.substring(
      source.indexOf('webPreferences:'),
      source.indexOf('webPreferences:') + 400
    )
    expect(webPrefsSection).toContain('sandbox: true')
    expect(webPrefsSection).toContain('contextIsolation: true')
    expect(webPrefsSection).toContain('nodeIntegration: false')
  })

  it('日志窗口也启用 sandbox', () => {
    // 日志窗口的 webPreferences 也应该有安全配置
    const logWindowSection = source.substring(
      source.lastIndexOf('webPreferences:'),
      source.lastIndexOf('webPreferences:') + 400
    )
    expect(logWindowSection).toContain('sandbox: true')
    expect(logWindowSection).toContain('contextIsolation: true')
    expect(logWindowSection).toContain('nodeIntegration: false')
  })
})

describe('main.ts — CSP 安全头安装', () => {
  const source = readMainSource()

  it('在 app.whenReady() 中安装 CSP', () => {
    const readySection = source.substring(
      source.indexOf('app.whenReady'),
      source.indexOf('app.whenReady') + 2000
    )
    expect(readySection).toContain('installCspHeaders')
    expect(readySection).toContain('session.defaultSession')
    expect(readySection).toContain('app.isPackaged')
  })

  it('记录 CSP 安装日志', () => {
    const readySection = source.substring(
      source.indexOf('app.whenReady'),
      source.indexOf('app.whenReady') + 2000
    )
    expect(readySection).toContain('CSP 已安装')
  })
})

describe('main.ts — 权限处理器安装', () => {
  const source = readMainSource()

  it('安装权限请求处理器', () => {
    expect(source).toContain('installPermissionHandler')
    expect(source).toContain('installPermissionCheckHandler')
  })

  it('权限处理器在 app.whenReady() 中调用', () => {
    const readySection = source.substring(
      source.indexOf('app.whenReady'),
      source.indexOf('app.whenReady') + 2000
    )
    expect(readySection).toContain('installPermissionHandler(session.defaultSession)')
    expect(readySection).toContain('installPermissionCheckHandler(session.defaultSession)')
  })

  it('记录权限处理器安装日志', () => {
    const readySection = source.substring(
      source.indexOf('app.whenReady'),
      source.indexOf('app.whenReady') + 2000
    )
    expect(readySection).toContain('权限处理器已安装')
    expect(readySection).toContain('deny-by-default')
  })
})

describe('main.ts — 导航安全', () => {
  const source = readMainSource()

  it('安装渲染器安全策略', () => {
    expect(source).toContain('installRendererSecurity')
  })

  it('包含 will-navigate 守卫', () => {
    expect(source).toContain("'will-navigate'")
    expect(source).toContain("'will-redirect'")
  })

  it('包含 setWindowOpenHandler 拦截新窗口', () => {
    expect(source).toContain('setWindowOpenHandler')
    expect(source).toContain("action: 'deny'")
  })

  it('外部链接通过 shell.openExternal 打开', () => {
    expect(source).toContain('shell.openExternal')
    expect(source).toContain('normalizeExternalNavigation')
  })
})

describe('main.ts — 插件安全校验 IPC', () => {
  const source = readMainSource()

  it('注册 plugin:isSafeIframeSandbox IPC 处理器', () => {
    expect(source).toContain("'plugin:isSafeIframeSandbox'")
    expect(source).toContain('isSafeIframeSandbox')
  })

  it('注册 plugin:isSafePluginUrl IPC 处理器', () => {
    expect(source).toContain("'plugin:isSafePluginUrl'")
    expect(source).toContain('isSafePluginUrl')
  })

  it('注册 plugin:hasDangerousScriptInjection IPC 处理器', () => {
    expect(source).toContain("'plugin:hasDangerousScriptInjection'")
    expect(source).toContain('hasDangerousScriptInjection')
  })

  it('注册 plugin:validatePluginContent IPC 处理器', () => {
    expect(source).toContain("'plugin:validatePluginContent'")
    expect(source).toContain('validatePluginContent')
  })

  it('导入 pluginSecurityPolicy 模块', () => {
    expect(source).toContain("from './services/pluginSecurityPolicy'")
    expect(source).toContain('isSafeIframeSandbox')
    expect(source).toContain('isSafePluginUrl')
    expect(source).toContain('hasDangerousScriptInjection')
    expect(source).toContain('validatePluginContent')
  })
})

describe('main.ts — 启动超时与错误处理', () => {
  const source = readMainSource()

  it('包含页面加载超时机制', () => {
    expect(source).toContain('pageLoadTimeoutMs')
    expect(source).toContain('pageLoadTimedOut')
    expect(source).toContain('pageLoadTimer')
  })

  it('生产态 30 秒超时，开发态 60 秒', () => {
    expect(source).toContain('30_000')
    expect(source).toContain('60_000')
    expect(source).toContain('app.isPackaged ? 30_000 : 60_000')
  })

  it('超时发送 startup-error 错误码 -408', () => {
    expect(source).toContain('-408')
    expect(source).toContain('页面加载超时')
  })

  it('did-finish-load 清除超时计时器', () => {
    expect(source).toContain("'did-finish-load'")
    expect(source).toContain('clearTimeout(pageLoadTimer)')
  })

  it('did-fail-load 发送 startup-error', () => {
    expect(source).toContain("'did-fail-load'")
    expect(source).toContain("'startup-error'")
  })

  it('prewarmBackend 失败发送 startup-error 错误码 -503', () => {
    expect(source).toContain('-503')
    expect(source).toContain('后端服务预热失败')
  })
})

describe('main.ts — 文件访问安全', () => {
  const source = readMainSource()

  it('open-file 使用 resolveRendererFilePath 和 isSafeDocumentPath', () => {
    expect(source).toContain('resolveRendererFilePath')
    expect(source).toContain('isSafeDocumentPath')
  })

  it('show-item-in-folder 使用 resolveRendererFilePath', () => {
    expect(source).toContain("'show-item-in-folder'")
    expect(source).toContain('resolveRendererFilePath')
  })

  it('open-url 使用 normalizeExternalNavigation', () => {
    expect(source).toContain("'open-url'")
    expect(source).toContain('normalizeExternalNavigation')
  })
})

describe('main.ts — 预加载脚本安全', () => {
  const source = readMainSource()

  it('preload.ts 通过 contextBridge 暴露 API', () => {
    const preloadPath = path.resolve(servicesDirectory, '..', '..', 'preload.ts')
    const preloadSource = fs.readFileSync(preloadPath, 'utf8')
    expect(preloadSource).toContain('contextBridge')
    expect(preloadSource).toContain('exposeInMainWorld')
    expect(preloadSource).toContain('process.isMainFrame')
  })

  it('preload.ts 插件安全校验 API 已暴露', () => {
    const preloadPath = path.resolve(servicesDirectory, '..', '..', 'preload.ts')
    const preloadSource = fs.readFileSync(preloadPath, 'utf8')
    expect(preloadSource).toContain('pluginIsSafeIframeSandbox')
    expect(preloadSource).toContain('pluginIsSafePluginUrl')
    expect(preloadSource).toContain('pluginHasDangerousScriptInjection')
    expect(preloadSource).toContain('pluginValidatePluginContent')
    expect(preloadSource).toContain("'plugin:isSafeIframeSandbox'")
    expect(preloadSource).toContain("'plugin:isSafePluginUrl'")
    expect(preloadSource).toContain("'plugin:hasDangerousScriptInjection'")
    expect(preloadSource).toContain("'plugin:validatePluginContent'")
  })
})

describe('main.ts — TypeScript 类型声明', () => {
  it('electron.d.ts 声明了 PluginContentSecurityResult', () => {
    const typesPath = path.resolve(
      servicesDirectory,
      '..',
      '..',
      '..',
      'src',
      'types',
      'electron.d.ts'
    )
    const typesSource = fs.readFileSync(typesPath, 'utf8')
    expect(typesSource).toContain('PluginContentSecurityResult')
    expect(typesSource).toContain('safe: boolean')
    expect(typesSource).toContain('violations:')
  })

  it('electron.d.ts 声明了插件安全校验方法', () => {
    const typesPath = path.resolve(
      servicesDirectory,
      '..',
      '..',
      '..',
      'src',
      'types',
      'electron.d.ts'
    )
    const typesSource = fs.readFileSync(typesPath, 'utf8')
    expect(typesSource).toContain('pluginIsSafeIframeSandbox')
    expect(typesSource).toContain('pluginIsSafePluginUrl')
    expect(typesSource).toContain('pluginHasDangerousScriptInjection')
    expect(typesSource).toContain('pluginValidatePluginContent')
  })
})
