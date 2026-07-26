/**
 * “查找/打开日志”定位测试。
 *
 * 真机反馈：后端启动失败时点击“打开日志”，get-app-path('logs') 返回
 * AppData 下不存在的目录，showItemInFolder 抛错后回退到导出日志对话框，
 * 且对话框默认目录不是绿色包自带的 appRoot/debug。
 *
 * 由于 main.ts 的 IPC 处理器依赖真实 Electron 环境，本测试沿用
 * startupFailurePropagation.test.ts 的做法，通过源码契约验证行为。
 */

import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const servicesDirectory = path.dirname(fileURLToPath(import.meta.url))
const mainSource = fs.readFileSync(path.resolve(servicesDirectory, '..', '..', 'main.ts'), 'utf8')
const loggerSource = fs.readFileSync(path.resolve(servicesDirectory, '..', 'logger.ts'), 'utf8')

describe('log dialog location policy', () => {
  it("get-app-path 将 'logs' 定位到 appRoot/debug（与 logger 写入目录同源）", () => {
    const handlerMatch = mainSource.match(/ipcMain\.handle\('get-app-path'[\s\S]*?\n\}\)/)
    expect(handlerMatch).not.toBeNull()
    const handler = handlerMatch![0]

    // 特判 'logs'，返回 getAppRoot() 下的 debug 目录，而不是 app.getPath('logs')
    expect(handler).toMatch(/name === 'logs'/)
    expect(handler).toMatch(/path\.join\(getAppRoot\(\),\s*'debug'\)/)
    // 其余名称仍走 app.getPath
    expect(handler).toMatch(/app\.getPath\(name\)/)

    // 防止与 logger 的实际写入位置发生分叉：logger 也写入 <appRoot>/debug
    expect(loggerSource).toMatch(/path\.join\([^)]*,\s*'debug',\s*'frontend\.log'\)/)
  })

  it('show-item-in-folder 对目录直接打开内部，对文件保持定位选中', () => {
    const handlerMatch = mainSource.match(/ipcMain\.handle\('show-item-in-folder'[\s\S]*?\n\}\)/)
    expect(handlerMatch).not.toBeNull()
    const handler = handlerMatch![0]

    // 目录（如 appRoot/debug）用 shell.openPath 打开目录内部
    expect(handler).toMatch(/isDirectory\(\)/)
    expect(handler).toMatch(/shell\.openPath\(resolvedPath\)/)
    // 文件仍用 showItemInFolder 定位并选中
    expect(handler).toMatch(/shell\.showItemInFolder\(resolvedPath\)/)
    // 仍保留存在性校验
    expect(handler).toMatch(/existsSync\(resolvedPath\)/)
  })

  it('log:export 导出对话框默认定位到 appRoot/debug 日志目录', () => {
    const handlerMatch = mainSource.match(/ipcMain\.handle\('log:export'[\s\S]*?\n\}\)/)
    expect(handlerMatch).not.toBeNull()
    const handler = handlerMatch![0]

    // debugDir 由 appRoot 推导
    expect(handler).toMatch(/path\.join\(appRoot,\s*'debug'\)/)
    // showSaveDialog 的 defaultPath 位于 debugDir 内
    expect(handler).toMatch(/defaultPath:\s*path\.join\(debugDir,/)
    // 目录不存在时不弹对话框，直接返回结构化错误
    expect(handler).toMatch(/日志目录不存在/)
  })

  it('启动失败面板“打开日志”链路契约保持一致（面板 → getAppPath → showItemInFolder）', () => {
    const appSource = fs.readFileSync(
      path.resolve(servicesDirectory, '..', '..', '..', 'src', 'App.vue'),
      'utf8'
    )
    const overlaySource = fs.readFileSync(
      path.resolve(
        servicesDirectory,
        '..',
        '..',
        '..',
        'src',
        'components',
        'BackendStartupOverlay.vue'
      ),
      'utf8'
    )

    // 面板按钮文案是“打开日志”（目录），未承诺“下方日志”等内联展示
    expect(overlaySource).toContain('打开日志')
    expect(overlaySource).not.toContain('下方日志')
    // 渲染层通过 getAppPath('logs') + showItemInFolder 打开日志目录
    expect(appSource).toContain("getAppPath('logs')")
    expect(appSource).toContain('showItemInFolder(logsPath)')
  })
})
