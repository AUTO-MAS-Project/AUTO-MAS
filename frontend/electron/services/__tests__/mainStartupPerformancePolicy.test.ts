import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const servicesDirectory = path.dirname(fileURLToPath(import.meta.url))
const mainSourcePath = path.resolve(servicesDirectory, '..', '..', 'main.ts')
const source = fs.readFileSync(mainSourcePath, 'utf8')

function sourceBetween(start: string, end: string): string {
  const startIndex = source.indexOf(start)
  const endIndex = source.indexOf(end, startIndex + start.length)
  expect(startIndex).toBeGreaterThanOrEqual(0)
  expect(endIndex).toBeGreaterThan(startIndex)
  return source.slice(startIndex, endIndex)
}

describe('main.ts cold-start and hot-path caching policy', () => {
  it('returns the process-memory config memo before touching the filesystem', () => {
    const loadConfigSource = sourceBetween('function loadConfig()', '// 保存配置')
    const cacheGuardIndex = loadConfigSource.indexOf('if (configCache != null)')
    const configPathIndex = loadConfigSource.indexOf('getConfigPath()')

    expect(cacheGuardIndex).toBeGreaterThanOrEqual(0)
    expect(configPathIndex).toBeGreaterThan(cacheGuardIndex)
  })

  it('invalidates the config memo after every frontend_config write', () => {
    const saveConfigSource = sourceBetween('function saveConfig(', '/**')
    const rendererSaveSource = sourceBetween(
      "ipcMain.handle('save-config'",
      '// 新增：实时更新托盘状态的IPC处理器'
    )

    expect(saveConfigSource).toContain('configCache = null')
    expect(rendererSaveSource).toContain('configCache = null')
  })

  it('caches both successful and empty tray icon probe results', () => {
    const traySource = sourceBetween('function resolveTrayIcon()', '// 创建托盘')

    expect(traySource).toContain('if (cachedTrayIcon)')
    expect(traySource).toContain('cachedTrayIcon = trayIcon')
    expect(traySource).not.toMatch(/if \(!trayIcon\.isEmpty\(\)\) \{\s*cachedTrayIcon/)
  })
})
