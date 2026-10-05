import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AppearanceCleanupResult } from '@/types/appearance'

const state = vi.hoisted(() => ({
  root: '',
  installed: new Set<string>(),
  handlers: new Map<string, (...args: unknown[]) => unknown>(),
  send: vi.fn(),
}))

vi.mock('electron', () => ({
  app: { getPath: () => path.join(state.root, 'userdata') },
  ipcMain: {
    handle: (channel: string, callback: (...args: unknown[]) => unknown) =>
      state.handlers.set(channel, callback),
  },
  BrowserWindow: {
    getAllWindows: () => [{ isDestroyed: () => false, webContents: { send: state.send } }],
  },
}))
vi.mock('../services/environmentService', () => ({ getAppRoot: () => state.root }))
vi.mock('../services/logger', () => ({
  getLogger: () => ({ info: vi.fn(), warn: vi.fn() }),
}))
vi.mock('../services/appearanceService', () => ({
  getAppearance: (_root: string, id: string) => (state.installed.has(id) ? { id } : null),
  isAppearanceGone: (_root: string, id: string) => !state.installed.has(id),
  listAppearances: () => [],
  importAppearancePackage: vi.fn(),
  removeAppearance: (_root: string, id: string) =>
    state.installed.delete(id) ? { success: true } : { success: false, error: '外观不存在' },
}))

const { registerAppearanceHandlers } = await import('./appearanceHandlers')
const { patchConfigFile } = await import('../utils/configFile')
registerAppearanceHandlers()

const configPath = () => path.join(state.root, 'config', 'frontend_config.json')
const readConfig = () => JSON.parse(fs.readFileSync(configPath(), 'utf8'))
const invoke = (channel: string, id: unknown) => {
  const handler = state.handlers.get(channel)
  if (!handler) throw new Error(`Missing handler: ${channel}`)
  return handler({}, id) as AppearanceCleanupResult
}

beforeEach(() => {
  state.root = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-appearance-ipc-'))
  state.installed.clear()
  state.installed.add('x')
  state.installed.add('y')
  state.send.mockClear()
  patchConfigFile(configPath(), {
    appearanceId: 'x',
    themeMode: 'light',
    themeColor: 'blue',
    UI: { location: '100,100' },
  })
})

afterEach(() => {
  if (
    path.dirname(state.root) !== path.resolve(os.tmpdir()) ||
    !path.basename(state.root).startsWith('auto-mas-appearance-ipc-')
  ) {
    throw new Error('测试清理目录超出临时目录')
  }
  fs.rmSync(state.root, { recursive: true, force: true })
})

describe('appearance config cleanup IPC', () => {
  it('clears the deleted current package and broadcasts the fallback before returning', () => {
    expect(invoke('appearance:remove', 'x').success).toBe(true)
    expect(readConfig()).toEqual({
      appearanceId: null,
      themeMode: 'light',
      themeColor: 'blue',
      UI: { location: '100,100' },
    })
    expect(state.send.mock.calls).toEqual([
      ['theme-config-changed', { appearanceId: null, themeMode: 'light', themeColor: 'blue' }],
      ['appearance-changed'],
    ])
  })

  it('deleting a noncurrent package preserves the latest choice and only broadcasts assets', () => {
    patchConfigFile(configPath(), { appearanceId: 'y' })
    expect(invoke('appearance:remove', 'x').success).toBe(true)
    expect(readConfig().appearanceId).toBe('y')
    expect(state.send.mock.calls).toEqual([['appearance-changed']])
  })

  it('late cleanup of X returns the current Y without clearing or broadcasting a fallback', () => {
    state.installed.delete('x')
    patchConfigFile(configPath(), { appearanceId: 'y' })
    expect(invoke('appearance:clear-invalid', 'x')).toEqual({
      success: true,
      cleared: false,
      appearanceId: 'y',
    })
    expect(readConfig().appearanceId).toBe('y')
    expect(state.send).not.toHaveBeenCalled()
  })

  it('invalid startup cleanup only clears the selected package if it is still invalid', () => {
    expect(invoke('appearance:clear-invalid', 'x')).toEqual({
      success: true,
      cleared: false,
      appearanceId: 'x',
    })
    state.installed.delete('x')
    expect(invoke('appearance:clear-invalid', 'x')).toEqual({
      success: true,
      cleared: true,
      appearanceId: null,
    })
    expect(readConfig().appearanceId).toBe(null)
    expect(state.send).toHaveBeenCalledWith('theme-config-changed', {
      appearanceId: null,
      themeMode: 'light',
      themeColor: 'blue',
    })
  })

  it.each([null, '../x', '', 'X'])('rejects invalid expected package ID %s', id => {
    expect(invoke('appearance:clear-invalid', id).success).toBe(false)
    expect(readConfig().appearanceId).toBe('x')
    expect(state.send).not.toHaveBeenCalled()
  })
})
