import { createServer, type ServerResponse } from 'node:http'
import { mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vite-plus/test'

import { SmartDownloader } from './downloadService'

const logger = vi.hoisted(() => ({
  info: vi.fn(),
  debug: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}))
vi.mock('./logger', () => ({ getLogger: () => logger }))

describe('下载故障的网络分类', () => {
  it('连接被重置时报告网络失败，无效文件响应保留原分类', async () => {
    let mode: 'reset' | 'html' | 'fragments' = 'reset'
    const responses: ServerResponse[] = []
    let rangeRequests = 0
    let receivedAll!: () => void
    const allRequests = new Promise<void>(resolve => {
      receivedAll = resolve
    })
    const server = createServer((request, response) => {
      response.setHeader('Connection', 'close')
      if (mode === 'reset') {
        request.socket.destroy()
      } else if (mode === 'html') {
        response.writeHead(200, { 'Content-Type': 'text/html', 'Content-Length': '0' }).end()
      } else if (request.method === 'HEAD') {
        response
          .writeHead(200, {
            'Content-Length': String(12 * 1024 * 1024),
            'Accept-Ranges': 'bytes',
          })
          .end()
      } else {
        rangeRequests += 1
        if (request.headers.range?.startsWith('bytes=0-')) request.socket.destroy()
        else {
          response.writeHead(206, { 'Content-Length': String(3 * 1024 * 1024) })
          response.write('partial')
          responses.push(response)
        }
        if (rangeRequests === 4) receivedAll()
      }
    })
    const directory = mkdtempSync(join(tmpdir(), 'mas-download-failure-'))
    try {
      await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
      const address = server.address()
      if (!address || typeof address === 'string') throw new Error('未取得测试端口')
      const url = `http://127.0.0.1:${address.port}/runtime.exe`
      const downloader = new SmartDownloader()
      const savePath = join(directory, 'runtime.exe')
      expect(await downloader.download(url, savePath)).toMatchObject({
        success: false,
        networkUnavailable: true,
      })
      expect(readdirSync(directory)).toEqual([])
      mode = 'html'
      const invalidFile = await downloader.download(url, savePath)
      expect(invalidFile.success).toBe(false)
      expect(invalidFile.networkUnavailable).toBeUndefined()
      expect(readdirSync(directory)).toEqual([])

      mode = 'fragments'
      writeFileSync(savePath, 'partial download from an interrupted attempt')
      logger.error.mockClear()
      let completed = false
      const pending = downloader.download(url, savePath).then(result => {
        completed = true
        return result
      })
      await allRequests
      // 先确认客户端已观察到首片错误，避免仅靠服务器收到请求就断言仍在等待。
      await vi.waitFor(() => expect(logger.error).toHaveBeenCalled())
      expect(rangeRequests).toBe(4)
      expect(responses).toHaveLength(3)
      expect(responses.every(response => !response.destroyed)).toBe(true)
      expect(completed).toBe(false)
      expect(readdirSync(directory)).toEqual(['runtime.exe'])
      for (const response of responses) response.destroy()
      expect(await pending).toMatchObject({ success: false, networkUnavailable: true })
      expect(readdirSync(directory)).toEqual([])
      await vi.waitFor(async () => {
        const connections = await new Promise<number>((resolve, reject) =>
          server.getConnections((error, count) => (error ? reject(error) : resolve(count)))
        )
        expect(connections).toBe(0)
      })
    } finally {
      for (const response of responses) response.destroy()
      server.closeAllConnections()
      await new Promise<void>((resolve, reject) =>
        server.close(error => (error ? reject(error) : resolve()))
      )
      rmSync(directory, { recursive: true, force: true })
    }
  })
})
