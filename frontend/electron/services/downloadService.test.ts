import { createServer } from 'node:http'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vite-plus/test'

import { SmartDownloader } from './downloadService'

vi.mock('./logger', () => ({
  getLogger: () => ({ info: vi.fn(), debug: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

describe('下载故障的网络分类', () => {
  it('连接被重置时报告网络失败，无效文件响应保留原分类', async () => {
    let resetConnection = true
    const server = createServer((request, response) => {
      if (resetConnection) request.socket.destroy()
      else response.writeHead(200, { 'Content-Type': 'text/html', 'Content-Length': '0' }).end()
    })
    const directory = mkdtempSync(join(tmpdir(), 'mas-download-failure-'))
    try {
      await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
      const address = server.address()
      if (!address || typeof address === 'string') throw new Error('未取得测试端口')
      const url = `http://127.0.0.1:${address.port}/runtime.exe`
      const downloader = new SmartDownloader()
      expect(await downloader.download(url, join(directory, 'runtime.exe'))).toMatchObject({
        success: false,
        networkUnavailable: true,
      })
      resetConnection = false
      const invalidFile = await downloader.download(url, join(directory, 'runtime.exe'))
      expect(invalidFile.success).toBe(false)
      expect(invalidFile.networkUnavailable).toBeUndefined()
    } finally {
      await new Promise<void>((resolve, reject) =>
        server.close(error => (error ? reject(error) : resolve()))
      )
      rmSync(directory, { recursive: true, force: true })
    }
  })
})
