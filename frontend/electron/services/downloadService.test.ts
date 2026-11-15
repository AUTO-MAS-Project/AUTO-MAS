import { createServer, type ServerResponse } from 'node:http'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vite-plus/test'

import { SmartDownloader } from './downloadService'

vi.mock('./logger', () => ({
  getLogger: () => ({ info: vi.fn(), debug: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

describe('下载故障的网络分类', () => {
  it('首个分片断开后，仍等其余分片收口才返回可恢复的网络失败', async () => {
    const responses: ServerResponse[] = []
    let rangeRequests = 0
    let receivedAll: (() => void) | undefined
    const allRequests = new Promise<void>(resolve => {
      receivedAll = resolve
    })
    const server = createServer((request, response) => {
      if (request.method === 'HEAD') {
        response
          .writeHead(200, { 'Content-Length': String(12 * 1024 * 1024), 'Accept-Ranges': 'bytes' })
          .end()
        return
      }
      rangeRequests += 1
      if (request.headers.range?.startsWith('bytes=0-')) request.socket.destroy()
      else {
        response.writeHead(206)
        response.flushHeaders()
        responses.push(response)
      }
      if (rangeRequests === 4) receivedAll?.()
    })
    const directory = mkdtempSync(join(tmpdir(), 'mas-download-fragments-'))
    try {
      await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
      const address = server.address()
      if (!address || typeof address === 'string') throw new Error('未取得测试端口')
      let completed = false
      const pending = new SmartDownloader().download(
        `http://127.0.0.1:${address.port}/runtime.exe`,
        join(directory, 'runtime.exe')
      )
      void pending.then(() => {
        completed = true
      })
      await allRequests
      await new Promise<void>(resolve => setImmediate(resolve))
      expect(completed).toBe(false)
      for (const response of responses) response.destroy()
      expect(await pending).toMatchObject({ success: false, networkUnavailable: true })
    } finally {
      for (const response of responses) response.destroy()
      server.closeAllConnections()
      await new Promise<void>((resolve, reject) =>
        server.close(error => (error ? reject(error) : resolve()))
      )
      rmSync(directory, { recursive: true, force: true })
    }
  })

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
