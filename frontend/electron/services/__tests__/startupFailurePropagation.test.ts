/**
 * 启动失败传播测试。
 *
 * 验证 main.ts 中 did-fail-load 事件处理器能正确向 renderer 发送
 * 结构化 startup-error 消息。
 *
 * 由于需要真实 Electron BrowserWindow，本测试通过检查 main.ts 源码
 * 来验证 did-fail-load 处理器中包含了 startup-error IPC 发送逻辑。
 */

import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

describe('startup failure propagation', () => {
  const servicesDirectory = path.dirname(fileURLToPath(import.meta.url))
  const mainSourcePath = path.resolve(servicesDirectory, '..', '..', 'main.ts')

  it('main.ts sends startup-error IPC on did-fail-load', () => {
    const mainSource = fs.readFileSync(mainSourcePath, 'utf8')

    // 验证 did-fail-load 处理器中包含 startup-error 发送
    expect(mainSource).toContain("'did-fail-load'")
    expect(mainSource).toContain("'startup-error'")
    expect(mainSource).toContain('webContents.send')
    expect(mainSource).toContain('errorCode')
    expect(mainSource).toContain('errorDescription')
  })

  it('startup-error payload includes errorCode, errorDescription and timestamp', () => {
    const mainSource = fs.readFileSync(mainSourcePath, 'utf8')

    // 验证 payload 结构
    expect(mainSource).toMatch(/type:\s*'startup-error'/)
    expect(mainSource).toMatch(/errorCode/)
    expect(mainSource).toMatch(/errorDescription/)
    expect(mainSource).toMatch(/timestamp:\s*Date\.now\(\)/)
  })

  it('preload.ts exposes onStartupError listener', () => {
    const preloadSource = fs.readFileSync(
      path.resolve(servicesDirectory, '..', '..', 'preload.ts'),
      'utf8'
    )

    expect(preloadSource).toContain('onStartupError')
    expect(preloadSource).toContain("'startup-error'")
    expect(preloadSource).toContain('removeStartupErrorListener')
  })

  it('index.html contains startup error fallback UI', () => {
    const indexPath = path.resolve(servicesDirectory, '..', '..', '..', 'index.html')
    const htmlSource = fs.readFileSync(indexPath, 'utf8')
    const fallbackSource = fs.readFileSync(
      path.resolve(servicesDirectory, '..', '..', '..', 'src', 'bootFallback.ts'),
      'utf8'
    )

    // 验证结构化错误 UI
    expect(htmlSource).toContain('app-boot-error')
    expect(htmlSource).toContain('启动失败')
    expect(htmlSource).toContain('/src/bootFallback.ts')
    expect(htmlSource).not.toContain('<script>')
    expect(htmlSource).not.toContain('onclick=')
    expect(fallbackSource).toContain('onStartupError')
    expect(fallbackSource).toContain('has-error')
    // 重试和安全退出按钮
    expect(htmlSource).toContain('重试')
    expect(htmlSource).toContain('安全退出')
  })

  it('electron.d.ts declares StartupErrorPayload type', () => {
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

    expect(typesSource).toContain('StartupErrorPayload')
    expect(typesSource).toContain("type: 'startup-error'")
    expect(typesSource).toContain('onStartupError')
  })
})
