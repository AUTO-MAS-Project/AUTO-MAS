import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { EventEmitter } from 'node:events'
import AdmZip from 'adm-zip'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { AppUpdateService, normalizeAppVersion, parseUpdateNotes } from './appUpdateService'
import type { BackendService } from './backendService'

const native = vi.hoisted(
  () => /* 提前建立网络、代理和进程启动替身，供提升执行的模块 mock 共用。 */ ({
    fetch: vi.fn(),
    setProxy: vi.fn(),
    spawn: vi.fn(),
  })
)
vi.mock('electron', () => /* 替换 Electron 网络分区入口，使更新测试不建立真实桌面网络会话。 */ ({
  session: {
    fromPartition: () => /* 向更新服务提供受控的查询和代理替身。 */ ({
      fetch: native.fetch,
      setProxy: native.setProxy,
    }),
  },
}))
vi.mock('node:child_process', () => /* 替换安装器启动边界，避免测试运行真实安装程序。 */ ({
  spawn: native.spawn,
}))
afterEach(() => {
  // 每个用例结束后恢复全局对象并清空 mock 调用记录。
  vi.unstubAllGlobals()
  vi.clearAllMocks()
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
    native.fetch.mockImplementation(
      async () =>
        /* 为目标版本提供受控项目元数据，供验证 Python 包版本与应用标签的对应。 */ new Response(
          `[project]\nversion="${pythonVersion}"\ndependencies=["pydantic>=2"]\n`
        )
    )
    native.fetch.mockRejectedValueOnce(new TypeError('connection failed'))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: URL) => {
        // 模拟设置、预检与统一下载接口，记录准入次数并返回共享缓存文件。
        switch (url.pathname) {
          case '/api/setting/get':
            return Response.json({
              code: 200,
              data: { Update: { ProxyAddress: 'http://127.0.0.1:7890' } },
            })
          case '/api/update/precheck':
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
      expect(checks).toBe(3)
      expect(await readFile(copied!)).toEqual(archive.toBuffer())
      await rm(shared)
      return { success: true }
    })
    const startBackend = vi.fn()
    native.spawn.mockImplementation((installer: string) => {
      // 检查安装器从前端副本目录启动，并返回可确认启动的受控子进程。
      expect(installer).toBe(join(copied!, '..', 'AUTO-MAS-Setup.exe'))
      const child = Object.assign(new EventEmitter(), { unref: vi.fn() })
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
      await service.install(backend)
      expect(native.setProxy).toHaveBeenCalledWith({ proxyRules: 'http://127.0.0.1:7890' })
      expect(await readFile(join(copied!, '..', 'AUTO-MAS-Setup.exe'), 'utf8')).toBe(
        'installer-boundary-fixture'
      )
      expect(startBackend).not.toHaveBeenCalled()
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })
})
