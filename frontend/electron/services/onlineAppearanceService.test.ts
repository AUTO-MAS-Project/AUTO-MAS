import * as crypto from 'crypto'
import * as fs from 'fs'
import * as http from 'http'
import type { AddressInfo } from 'net'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  APPEARANCE_SOURCES_FILE,
  createOnlineAppearanceService,
  readAppearanceSources,
  type OnlineAppearanceServiceOptions,
  type OnlineFetch,
} from './onlineAppearanceService'

const state = vi.hoisted(() => ({
  root: '',
  handlers: new Map<string, (...args: unknown[]) => unknown>(),
  send: vi.fn(),
  logs: [] as string[],
}))

vi.mock('electron', () => ({
  app: {
    getPath: (name: string) =>
      name === 'temp' ? path.join(state.root, 'temp') : path.join(state.root, 'userdata'),
  },
  ipcMain: {
    handle: (channel: string, callback: (...args: unknown[]) => unknown) =>
      state.handlers.set(channel, callback),
  },
  BrowserWindow: {
    getAllWindows: () => [{ isDestroyed: () => false, webContents: { send: state.send } }],
  },
  net: { fetch: (...args: Parameters<typeof fetch>) => fetch(...args) },
}))
vi.mock('./environmentService', () => ({ getAppRoot: () => state.root }))
vi.mock('./logger', () => ({
  getLogger: () => ({
    info: (message: string) => state.logs.push(`info ${message}`),
    warn: (message: string) => state.logs.push(`warn ${message}`),
  }),
}))

const MIB = 1024 * 1024
const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64'
)

type DownloadMode = 'normal' | 'destroy-half' | 'stream-overflow' | 'length-overflow' | 'stall'

interface FakeVersion {
  versionNo: number
  data: Buffer
  sha256?: string
  fileSize?: number
  mode?: DownloadMode
}

interface FakeFile {
  fileKey: string
  displayName: string
  description?: string | null
  versions: FakeVersion[]
}

const site = {
  files: new Map<string, FakeFile>(),
  requests: [] as string[],
  listStatus: 200,
  listRaw: undefined as string | undefined,
  sentBytes: 0,
  downloadClosed: Promise.resolve(),
}

const sha256 = (data: Buffer | string): string =>
  crypto.createHash('sha256').update(data).digest('hex')

function sendJson(res: http.ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body)
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(text),
  })
  res.end(text)
}

function notFound(res: http.ServerResponse, message: string): void {
  sendJson(res, 404, { code: 404, message, data: null })
}

function itemJson(file: FakeFile) {
  return {
    project_key: 'auto-mas',
    category_key: 'Appearance',
    file_key: file.fileKey,
    display_name: file.displayName,
    description: file.description === undefined ? null : file.description,
    owner_username: 'tester',
    tags: [],
    published_version_no: Math.max(...file.versions.map(version => version.versionNo)),
    published_at: '2026-10-06T00:00:00Z',
    updated_at: '2026-10-06T01:00:00Z',
    detail_path: `/files/auto-mas/Appearance/${file.fileKey}`,
  }
}

function versionJson(version: FakeVersion) {
  return {
    version_no: version.versionNo,
    source_filename: `v${version.versionNo}.zip`,
    file_size: version.fileSize ?? version.data.length,
    sha256: version.sha256 ?? sha256(version.data),
    change_note: null,
    created_at: `2026-10-0${version.versionNo}T00:00:00Z`,
  }
}

function serveDownload(
  req: http.IncomingMessage,
  res: http.ServerResponse,
  version: FakeVersion
): void {
  let resolveClosed = (): void => undefined
  site.downloadClosed = new Promise(resolve => {
    resolveClosed = resolve
  })
  site.sentBytes = 0
  res.on('close', resolveClosed)
  const mode = version.mode ?? 'normal'
  if (mode === 'normal') {
    res.writeHead(200, {
      'Content-Type': 'application/octet-stream',
      'Content-Length': version.data.length,
      ETag: `"${sha256(version.data)}"`,
    })
    site.sentBytes = version.data.length
    res.end(version.data)
    return
  }
  if (mode === 'destroy-half') {
    res.writeHead(200, { 'Content-Length': version.data.length })
    const half = version.data.subarray(0, Math.floor(version.data.length / 2))
    site.sentBytes = half.length
    res.write(half, () => setTimeout(() => req.socket.destroy(), 20))
    return
  }
  if (mode === 'stall') {
    res.writeHead(200, { 'Content-Length': version.data.length })
    res.write(version.data.subarray(0, 10))
    site.sentBytes = 10
    return
  }
  // 超限流：不带 Content-Length（chunked）或谎报超大 Content-Length，按背压持续发送直到被掐断。
  res.writeHead(
    200,
    mode === 'length-overflow' ? { 'Content-Length': String(17 * MIB) } : { 'Content-Type': 'x' }
  )
  const chunk = Buffer.alloc(64 * 1024, 7)
  const target = 40 * MIB
  let closed = false
  res.on('close', () => {
    closed = true
  })
  const pump = (): void => {
    while (!closed && site.sentBytes < target) {
      site.sentBytes += chunk.length
      if (!res.write(chunk)) {
        res.once('drain', pump)
        return
      }
    }
    if (!closed) res.end()
  }
  pump()
}

const server = http.createServer((req, res) => {
  site.requests.push(req.url ?? '')
  const url = new URL(req.url ?? '/', 'http://127.0.0.1')
  const prefix = '/api/v1/files'
  if (url.pathname === prefix) {
    if (site.listRaw !== undefined) {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(site.listRaw)
      return
    }
    if (site.listStatus !== 200) {
      sendJson(res, site.listStatus, { code: site.listStatus, message: 'error', data: null })
      return
    }
    const keyword = url.searchParams.get('keyword') ?? ''
    const items = [...site.files.values()]
      .filter(file => !keyword || file.displayName.includes(keyword))
      .map(itemJson)
    sendJson(res, 200, {
      code: 0,
      message: 'ok',
      data: {
        items,
        pagination: {
          page: Number(url.searchParams.get('page')),
          page_size: Number(url.searchParams.get('page_size')),
          total: items.length,
          has_next: false,
        },
      },
    })
    return
  }
  const segments = url.pathname
    .slice(prefix.length + 1)
    .split('/')
    .map(decodeURIComponent)
  const [project, category, fileKey, action] = segments
  const file = site.files.get(fileKey ?? '')
  if (project !== 'auto-mas' || category !== 'Appearance' || !file) {
    notFound(res, 'Published file not found.')
    return
  }
  if (action === undefined) {
    const latest = [...file.versions].sort((a, b) => b.versionNo - a.versionNo)[0]
    sendJson(res, 200, {
      code: 0,
      message: 'ok',
      data: { ...itemJson(file), published_version: latest ? versionJson(latest) : null },
    })
    return
  }
  if (action === 'versions') {
    sendJson(res, 200, { code: 0, message: 'ok', data: file.versions.map(versionJson) })
    return
  }
  if (action === 'download') {
    const version = file.versions.find(
      item => item.versionNo === Number(url.searchParams.get('version_no'))
    )
    if (!version) {
      notFound(res, 'Published file version not found.')
      return
    }
    serveDownload(req, res, version)
    return
  }
  notFound(res, 'Not found.')
})

await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
const BASE_URL = `http://127.0.0.1:${(server.address() as AddressInfo).port}/api/v1`
const globalFetch = fetch as unknown as OnlineFetch

const { registerAppearanceHandlers } = await import('../ipc/appearanceHandlers')
// 注册时会清一次缓存目录，先指向一个临时根，避免落到相对路径上。
const bootstrapRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-online-appearance-'))
state.root = bootstrapRoot
registerAppearanceHandlers({
  online: {
    fetch: globalFetch,
    baseUrl: BASE_URL,
    userDataPath: () => path.join(state.root, 'userdata'),
    cacheDir: () => path.join(state.root, 'cache'),
  },
})
fs.rmSync(bootstrapRoot, { recursive: true, force: true })

const userData = () => path.join(state.root, 'userdata')
const cacheDir = () => path.join(state.root, 'cache')
const appearanceDir = (id: string) => path.join(userData(), 'appearances', id)
const cacheFiles = (): string[] => (fs.existsSync(cacheDir()) ? fs.readdirSync(cacheDir()) : [])

function makeService(overrides: Partial<OnlineAppearanceServiceOptions> = {}) {
  return createOnlineAppearanceService({
    fetch: globalFetch,
    baseUrl: BASE_URL,
    userDataPath: userData,
    cacheDir,
    ...overrides,
  })
}

function invoke<T>(channel: string, ...args: unknown[]): Promise<T> {
  const handler = state.handlers.get(channel)
  if (!handler) throw new Error(`Missing handler: ${channel}`)
  return Promise.resolve(handler({}, ...args) as T)
}

function makePackage(id: string, name: string, options: { preview?: boolean } = {}): Buffer {
  const zip = new AdmZip()
  const manifest = {
    formatVersion: 1,
    id,
    name,
    description: `${name} 描述`,
    mode: 'dark',
    tokens: { colorPrimary: '#ff6600', borderRadius: 6 },
    background: { path: 'assets/background.png', opacity: 0.3 },
    ...(options.preview ? { preview: 'preview.png' } : {}),
  }
  zip.addFile('theme.json', Buffer.from(JSON.stringify(manifest)))
  zip.addFile('assets/background.png', PNG_1X1)
  if (options.preview) zip.addFile('preview.png', PNG_1X1)
  return zip.toBuffer()
}

function addFile(fileKey: string, versions: FakeVersion[], displayName = fileKey): FakeFile {
  const file = { fileKey, displayName, versions }
  site.files.set(fileKey, file)
  return file
}

function writeSources(sources: Record<string, unknown>): void {
  fs.mkdirSync(userData(), { recursive: true })
  fs.writeFileSync(
    path.join(userData(), APPEARANCE_SOURCES_FILE),
    JSON.stringify({ schemaVersion: 1, sources })
  )
}

function fakeInstalled(id: string): void {
  fs.mkdirSync(appearanceDir(id), { recursive: true })
  fs.writeFileSync(path.join(appearanceDir(id), 'theme.json'), '{}')
}

function snapshotDirectory(directory: string): Record<string, string> {
  const result: Record<string, string> = {}
  const visit = (current: string, relative: string): void => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const entryRelative = relative ? `${relative}/${entry.name}` : entry.name
      const entryPath = path.join(current, entry.name)
      if (entry.isDirectory()) visit(entryPath, entryRelative)
      else result[entryRelative] = sha256(fs.readFileSync(entryPath))
    }
  }
  visit(directory, '')
  return result
}

const record = (fileKey: string, versionNo: number, installedAt: string) => ({
  origin: 'http://127.0.0.1',
  projectKey: 'auto-mas',
  categoryKey: 'Appearance',
  fileKey,
  versionNo,
  sha256: 'a'.repeat(64),
  installedAt,
})

beforeEach(() => {
  state.root = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-online-appearance-'))
  state.send.mockClear()
  state.logs.length = 0
  site.files.clear()
  site.requests.length = 0
  site.listStatus = 200
  site.listRaw = undefined
})

afterEach(() => {
  if (
    path.dirname(state.root) !== path.resolve(os.tmpdir()) ||
    !path.basename(state.root).startsWith('mas-online-appearance-')
  ) {
    throw new Error('测试清理目录超出临时目录')
  }
  fs.rmSync(state.root, { recursive: true, force: true })
})

afterAll(async () => {
  server.closeAllConnections()
  await new Promise(resolve => server.close(resolve))
})

describe('online appearance list', () => {
  it('maps items and marks only installed packages whose directory still exists', async () => {
    addFile('alpha', [{ versionNo: 1, data: Buffer.from('a') }], 'Alpha 外观')
    site.files.get('alpha')!.description = null
    addFile(
      'beta',
      [
        { versionNo: 1, data: Buffer.from('b') },
        { versionNo: 4, data: Buffer.from('b4') },
      ],
      'Beta'
    )
    addFile('gamma', [{ versionNo: 2, data: Buffer.from('g') }], 'Gamma')
    // alpha 有两条记录，取 installedAt 最新且目录仍在的；beta 的目录已被删掉。
    writeSources({
      'alpha-old': record('alpha', 1, '2026-10-01T00:00:00.000Z'),
      'alpha-new': record('alpha', 3, '2026-10-05T00:00:00.000Z'),
      'beta-gone': record('beta', 4, '2026-10-05T00:00:00.000Z'),
    })
    fakeInstalled('alpha-old')
    fakeInstalled('alpha-new')

    const result = await makeService().list({ page: 1, pageSize: 20 })
    expect(result.success).toBe(true)
    expect(result.pagination).toEqual({ page: 1, pageSize: 20, total: 3, hasNext: false })
    expect(result.items).toEqual([
      {
        fileKey: 'alpha',
        displayName: 'Alpha 外观',
        description: '',
        ownerUsername: 'tester',
        publishedVersionNo: 1,
        publishedAt: '2026-10-06T00:00:00Z',
        updatedAt: '2026-10-06T01:00:00Z',
        installed: { appearanceId: 'alpha-new', versionNo: 3 },
      },
      expect.objectContaining({ fileKey: 'beta', publishedVersionNo: 4, installed: null }),
      expect.objectContaining({ fileKey: 'gamma', installed: null }),
    ])
  })

  it('returns an empty list and passes trimmed keyword, page and page size', async () => {
    const service = makeService()
    const result = await service.list({ page: 2, pageSize: 5, keyword: '  不存在  ' })
    expect(result).toMatchObject({ success: true, items: [] })
    const requested = new URL(site.requests[0]!, 'http://x')
    expect(Object.fromEntries(requested.searchParams)).toEqual({
      project_key: 'auto-mas',
      category_key: 'Appearance',
      page: '2',
      page_size: '5',
      keyword: '不存在',
    })

    await service.list({ keyword: '   ' })
    expect(new URL(site.requests[1]!, 'http://x').searchParams.has('keyword')).toBe(false)
  })

  it.each([
    { page: 0 },
    { page: 1.5 },
    { pageSize: 51 },
    { pageSize: 0 },
    { keyword: 'x'.repeat(65) },
  ])('rejects invalid query %o without requesting the site', async query => {
    const result = await makeService().list(query)
    expect(result.success).toBe(false)
    expect(site.requests).toEqual([])
  })

  it('maps 404 to NOT_FOUND, 500 to NETWORK and a bad envelope to BAD_RESPONSE', async () => {
    const service = makeService()
    site.listStatus = 404
    expect(await service.list({})).toMatchObject({ success: false, code: 'NOT_FOUND' })
    site.listStatus = 500
    expect(await service.list({})).toMatchObject({ success: false, code: 'NETWORK' })
    site.listRaw = JSON.stringify({ code: 1, message: 'no', data: null })
    expect(await service.list({})).toMatchObject({ success: false, code: 'BAD_RESPONSE' })
    site.listRaw = 'not json'
    expect(await service.list({})).toMatchObject({ success: false, code: 'BAD_RESPONSE' })
  })

  it('reports NETWORK when the site is unreachable', async () => {
    const closed = http.createServer()
    await new Promise<void>(resolve => closed.listen(0, '127.0.0.1', resolve))
    const port = (closed.address() as AddressInfo).port
    await new Promise(resolve => closed.close(resolve))
    const result = await makeService({ baseUrl: `http://127.0.0.1:${port}/api/v1` }).list({})
    expect(result).toMatchObject({ success: false, code: 'NETWORK' })
    expect(typeof result.error).toBe('string')
  })
})

describe('online appearance detail', () => {
  it('returns the item with versions sorted newest first and drops malformed versions', async () => {
    addFile('alpha', [
      { versionNo: 1, data: Buffer.from('one') },
      { versionNo: 3, data: Buffer.from('three') },
      { versionNo: 2, data: Buffer.from('two') },
      { versionNo: 5, data: Buffer.from('bad'), sha256: 'not-a-hash' },
    ])
    const result = await makeService().detail('alpha')
    expect(result.success).toBe(true)
    expect(result.item).toMatchObject({ fileKey: 'alpha', publishedVersionNo: 5, installed: null })
    expect(result.versions?.map(version => version.versionNo)).toEqual([3, 2, 1])
    expect(result.versions?.[0]).toEqual({
      versionNo: 3,
      fileSize: 5,
      sha256: sha256('three'),
      changeNote: '',
      createdAt: '2026-10-03T00:00:00Z',
    })
  })

  it('maps a missing package to NOT_FOUND', async () => {
    expect(await makeService().detail('missing')).toMatchObject({
      success: false,
      code: 'NOT_FOUND',
    })
  })

  it.each(['', '.', '..', 'a/b', 'a\\b', 'a?b', 'a#b', '%2e%2e', 'a\u0000b', 'x'.repeat(129)])(
    'rejects invalid file key %j without requesting the site',
    async fileKey => {
      const service = makeService()
      expect((await service.detail(fileKey)).success).toBe(false)
      expect((await service.prepare(fileKey, 1)).success).toBe(false)
      expect(site.requests).toEqual([])
    }
  )
})

describe('online appearance prepare and install', () => {
  it('pins the requested version: v1 download uses version_no=1 and previews the v1 package', async () => {
    const v1 = makePackage('theme-a', '版本一', { preview: true })
    const v2 = makePackage('theme-a', '版本二', { preview: true })
    addFile('alpha', [
      { versionNo: 1, data: v1 },
      { versionNo: 2, data: v2 },
    ])
    const service = makeService()
    const result = await service.prepare('alpha', 1)
    expect(result).toMatchObject({
      success: true,
      fileKey: 'alpha',
      versionNo: 1,
      fileSize: v1.length,
      sha256: sha256(v1),
      existing: null,
      appearance: {
        id: 'theme-a',
        name: '版本一',
        description: '版本一 描述',
        mode: 'dark',
        tokens: { colorPrimary: '#ff6600', borderRadius: 6 },
      },
    })
    expect(result.appearance?.previewUrl).toMatch(/^data:image\/png;base64,/)
    const downloads = site.requests.filter(url => url.includes('/download'))
    expect(downloads).toEqual(['/api/v1/files/auto-mas/Appearance/alpha/download?version_no=1'])
    expect(cacheFiles()).toEqual([`${result.token}.zip`])
    // 只读解析不写用户目录。
    expect(fs.existsSync(path.join(userData(), 'appearances'))).toBe(false)

    site.requests.length = 0
    expect(await service.prepare('alpha', 9)).toMatchObject({ success: false, code: 'NOT_FOUND' })
    expect(site.requests.some(url => url.includes('/download'))).toBe(false)
  })

  it('installs through IPC, records the source, broadcasts and deletes the cache', async () => {
    const v1 = makePackage('theme-a', '版本一')
    addFile('alpha', [{ versionNo: 1, data: v1 }])
    const prepared = await invoke<{ success: boolean; token: string }>(
      'appearance:online-prepare',
      'alpha',
      1
    )
    expect(prepared.success).toBe(true)
    const installed = await invoke<{ success: boolean; appearance?: { id: string } }>(
      'appearance:online-install',
      prepared.token,
      false
    )
    expect(installed).toMatchObject({ success: true, appearance: { id: 'theme-a' } })
    expect(
      JSON.parse(fs.readFileSync(path.join(appearanceDir('theme-a'), 'theme.json'), 'utf8')).name
    ).toBe('版本一')

    const raw = JSON.parse(fs.readFileSync(path.join(userData(), APPEARANCE_SOURCES_FILE), 'utf8'))
    expect(raw.schemaVersion).toBe(1)
    expect(raw.sources['theme-a']).toMatchObject({
      origin: new URL(BASE_URL).origin,
      projectKey: 'auto-mas',
      categoryKey: 'Appearance',
      fileKey: 'alpha',
      versionNo: 1,
      sha256: sha256(v1),
    })
    expect(Number.isNaN(Date.parse(raw.sources['theme-a'].installedAt))).toBe(false)
    expect(state.send).toHaveBeenCalledWith('appearance-changed')
    expect(cacheFiles()).toEqual([])
    expect(state.logs.some(line => line.includes('data:'))).toBe(false)
    expect(state.logs.some(line => line.includes('开始下载在线外观: alpha 版本 1'))).toBe(true)

    // 列表据来源记录标出已安装。
    const listed = await invoke<{ items: Array<{ installed: unknown }> }>('appearance:online-list')
    expect(listed.items[0]!.installed).toEqual({ appearanceId: 'theme-a', versionNo: 1 })
  })

  it('rejects a SHA-256 mismatch without leaving cache files or touching appearances', async () => {
    const data = makePackage('theme-a', '版本一')
    addFile('alpha', [{ versionNo: 1, data, sha256: sha256('something else') }])
    const result = await makeService().prepare('alpha', 1)
    expect(result).toMatchObject({ success: false, code: 'CHECKSUM_MISMATCH' })
    expect(cacheFiles()).toEqual([])
    expect(fs.existsSync(path.join(userData(), 'appearances'))).toBe(false)
  })

  it('rejects a size mismatch as CHECKSUM_MISMATCH', async () => {
    const data = makePackage('theme-a', '版本一')
    addFile('alpha', [{ versionNo: 1, data, fileSize: data.length + 1 }])
    expect(await makeService().prepare('alpha', 1)).toMatchObject({
      success: false,
      code: 'CHECKSUM_MISMATCH',
    })
    expect(cacheFiles()).toEqual([])
  })

  it('refuses a declared size over 16 MiB without sending a download request', async () => {
    addFile('alpha', [{ versionNo: 1, data: Buffer.from('x'), fileSize: 16 * MIB + 1 }])
    expect(await makeService().prepare('alpha', 1)).toMatchObject({
      success: false,
      code: 'TOO_LARGE',
    })
    expect(site.requests.some(url => url.includes('/download'))).toBe(false)
  })

  it('aborts a stream without Content-Length once it exceeds 16 MiB', async () => {
    addFile('alpha', [
      { versionNo: 1, data: Buffer.from('x'), fileSize: 16 * MIB, mode: 'stream-overflow' },
    ])
    const result = await makeService().prepare('alpha', 1)
    expect(result).toMatchObject({ success: false, code: 'TOO_LARGE' })
    await site.downloadClosed
    expect(site.sentBytes).toBeLessThan(40 * MIB)
    expect(cacheFiles()).toEqual([])
  })

  it('stops as soon as the stream outgrows the size registered on the site', async () => {
    addFile('alpha', [{ versionNo: 1, data: Buffer.from('x'), mode: 'stream-overflow' }])
    const result = await makeService().prepare('alpha', 1)
    expect(result).toMatchObject({ success: false, code: 'CHECKSUM_MISMATCH' })
    await site.downloadClosed
    expect(site.sentBytes).toBeLessThan(16 * MIB)
    expect(cacheFiles()).toEqual([])
  })

  it('refuses a Content-Length over 16 MiB before reading the body', async () => {
    addFile('alpha', [{ versionNo: 1, data: Buffer.from('x'), mode: 'length-overflow' }])
    const result = await makeService().prepare('alpha', 1)
    expect(result).toMatchObject({ success: false, code: 'TOO_LARGE' })
    await site.downloadClosed
    expect(site.sentBytes).toBeLessThan(17 * MIB)
    expect(cacheFiles()).toEqual([])
  })

  it('maps a connection destroyed mid-download to NETWORK and cleans up', async () => {
    addFile('alpha', [
      { versionNo: 1, data: makePackage('theme-a', '版本一'), mode: 'destroy-half' },
    ])
    expect(await makeService().prepare('alpha', 1)).toMatchObject({
      success: false,
      code: 'NETWORK',
    })
    expect(cacheFiles()).toEqual([])
  })

  it('maps an idle download to NETWORK after the idle timeout', async () => {
    addFile('alpha', [{ versionNo: 1, data: makePackage('theme-a', '版本一'), mode: 'stall' }])
    const result = await makeService({ downloadIdleTimeoutMs: 200 }).prepare('alpha', 1)
    expect(result).toMatchObject({ success: false, code: 'NETWORK' })
    expect(result.error).toContain('超时')
    expect(cacheFiles()).toEqual([])
  })

  it('reports INVALID_PACKAGE for a hash-valid but invalid archive and cleans up', async () => {
    const missingTheme = new AdmZip()
    missingTheme.addFile('assets/background.png', PNG_1X1)
    const traversal = new AdmZip()
    traversal.addFile('../theme.json', Buffer.from('{}'))
    addFile('alpha', [
      { versionNo: 1, data: missingTheme.toBuffer() },
      { versionNo: 2, data: traversal.toBuffer() },
      { versionNo: 3, data: Buffer.from('not a zip at all') },
    ])
    const service = makeService()
    const first = await service.prepare('alpha', 1)
    expect(first).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })
    expect(first.error).toContain('theme.json')
    expect(await service.prepare('alpha', 2)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })
    expect(await service.prepare('alpha', 3)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })
    expect(cacheFiles()).toEqual([])
    expect(fs.existsSync(path.join(userData(), 'appearances'))).toBe(false)
  })

  it('handles same-ID replacement: DUPLICATE_ID keeps the cache, replace installs v2', async () => {
    addFile('alpha', [
      { versionNo: 1, data: makePackage('theme-a', '版本一') },
      { versionNo: 2, data: makePackage('theme-a', '版本二') },
    ])
    const service = makeService()
    const first = await service.prepare('alpha', 1)
    expect(service.install(first.token, false).success).toBe(true)

    const second = await service.prepare('alpha', 2)
    expect(second).toMatchObject({ success: true, existing: { id: 'theme-a', name: '版本一' } })
    const duplicate = service.install(second.token, false)
    expect(duplicate).toMatchObject({ success: false, code: 'DUPLICATE_ID' })
    expect(cacheFiles()).toEqual([`${second.token}.zip`])

    expect(service.install(second.token, true)).toMatchObject({
      success: true,
      appearance: { id: 'theme-a', name: '版本二' },
    })
    expect(
      JSON.parse(fs.readFileSync(path.join(appearanceDir('theme-a'), 'theme.json'), 'utf8')).name
    ).toBe('版本二')
    expect(readAppearanceSources(userData())['theme-a']?.versionNo).toBe(2)
    expect(cacheFiles()).toEqual([])
  })

  it('keeps the installed package and its source record when a later version fails', async () => {
    const broken = new AdmZip()
    broken.addFile('assets/background.png', PNG_1X1)
    const v4 = makePackage('theme-a', '版本四')
    addFile('alpha', [
      { versionNo: 1, data: makePackage('theme-a', '版本一') },
      { versionNo: 2, data: makePackage('theme-a', '版本二'), sha256: sha256('wrong') },
      { versionNo: 3, data: broken.toBuffer() },
      { versionNo: 4, data: v4 },
    ])
    const service = makeService()
    const first = await service.prepare('alpha', 1)
    expect(service.install(first.token, false).success).toBe(true)
    const before = snapshotDirectory(appearanceDir('theme-a'))
    const sourcesBefore = fs.readFileSync(path.join(userData(), APPEARANCE_SOURCES_FILE), 'utf8')

    expect((await service.prepare('alpha', 2)).code).toBe('CHECKSUM_MISMATCH')
    expect((await service.prepare('alpha', 3)).code).toBe('INVALID_PACKAGE')
    // 缓存文件在 prepare 后被改动：安装前复核哈希，拒绝且不动旧包。
    const fourth = await service.prepare('alpha', 4)
    expect(fourth.success).toBe(true)
    fs.writeFileSync(path.join(cacheDir(), `${fourth.token}.zip`), makePackage('theme-a', '篡改'))
    expect(service.install(fourth.token, true)).toMatchObject({
      success: false,
      code: 'CHECKSUM_MISMATCH',
    })

    expect(snapshotDirectory(appearanceDir('theme-a'))).toEqual(before)
    expect(fs.readFileSync(path.join(userData(), APPEARANCE_SOURCES_FILE), 'utf8')).toBe(
      sourcesBefore
    )
    expect(cacheFiles()).toEqual([])
  })

  it('treats unknown, discarded and expired tokens as EXPIRED and evicts beyond four', async () => {
    let clock = 1_000_000
    const service = makeService({ now: () => clock })
    addFile('alpha', [{ versionNo: 1, data: makePackage('theme-a', '版本一') }])

    expect(service.install('unknown-token', false)).toMatchObject({
      success: false,
      code: 'EXPIRED',
    })
    expect(await invoke('appearance:online-install', 42)).toMatchObject({ success: false })

    const discarded = await service.prepare('alpha', 1)
    expect(service.discard(discarded.token)).toEqual({ success: true })
    expect(service.install(discarded.token, false).code).toBe('EXPIRED')
    expect(cacheFiles()).toEqual([])

    const expired = await service.prepare('alpha', 1)
    clock += 31 * 60 * 1000
    expect(service.install(expired.token, false).code).toBe('EXPIRED')
    expect(cacheFiles()).toEqual([])

    const tokens: string[] = []
    for (let index = 0; index < 5; index += 1) {
      tokens.push((await service.prepare('alpha', 1)).token!)
    }
    expect(cacheFiles().sort()).toEqual(
      tokens
        .slice(1)
        .map(token => `${token}.zip`)
        .sort()
    )
    expect(service.install(tokens[0], false).code).toBe('EXPIRED')
    expect(service.install(tokens[4], false).success).toBe(true)
  })

  it('rejects a redirect from an https base to a non-https URL', async () => {
    const stubFetch: OnlineFetch = async () => ({
      status: 200,
      url: 'http://evil.example/api/v1/files',
      headers: { get: () => null },
      body: null,
    })
    const result = await makeService({
      baseUrl: 'https://share.example/api/v1',
      fetch: stubFetch,
    }).list({})
    expect(result).toMatchObject({ success: false, code: 'BAD_RESPONSE' })
  })

  it('clears only stale online-appearance files from the cache directory', () => {
    fs.mkdirSync(cacheDir(), { recursive: true })
    const stale = crypto.randomUUID()
    fs.writeFileSync(path.join(cacheDir(), `${stale}.zip`), 'x')
    fs.writeFileSync(path.join(cacheDir(), `${crypto.randomUUID()}.part`), 'x')
    fs.writeFileSync(path.join(cacheDir(), 'keep.zip'), 'x')
    fs.writeFileSync(path.join(cacheDir(), `${stale}.txt`), 'x')
    makeService().clearCacheDirectory()
    expect(cacheFiles().sort()).toEqual(['keep.zip', `${stale}.txt`].sort())
  })

  it('treats a corrupt source record file as empty and logs a warning', async () => {
    fs.mkdirSync(userData(), { recursive: true })
    fs.writeFileSync(path.join(userData(), APPEARANCE_SOURCES_FILE), '{broken')
    const warnings: string[] = []
    expect(
      readAppearanceSources(userData(), {
        info: () => undefined,
        warn: message => warnings.push(message),
      })
    ).toEqual({})
    expect(warnings).toHaveLength(1)

    addFile('alpha', [{ versionNo: 1, data: makePackage('theme-a', '版本一') }])
    const service = makeService()
    const prepared = await service.prepare('alpha', 1)
    expect(service.install(prepared.token, false).success).toBe(true)
    expect(readAppearanceSources(userData())['theme-a']?.versionNo).toBe(1)
  })
})
