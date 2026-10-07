import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AppearanceCleanupResult, LocalAppearanceInspectResult } from '@/types/appearance'

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
  net: { request: vi.fn() },
}))
vi.mock('../services/environmentService', () => ({ getAppRoot: () => state.root }))
vi.mock('../services/logger', () => ({
  getLogger: () => ({ info: vi.fn(), warn: vi.fn() }),
}))
vi.mock('../services/appearanceService', async importOriginal => {
  const actual = await importOriginal<typeof import('../services/appearanceService')>()
  return {
    // 本地包预览走真实的只读校验，其余写目录的操作用内存替身。
    inspectAppearancePackage: actual.inspectAppearancePackage,
    AppearanceError: actual.AppearanceError,
    getAppearance: (_root: string, id: string) => (state.installed.has(id) ? { id } : null),
    isAppearanceGone: (_root: string, id: string) => !state.installed.has(id),
    listAppearances: () => [],
    importAppearancePackage: vi.fn(),
    removeAppearance: (_root: string, id: string) =>
      state.installed.delete(id) ? { success: true } : { success: false, error: '外观不存在' },
  }
})

const { registerAppearanceHandlers } = await import('./appearanceHandlers')
const { patchConfigFile } = await import('../utils/configFile')
// 注册时会清理在线外观缓存目录，先给一个临时根目录，别让它落到当前工作目录的相对路径上。
const bootstrapRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-appearance-ipc-'))
state.root = bootstrapRoot
registerAppearanceHandlers()
fs.rmSync(bootstrapRoot, { recursive: true, force: true })

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

  it('local import and removal drop the online source record of that ID only', async () => {
    const sourcesPath = path.join(state.root, 'userdata', 'appearance-sources.json')
    const source = (fileKey: string) => ({
      origin: 'https://data.auto-mas.top',
      projectKey: 'auto-mas',
      categoryKey: 'theme',
      fileKey,
      versionNo: 3,
      sha256: 'b'.repeat(64),
      installedAt: '2026-10-06T00:00:00.000Z',
    })
    fs.mkdirSync(path.dirname(sourcesPath), { recursive: true })
    fs.writeFileSync(
      sourcesPath,
      JSON.stringify({ schemaVersion: 1, sources: { x: source('fx'), y: source('fy') } })
    )
    const { importAppearancePackage } = await import('../services/appearanceService')
    vi.mocked(importAppearancePackage).mockReturnValueOnce({
      success: true,
      appearance: { id: 'x' } as never,
    })
    const zipPath = path.join(state.root, 'local.zip')
    fs.writeFileSync(zipPath, 'zip')

    const handler = state.handlers.get('appearance:import')!
    expect(handler({}, zipPath, true)).toMatchObject({ success: true })
    const afterImport = JSON.parse(fs.readFileSync(sourcesPath, 'utf8'))
    expect(afterImport.schemaVersion).toBe(1)
    expect(Object.keys(afterImport.sources)).toEqual(['y'])

    expect(invoke('appearance:remove', 'y').success).toBe(true)
    expect(JSON.parse(fs.readFileSync(sourcesPath, 'utf8')).sources).toEqual({})
  })

  it('registers the online appearance channels and rejects wrongly typed arguments', async () => {
    for (const channel of [
      'appearance:online-list',
      'appearance:online-detail',
      'appearance:online-prepare',
      'appearance:online-install',
      'appearance:online-discard',
    ]) {
      expect(state.handlers.has(channel)).toBe(true)
    }
    const call = (channel: string, ...args: unknown[]) => state.handlers.get(channel)!({}, ...args)
    expect(await call('appearance:online-list', 'x')).toMatchObject({ success: false })
    expect(await call('appearance:online-detail', 1)).toMatchObject({ success: false })
    expect(await call('appearance:online-prepare', 'alpha', '1')).toMatchObject({ success: false })
    expect(await call('appearance:online-install', 'token', 'yes')).toMatchObject({
      success: false,
    })
    expect(await call('appearance:online-install', 'unknown-token')).toMatchObject({
      success: false,
      code: 'EXPIRED',
    })
    expect(await call('appearance:online-discard', null)).toEqual({ success: false })
    expect(state.send).not.toHaveBeenCalled()
  })

  it.each([null, '../x', '', 'X'])('rejects invalid expected package ID %s', id => {
    expect(invoke('appearance:clear-invalid', id).success).toBe(false)
    expect(readConfig().appearanceId).toBe('x')
    expect(state.send).not.toHaveBeenCalled()
  })
})

describe('local appearance inspect IPC', () => {
  const PNG_1X1 = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64'
  )
  const inspect = (zipPath: unknown) =>
    state.handlers.get('appearance:inspect-local')!({}, zipPath) as LocalAppearanceInspectResult

  function writeZip(name: string, manifest: unknown, files: Record<string, Buffer> = {}): string {
    const zip = new AdmZip()
    zip.addFile('theme.json', Buffer.from(JSON.stringify(manifest)))
    for (const [entry, data] of Object.entries(files)) zip.addFile(entry, data)
    const zipPath = path.join(state.root, name)
    zip.writeZip(zipPath)
    return zipPath
  }

  it('returns the preview of a valid package without writing any directory', () => {
    const zipPath = writeZip(
      'pack.zip',
      {
        formatVersion: 1,
        id: 'sakura',
        name: '樱花',
        description: '粉色',
        mode: 'light',
        tokens: { colorPrimary: '#ff88aa' },
        preview: 'preview.png',
      },
      { 'preview.png': PNG_1X1 }
    )
    const before = fs.readdirSync(state.root).sort()

    const result = inspect(zipPath)

    expect(result).toEqual({
      success: true,
      fileSize: fs.statSync(zipPath).size,
      appearance: {
        id: 'sakura',
        name: '樱花',
        description: '粉色',
        mode: 'light',
        tokens: { colorPrimary: '#ff88aa' },
        previewUrl: `data:image/png;base64,${PNG_1X1.toString('base64')}`,
      },
    })
    expect(fs.readdirSync(state.root).sort()).toEqual(before)
    expect(state.send).not.toHaveBeenCalled()
  })

  it('reports an invalid package as INVALID_PACKAGE', () => {
    const undeclared = writeZip(
      'bad.zip',
      {
        formatVersion: 1,
        id: 'bad',
        name: 'Bad',
        mode: 'light',
        tokens: { colorPrimary: '#000000' },
      },
      { 'extra.png': PNG_1X1 }
    )
    expect(inspect(undeclared)).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })

    const notZip = path.join(state.root, 'broken.zip')
    fs.writeFileSync(notZip, 'not a zip')
    expect(inspect(notZip)).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })

    expect(inspect(path.join(state.root, 'missing.zip'))).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const huge = path.join(state.root, 'huge.zip')
    fs.writeFileSync(huge, Buffer.alloc(16 * 1024 * 1024 + 1))
    expect(inspect(huge)).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })
  })

  it.each([undefined, null, 42, { path: 'a.zip' }, 'theme.json', 'pack.rar'])(
    'rejects argument %j',
    zipPath => {
      expect(inspect(zipPath)).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })
    }
  )
})

describe('upload cover inspect IPC', () => {
  const PNG_1X1 = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64'
  )
  const inspectCover = (imagePath: unknown) =>
    state.handlers.get('appearance:inspect-cover')!({}, imagePath) as {
      success: boolean
      dataUrl?: string
      error?: string
    }
  const writeFile = (name: string, data: Buffer): string => {
    const filePath = path.join(state.root, name)
    fs.writeFileSync(filePath, data)
    return filePath
  }

  it('returns a data URL typed by the file header, not the extension', () => {
    const result = inspectCover(writeFile('cover.bin', PNG_1X1))
    expect(result.success).toBe(true)
    expect(result.dataUrl).toBe(`data:image/png;base64,${PNG_1X1.toString('base64')}`)

    const webp = Buffer.concat([Buffer.from('RIFF'), Buffer.alloc(4), Buffer.from('WEBPVP8 ')])
    expect(inspectCover(writeFile('cover.png', webp)).dataUrl).toMatch(/^data:image\/webp;base64,/)
  })

  it('rejects images over 2 MB, unknown formats, folders and missing files', () => {
    const huge = Buffer.concat([PNG_1X1, Buffer.alloc(2 * 1024 * 1024)])
    expect(inspectCover(writeFile('huge.png', huge))).toMatchObject({ success: false })
    expect(inspectCover(writeFile('fake.png', Buffer.from('GIF89a')))).toMatchObject({
      success: false,
    })
    expect(inspectCover(state.root)).toMatchObject({ success: false })
    expect(inspectCover(path.join(state.root, 'missing.png'))).toMatchObject({ success: false })
  })

  it.each([undefined, null, 42, '', { path: 'a.png' }])('rejects argument %j', imagePath => {
    expect(inspectCover(imagePath)).toMatchObject({ success: false })
  })
})
