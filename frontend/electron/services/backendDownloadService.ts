import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { randomUUID } from 'node:crypto'
export interface DownloadRequest {
  url: string
  rid?: string | null
  content_hash?: string | null
  downloader?: 'builtin' | 'fluxdown' | null
}
export interface DownloadSnapshot {
  state?: string
  path?: string | null
  writer_unconfirmed?: boolean
  error_code?: string | null
  downloaded?: number
  total?: number
  speed?: number
}
interface OutBase {
  code?: number
  message?: string
}
interface DownloadAcquireOut extends OutBase {
  accepted?: boolean
}
interface DownloadOut extends OutBase {
  data: DownloadSnapshot
}
export interface CoreUpgradePrecheckOut extends OutBase {
  compatible: boolean
  conflicts?: { message: string }[]
}

export class DownloadWriterUnconfirmed extends Error {}

export async function backendRequest<T>(
  baseUrl: string,
  endpoint: string,
  body: unknown,
  signal?: AbortSignal
): Promise<T> {
  // 向本地后端发送可取消的 JSON 请求，统一检查 HTTP 与业务结果后返回契约数据。
  const response = await fetch(new URL(endpoint, baseUrl), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw new Error(`后端请求失败 (${response.status})`)
  const result = (await response.json()) as T & { code?: number; message?: string }
  if (result.message === 'download_writer_unconfirmed')
    throw new DownloadWriterUnconfirmed('下载尚未确认停写')
  if (result.code !== undefined && result.code !== 200)
    throw new Error(result.message || '后端操作失败')
  return result
}

/** 完成副本后才释放引用；取消只释放自己的引用，并等待后端确认停写。 */
export async function downloadAndCopy(
  baseUrl: string,
  request: DownloadRequest,
  destination: string,
  options: { signal?: AbortSignal; progress?: (snapshot: DownloadSnapshot) => void } = {}
): Promise<void> {
  // 为前端建立独立下载引用，忙时重试并轮询进度，成功后复制文件到前端目录，最终释放后端引用。
  const owner = `frontend:${randomUUID()}`
  let accepted = false
  const pause = () =>
    /* 在下载受理重试或状态轮询之间等待固定间隔，避免持续占用后端接口。 */ new Promise<void>(
      resolve => /* 在轮询间隔到期后唤醒等待中的下载流程。 */ setTimeout(resolve, 500)
    )
  try {
    while (!accepted) {
      options.signal?.throwIfAborted()
      accepted =
        (
          await backendRequest<DownloadAcquireOut>(baseUrl, '/api/download/request', {
            owner,
            request,
          })
        ).accepted === true
      if (!accepted) await pause()
    }
    while (true) {
      options.signal?.throwIfAborted()
      const result = (
        await backendRequest<DownloadOut>(baseUrl, '/api/download/query', request, options.signal)
      ).data
      options.progress?.(result)
      if (result.writer_unconfirmed) throw new DownloadWriterUnconfirmed('下载尚未确认停写')
      if (result.state === 'succeeded' && result.path) {
        await fs.mkdir(path.dirname(destination), { recursive: true })
        await fs.copyFile(result.path, destination)
        options.signal?.throwIfAborted()
        return
      }
      if (['failed', 'cancelled', 'not_found'].includes(result.state ?? ''))
        throw new Error(`下载未完成：${result.error_code ?? result.state}`)
      await pause()
    }
  } finally {
    // 申请响应丢失也可能已计数；幂等释放 owner 可以同时覆盖该边界。
    await backendRequest<OutBase>(baseUrl, '/api/download/release', { owner, url: request.url })
  }
}
