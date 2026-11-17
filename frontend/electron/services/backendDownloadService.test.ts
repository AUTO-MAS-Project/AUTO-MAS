import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { downloadAndCopy, DownloadWriterUnconfirmed } from './backendDownloadService'

afterEach(() => /* 每个测试结束后恢复网络等被替换的全局对象。 */ vi.unstubAllGlobals())
describe('前端下载副本与后端引用', () => {
  // 组织前端复制下载结果及释放独立 URL 引用的契约测试。
  it('复制成功后才释放自己的 URL 引用，保留共享原件', async () => {
    // 验证复制产物后仅释放当前前端引用，后端共享原文件仍然保留。
    const root = await mkdtemp(join(tmpdir(), 'mas-download-client-'))
    const source = join(root, 'shared')
    const destination = join(root, 'frontend', 'package.zip')
    await writeFile(source, 'package')
    const calls: { path: string; owner?: string }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: URL, options: RequestInit) => {
        // 模拟统一下载的申请、成功查询与释放接口，并确认释放发生在复制完成之后。
        const body = JSON.parse(options.body as string)
        calls.push({ path: url.pathname, owner: body.owner })
        if (url.pathname.endsWith('/request')) return Response.json({ code: 200, accepted: true })
        if (url.pathname.endsWith('/query'))
          return Response.json({ code: 200, data: { state: 'succeeded', path: source } })
        expect(await readFile(destination, 'utf8')).toBe('package')
        return Response.json({ code: 200 })
      })
    )
    try {
      await downloadAndCopy(
        'http://127.0.0.1:36163',
        { url: 'https://example.test/file', rid: 'one' },
        destination
      )
      expect(await readFile(source, 'utf8')).toBe('package')
      expect(
        calls.map(
          item => /* 提取请求路径顺序，供断言下载申请、查询和释放的公共调用流程。 */ item.path
        )
      ).toEqual(['/api/download/request', '/api/download/query', '/api/download/release'])
      expect(calls[0].owner).toBe(calls[2].owner)
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  })
  it('停写未确认保持失败，不返回文件路径', async () => {
    // 验证下载器无法确认停写时返回专门错误，不向前端暴露可安装文件。
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: URL) => {
        // 模拟任务受理后停写未确认及释放拒绝的后端结果。
        if (url.pathname.endsWith('/request')) return Response.json({ code: 200, accepted: true })
        if (url.pathname.endsWith('/query'))
          return Response.json({ code: 200, data: { state: 'failed', writer_unconfirmed: true } })
        return Response.json({ code: 409, message: 'download_writer_unconfirmed' })
      })
    )
    await expect(
      downloadAndCopy('http://127.0.0.1:36163', { url: 'https://example.test/file' }, 'unused')
    ).rejects.toBeInstanceOf(DownloadWriterUnconfirmed)
  })
})
