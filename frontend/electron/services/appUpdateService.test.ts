import { access, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { EventEmitter } from 'node:events'
import { createHash } from 'node:crypto'
import AdmZip from 'adm-zip'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { AppUpdateService, normalizeAppVersion, parseUpdateNotes } from './appUpdateService'
import { prepareCoreUpgrade, prepareRuntimeBinary } from './runtimeUpgradePreparation'
import { resetLatestRuntimeVersionCache } from './runtimeReleaseService'
import type { BackendService } from './backendService'
import { recoverUpdateMaterials } from './updateStaging'

const native = vi.hoisted(
  () => /* 提前建立网络、代理和进程启动替身，供提升执行的模块 mock 共用。 */ ({
    fetch: vi.fn(),
    setProxy: vi.fn(),
    spawn: vi.fn(),
    runtimeRun: vi.fn(),
    runtimeStop: vi.fn(async () => {}),
  })
)

function targetFile(url: string, version = '5.9.0'): Response {
  // 提供同一版本的三个发行文件，验证前端将锁定环境而非当前解释器交给预检。
  if (url.endsWith('/.python-version')) return new Response('3.13.2\n')
  if (url.endsWith('/uv.lock')) return new Response('version=1\n')
  return new Response(`[project]\nversion="${version}"\ndependencies=["pydantic>=2"]\n`)
}
vi.mock('./runtime', async importOriginal => ({
  ...(await importOriginal<typeof import('./runtime')>()),
  createRuntimeClient: () => ({ run: native.runtimeRun, stop: native.runtimeStop }),
}))
vi.mock('electron', () => /* 替换 Electron 网络分区入口，使更新测试不建立真实桌面网络会话。 */ ({
  app: { isPackaged: false },
  session: {
    fromPartition: () => /* 向更新服务提供受控的查询和代理替身。 */ ({
      fetch: native.fetch,
      setProxy: native.setProxy,
    }),
  },
}))
vi.mock('node:child_process', () => /* 替换安装器启动边界，避免测试运行真实安装程序。 */ ({
  spawn: native.spawn,
  execFile: (
    _file: string,
    _args: string[],
    _options: unknown,
    callback: (error: Error | null, output: string, stderr: string) => void
  ) => {
    // 保留真实文件生命周期，仅将系统进程清单固定为当前测试前端。
    callback(
      null,
      JSON.stringify([
        {
          pid: process.pid,
          name: 'frontend.exe',
          started: 'frontend-start',
          executable: process.execPath,
          command: 'frontend',
        },
      ]),
      ''
    )
  },
}))
vi.mock('./logger', () => ({
  getLogger: () => ({ warn: vi.fn(), info: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))
afterEach(() => {
  // 每个用例结束后恢复全局对象并清空 mock 调用记录。
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  resetLatestRuntimeVersionCache()
})

describe('前端版本检查的发行契约', () => {
  // 组织应用版本号与公告过滤的公共契约测试。
  it('按 beta 序号而非字符串顺序筛选更新说明，坏段不妨碍其他版本', () => {
    // 验证 beta 数字按数值排序、损坏公告被过滤，并且不会混入当前版本以前的说明。
    const note =
      '<!--' +
      JSON.stringify({
        'v5.8.0-beta.2': { feat: ['older'] },
        'v5.8.0-beta.10': { feat: ['newer'] },
        'v5.8.0-beta.11': { fix: 'invalid' },
        'v5.8.0': { fix: ['stable'] },
        unknown: { feat: ['ignored'] },
      }) +
      '-->\nHuman readable body'
    expect(Object.keys(parseUpdateNotes(note, 'v5.8.0-beta.2'))).toEqual([
      'v5.8.0',
      'v5.8.0-beta.10',
    ])
    expect(parseUpdateNotes('<!--incomplete', 'v5.8.0')).toEqual({})
  })
  it('只接受宿主现行的正式与 beta 版本号', () => {
    // 验证版本输入只接受正式和 beta 形式，拒绝路径文本及其他预发布命名。
    expect(normalizeAppVersion('5.8.0-beta.10')).toBe('v5.8.0-beta.10')
    expect(() =>
      /* 把路径穿越形式交给版本校验，供断言其被拒绝。 */ normalizeAppVersion('../release/v5.8.0')
    ).toThrow()
    expect(() =>
      /* 把未支持的 rc 版本交给版本校验，供断言其被拒绝。 */ normalizeAppVersion('5.8.0-rc.1')
    ).toThrow()
  })
})

describe('前端应用升级编排', () => {
  // 组织前端拥有应用升级决策、下载材料与停机安装的集成边界测试。
  it.each([
    ['v5.9.0', '5.9.0'],
    ['v5.9.0-beta.10', '5.9.0b10'],
  ])('升级 %s：停机前复制、安装前再预检，不兼容时不停止后端', async (version, pythonVersion) => {
    // 分别验证正式和 beta 更新在停机前复制包、安装前再次预检，冲突时不会停止后端。
    const root = await mkdtemp(join(tmpdir(), 'mas-app-upgrade-'))
    const shared = join(root, 'backend-cache.zip')
    const archive = new AdmZip()
    archive.addFile('AUTO-MAS-Setup.exe', Buffer.from('installer-boundary-fixture'))
    await writeFile(shared, archive.toBuffer())
    let compatible = true
    let checks = 0
    let copied: string | null = null
    native.fetch.mockImplementation(async (url: string) => targetFile(url, pythonVersion))
    native.fetch.mockRejectedValueOnce(new TypeError('connection failed'))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: URL, options: RequestInit) => {
        // 模拟设置、预检与统一下载接口，记录准入次数并返回共享缓存文件。
        switch (url.pathname) {
          case '/api/setting/get':
            return Response.json({
              code: 200,
              data: { Update: { ProxyAddress: 'http://127.0.0.1:7890' } },
            })
          case '/api/update/precheck':
            expect(JSON.parse(options.body as string)).toMatchObject({
              version,
              python_version: '3.13.2',
              lockfile: 'version=1\n',
            })
            checks++
            return Response.json({
              code: 200,
              compatible,
              conflicts: compatible ? [] : [{ message: 'plugin version conflict' }],
            })
          case '/api/download/request':
            return Response.json({ code: 200, accepted: true })
          case '/api/download/query':
            return Response.json({ code: 200, data: { state: 'succeeded', path: shared } })
          case '/api/download/release':
            expect(service.snapshot.status).toBe('downloading')
            return Response.json({ code: 200 })
          default:
            throw new Error(`Unexpected backend endpoint: ${url.pathname}`)
        }
      })
    )
    const service = new AppUpdateService(
      root,
      () => /* 为测试更新服务提供固定的本地后端地址。 */ 'http://127.0.0.1:36163',
      event => {
        // 记录下载完成事件中的前端副本路径，供验证停机后的安装材料归属。
        if (event.type === 'completed') copied = event.snapshot.file
      }
    )
    const stopBackend = vi.fn(async () => {
      // 在模拟后端停止前确认预检次数与复制文件完整，再移除后端缓存模拟进程退出清理。
      expect(checks).toBeGreaterThanOrEqual(3)
      expect(await readFile(copied!)).toEqual(archive.toBuffer())
      await rm(shared)
      return { success: true }
    })
    const startBackend = vi.fn()
    native.spawn.mockImplementation((installer: string) => {
      // 检查安装器从前端副本目录启动，并返回可确认启动的受控子进程。
      expect(installer).toBe(join(copied!, '..', 'AUTO-MAS-Setup.exe'))
      const child = Object.assign(new EventEmitter(), { pid: 4321, unref: vi.fn() })
      queueMicrotask(() =>
        /* 异步发送安装器已启动事件，完成被测安装启动确认。 */ child.emit('spawn')
      )
      return child
    })
    try {
      await service.start(version, { currentVersion: 'v5.8.0', settings: { Source: 'CNB' } })
      expect(service.snapshot.status).toBe('completed')
      expect(copied).not.toBe(shared)
      expect(await readFile(copied!)).toEqual(archive.toBuffer())
      const backend = { stopBackend, startBackend } as unknown as BackendService
      compatible = false
      await expect(service.install(backend)).rejects.toThrow('plugin version conflict')
      expect(stopBackend).not.toHaveBeenCalled()
      compatible = true
      native.spawn.mockImplementationOnce(() => {
        const child = new EventEmitter()
        queueMicrotask(() => child.emit('error', new Error('installer denied')))
        return child
      })
      await expect(service.install(backend)).rejects.toThrow('installer denied')
      expect(startBackend).toHaveBeenCalledTimes(1)
      expect(await readFile(copied!)).toEqual(archive.toBuffer())
      await writeFile(shared, archive.toBuffer())
      const installing = service.install(backend).catch(error => error)
      await expect(service.install(backend)).rejects.toThrow('安装已经开始')
      expect(await installing).toBeUndefined()
      expect(stopBackend).toHaveBeenCalledTimes(2)
      expect(checks).toBe(4)
      expect(native.spawn).toHaveBeenCalledTimes(2)
      await expect(service.install(backend)).rejects.toThrow('安装已经开始')
      expect(native.setProxy).toHaveBeenCalledWith({ proxyRules: 'http://127.0.0.1:7890' })
      expect(await readFile(join(copied!, '..', 'AUTO-MAS-Setup.exe'), 'utf8')).toBe(
        'installer-boundary-fixture'
      )
      expect(startBackend).toHaveBeenCalledTimes(1)
      // 前端正常退出与新版提前启动均不能删除已经交给安装器的材料。
      await service.shutdown()
      await recoverUpdateMaterials(root)
      expect(await readFile(copied!)).toEqual(archive.toBuffer())
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })
})

it('手动同版本更新按远端提交预检，冲突在停机和材料准备前返回', async () => {
  const commit = 'c'.repeat(40)
  native.runtimeRun
    .mockResolvedValueOnce({ success: true, result: { details: { version: 'v5.9.0' } } })
    .mockResolvedValueOnce({ success: true, result: { details: { remoteCommit: commit } } })
  native.fetch.mockImplementation(async (url: string) => {
    expect(url).toContain(`/${commit}/`)
    return targetFile(url)
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: URL) => {
      if (url.pathname === '/api/setting/get')
        return Response.json({ code: 200, data: { Update: {} } })
      if (url.pathname === '/api/update/precheck')
        return Response.json({
          code: 200,
          compatible: false,
          conflicts: [{ message: 'plugin conflict' }],
        })
      throw new Error(`Unexpected endpoint: ${url.pathname}`)
    })
  )
  await expect(
    prepareCoreUpgrade(
      { runtimePath: 'runtime.exe', appRoot: 'test-root', dataRoot: 'test-root', mode: 'managed' },
      'http://127.0.0.1:36163',
      'v5.9.0'
    )
  ).rejects.toThrow('plugin conflict')
  expect(native.runtimeStop).toHaveBeenCalledTimes(1)
})

it.each([
  ['manual', 'metadata'],
  ['manual', 'solver'],
  ['application', 'metadata'],
  ['application', 'solver'],
] as const)(
  '取消 %s 更新的 %s 预检时，不继续下载或进入停机',
  async (entry, stage) => {
    const controller = new AbortController()
    const entered = Promise.withResolvers<void>()
    const pending = (_url: unknown, options?: RequestInit) => {
      // 模拟真实 fetch 的取消语义，缺少 signal 时在途请求会一直占用流程。
      entered.resolve()
      return new Promise<Response>((_resolve, reject) => {
        options?.signal?.addEventListener('abort', () => reject(options.signal?.reason), {
          once: true,
        })
      })
    }
    if (entry === 'manual')
      native.runtimeRun.mockResolvedValueOnce({
        success: true,
        result: { details: { version: 'v5.8.0' } },
      })
    native.fetch.mockImplementation(
      stage === 'metadata' ? pending : async (url: string) => targetFile(url)
    )
    const endpoints: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: URL, options?: RequestInit) => {
        endpoints.push(url.pathname)
        if (url.pathname === '/api/setting/get')
          return Promise.resolve(Response.json({ code: 200, data: { Update: {} } }))
        if (url.pathname === '/api/update/precheck') return pending(url, options)
        throw new Error(`Unexpected endpoint: ${url.pathname}`)
      })
    )
    const service = new AppUpdateService(
      'test-root',
      () => 'http://127.0.0.1:36163',
      () => {}
    )
    const preparation =
      entry === 'manual'
        ? prepareCoreUpgrade(
            {
              runtimePath: 'runtime.exe',
              appRoot: 'test-root',
              dataRoot: 'test-root',
              mode: 'managed',
            },
            'http://127.0.0.1:36163',
            'v5.9.0',
            controller.signal
          )
        : service.start('v5.9.0', { currentVersion: 'v5.8.0', settings: { Source: 'CNB' } })
    const cancelled = expect(preparation).rejects.toMatchObject({ name: 'AbortError' })
    await entered.promise
    if (entry === 'manual') controller.abort()
    else await service.cancel()
    await cancelled
    if (entry === 'application') expect(service.snapshot.status).toBe('cancelled')
    expect(endpoints).toEqual(
      stage === 'metadata' ? ['/api/setting/get'] : ['/api/setting/get', '/api/update/precheck']
    )
    expect(native.fetch).toHaveBeenCalledTimes(3)
    expect(native.runtimeRun).toHaveBeenCalledTimes(entry === 'manual' ? 1 : 0)
  },
  2000
)

it.each(['success', 'settings', 'precheck', 'unconfirmed', 'release-offline', 'cancel'] as const)(
  '换源作为同一下载流程执行，%s 路径不丢失终态或提前启动新源',
  async outcome => {
    // 在 HTTP 边界控制旧下载、引用释放和新下载，运行真实换源与复制流程。
    const root = await mkdtemp(join(tmpdir(), 'mas-source-switch-'))
    const shared = join(root, 'shared.zip')
    await writeFile(shared, 'package')
    const entered = Promise.withResolvers<void>()
    const releasing = Promise.withResolvers<void>()
    const release = Promise.withResolvers<void>()
    const requests: string[] = []
    const terminals: string[] = []
    let checks = 0
    let saves = 0
    let source = 'GitHub'
    native.fetch.mockImplementation(async (url: string) => targetFile(url))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: URL, options: RequestInit) => {
        // 旧源的查询保持在途，直到换源或用户取消；释放确认前不允许开始新源。
        const body = JSON.parse(options.body as string)
        if (url.pathname === '/api/setting/get')
          return Response.json({ code: 200, data: { Update: { Source: source } } })
        if (url.pathname === '/api/setting/update') {
          saves++
          if (outcome === 'settings')
            return Response.json({ code: 500, message: 'settings failed' })
          source = body.data.Update.Source
          return Response.json({ code: 200 })
        }
        if (url.pathname === '/api/update/precheck') {
          checks++
          const compatible = outcome !== 'precheck' || checks === 1
          return Response.json({
            code: 200,
            compatible,
            conflicts: compatible ? [] : [{ message: 'incompatible plugin' }],
          })
        }
        if (url.pathname === '/api/download/request') {
          requests.push(body.request.url)
          return Response.json({ code: 200, accepted: true })
        }
        if (url.pathname === '/api/download/query') {
          if (body.url.includes('github.com'))
            return new Promise<Response>((_resolve, reject) => {
              options.signal?.addEventListener('abort', () => reject(options.signal?.reason), {
                once: true,
              })
              entered.resolve()
            })
          return Response.json({ code: 200, data: { state: 'succeeded', path: shared } })
        }
        if (url.pathname === '/api/download/release') {
          if (body.url.includes('github.com')) {
            releasing.resolve()
            await release.promise
            if (outcome === 'unconfirmed')
              return Response.json({ code: 409, message: 'download_writer_unconfirmed' })
            if (outcome === 'release-offline') throw new TypeError('release disconnected')
          }
          return Response.json({ code: 200 })
        }
        throw new Error(`Unexpected endpoint: ${url.pathname}`)
      })
    )
    const service = new AppUpdateService(
      root,
      () => 'http://127.0.0.1:36163',
      event => {
        // 切源只有中间进度，整个更新下载只产生一次完成、失败或用户取消终态。
        if (event.type !== 'progress') terminals.push(event.type)
      }
    )
    const original = service
      .start('v5.9.0', { currentVersion: 'v5.8.0', settings: { Source: 'GitHub' } })
      .catch(error => error)
    let switching: Promise<unknown> | undefined
    try {
      await entered.promise
      switching = service.switchToCnb().catch(error => error)
      await releasing.promise
      expect(requests).toHaveLength(1)
      expect(saves).toBe(0)
      if (outcome === 'cancel') {
        const cancelled = service.cancel()
        release.resolve()
        await cancelled
      } else release.resolve()
      await switching
      await original
      expect(terminals).toEqual([
        outcome === 'success' ? 'completed' : outcome === 'cancel' ? 'cancelled' : 'failed',
      ])
      if (outcome === 'success') {
        expect(requests).toHaveLength(2)
        expect(requests[1]).toContain('cnb.cool')
        expect(service.snapshot.source).toBe('CNB')
        expect(await readFile(service.snapshot.file!, 'utf8')).toBe('package')
        expect(await readdir(join(root, '.frontend-updates'))).toHaveLength(1)
        await service.shutdown()
        await expect(access(service.snapshot.file!)).rejects.toMatchObject({ code: 'ENOENT' })
      } else {
        expect(requests).toHaveLength(1)
        if (outcome === 'cancel' || outcome === 'unconfirmed' || outcome === 'release-offline')
          expect(saves).toBe(0)
        if (outcome !== 'cancel') expect(service.snapshot.message).toBeTruthy()
        expect(await readdir(join(root, '.frontend-updates'))).toEqual([])
      }
    } finally {
      release.resolve()
      await service.cancel().catch(() => {})
      await Promise.all([original, switching])
      await rm(root, { recursive: true, force: true })
    }
  },
  3000
)

it('Runtime 预下载校验失败换源清理，释放等待实际对齐结束且不再访问网络', async () => {
  // 真实执行预取、摘要校验和文件替换，仅在发行 HTTP 与 Runtime 版本进程边界提供样本。
  const root = await mkdtemp(join(tmpdir(), 'mas-runtime-prepared-'))
  const runtimePath = join(root, 'auto-mas-runtime.exe')
  const shared = join(root, 'download-cache.exe')
  const target = 'v0.2.0'
  const content = 'new-runtime-binary'
  const hash = createHash('sha256').update(content).digest('hex')
  await writeFile(runtimePath, 'old-runtime-binary')
  await writeFile(shared, 'broken-download')
  let requests = 0
  let consuming = false
  const entered = Promise.withResolvers<void>()
  const release = Promise.withResolvers<void>()
  native.runtimeRun.mockImplementation(async () => {
    if (consuming) {
      entered.resolve()
      await release.promise
    }
    return {
      success: true,
      result: {
        details: {
          runtimeVersion: (await readFile(runtimePath, 'utf8')) === content ? target : 'v0.1.0',
        },
      },
    }
  })
  const fetcher = vi.fn(async (input: URL | string) => {
    const url = String(input)
    if (url.endsWith('/SHA256SUMS.txt'))
      return new Response(`${hash}  auto-mas-runtime-${target}.exe\n`)
    if (url.includes('/-/releases?'))
      return Response.json([{ tag_name: target, draft: false, prerelease: false }])
    if (url.endsWith('/api/download/request')) {
      if (++requests === 2) await writeFile(shared, content)
      return Response.json({ code: 200, accepted: true })
    }
    if (url.endsWith('/api/download/query'))
      return Response.json({ code: 200, data: { state: 'succeeded', path: shared } })
    if (url.endsWith('/api/download/release')) return Response.json({ code: 200 })
    throw new Error(`Unexpected URL: ${url}`)
  })
  vi.stubGlobal('fetch', fetcher)
  try {
    const prepared = await prepareRuntimeBinary(
      { mode: 'managed', runtimePath, appRoot: root, dataRoot: root },
      'http://127.0.0.1:36163',
      'v5.9.0'
    )
    expect(requests).toBe(2)
    expect(await readdir(join(root, '.frontend-updates'))).toHaveLength(1)
    const downloads = fetcher.mock.calls.length
    consuming = true
    const applying = prepared.apply({ runtimePath, appRoot: root, channel: 'stable' })
    await entered.promise
    const disposing = prepared.dispose()
    expect(await readdir(join(root, '.frontend-updates'))).toHaveLength(1)
    release.resolve()
    expect(await applying).toMatchObject({ status: 'upgraded' })
    await disposing
    expect(await readFile(runtimePath, 'utf8')).toBe(content)
    expect(await readdir(join(root, '.frontend-updates'))).toEqual([])
    expect(fetcher.mock.calls.length).toBe(downloads)
    await prepared.dispose()
    await expect(prepared.apply({ runtimePath, appRoot: root, channel: 'stable' })).rejects.toThrow(
      '已释放'
    )
  } finally {
    release.resolve()
    await rm(root, { recursive: true, force: true })
  }
})

it('已完成的更新包被外部移除时要求重新下载，不停止后端或启动安装器', async () => {
  const root = await mkdtemp(join(tmpdir(), 'mas-missing-package-'))
  const shared = join(root, 'cache.zip')
  await writeFile(shared, 'package')
  native.fetch.mockImplementation(async (url: string) => targetFile(url))
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: URL) => {
      if (url.pathname === '/api/setting/get')
        return Response.json({ code: 200, data: { Update: {} } })
      if (url.pathname === '/api/update/precheck')
        return Response.json({ code: 200, compatible: true })
      if (url.pathname === '/api/download/request')
        return Response.json({ code: 200, accepted: true })
      if (url.pathname === '/api/download/query')
        return Response.json({ code: 200, data: { state: 'succeeded', path: shared } })
      if (url.pathname === '/api/download/release') return Response.json({ code: 200 })
      throw new Error(`Unexpected endpoint: ${url.pathname}`)
    })
  )
  const service = new AppUpdateService(
    root,
    () => 'http://127.0.0.1:36163',
    () => {}
  )
  const stopBackend = vi.fn()
  try {
    await service.start('v5.9.0', { currentVersion: 'v5.8.0', settings: { Source: 'CNB' } })
    await rm(service.snapshot.file!)
    await expect(service.install({ stopBackend } as unknown as BackendService)).rejects.toThrow(
      '重新下载'
    )
    expect(service.snapshot).toMatchObject({ status: 'failed', file: null })
    expect(stopBackend).not.toHaveBeenCalled()
    expect(native.spawn).not.toHaveBeenCalled()
    await service.shutdown(true)
    expect(await readdir(join(root, '.frontend-updates'))).toEqual([])
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

it.each([null, false])(
  '预检返回 %s 时阻止下载并显示分类原因，下一次检查通过后可以重试',
  async compatible => {
    // 预检未完成和确定冲突都不能继续下载；错误提示和重试沿现有服务入口完成。
    const root = await mkdtemp(join(tmpdir(), 'mas-precheck-retry-'))
    const shared = join(root, 'cache.zip')
    await writeFile(shared, 'package')
    const message = compatible === null ? '兼容性检查未完成，请稍后重试' : '目标版本依赖冲突'
    let resolved = false
    const requests: string[] = []
    native.fetch.mockImplementation(async (url: string) => targetFile(url))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: URL) => {
        requests.push(url.pathname)
        if (url.pathname === '/api/setting/get')
          return Response.json({ code: 200, data: { Update: {} } })
        if (url.pathname === '/api/update/precheck')
          return Response.json(
            resolved
              ? { code: 200, compatible: true }
              : {
                  code: compatible === null ? 503 : 200,
                  status: compatible === null ? 'error' : 'success',
                  message,
                  compatible,
                  conflicts: compatible === null ? [] : [{ message }],
                }
          )
        if (url.pathname === '/api/download/request')
          return Response.json({ code: 200, accepted: true })
        if (url.pathname === '/api/download/query')
          return Response.json({ code: 200, data: { state: 'succeeded', path: shared } })
        if (url.pathname === '/api/download/release') return Response.json({ code: 200 })
        throw new Error(`Unexpected endpoint: ${url.pathname}`)
      })
    )
    const service = new AppUpdateService(
      root,
      () => 'http://127.0.0.1:36163',
      () => {}
    )
    const input = { currentVersion: 'v5.8.0', settings: { Source: 'CNB' } } as const
    try {
      await expect(service.start('v5.9.0', input)).rejects.toThrow(message)
      expect(service.snapshot).toMatchObject({ status: 'failed', message, file: null })
      expect(requests).toEqual(['/api/setting/get', '/api/update/precheck'])
      resolved = true
      await service.start('v5.9.0', input)
      expect(service.snapshot.status).toBe('completed')
      expect(await readFile(service.snapshot.file!, 'utf8')).toBe('package')
    } finally {
      await service.shutdown(true)
      await rm(root, { recursive: true, force: true })
    }
  }
)
