import type { net as electronNet } from 'electron'
import { Readable } from 'stream'
import type { OnlineFetch, OnlineResponseLike } from './onlineAppearanceService'

type NetModule = Pick<typeof electronNet, 'request'>

function headerReader(headers: Record<string, string | string[]>): OnlineResponseLike['headers'] {
  const values = new Map<string, string>()
  for (const [name, value] of Object.entries(headers)) {
    values.set(name.toLowerCase(), Array.isArray(value) ? value.join(', ') : String(value))
  }
  return { get: name => values.get(name.toLowerCase()) ?? null }
}

/**
 * 在线外观用的请求实现：基于 Electron net.request（走系统代理），**不跟随重定向**，
 * 每一跳 3xx 连同 Location 原样交给在线外观服务校验后再由它请求下一跳。
 * 不用 net.fetch：它跟随重定向后 Response.url 为空，redirect: 'manual' 又直接报错拿不到 Location，
 * 没法在跟随之前拦下降级到 http 的那一跳。
 */
export function createNetRequestFetch(net: NetModule): OnlineFetch {
  return (url, init) =>
    new Promise<OnlineResponseLike>((resolve, reject) => {
      if (init.signal.aborted) {
        reject(new Error('请求已取消'))
        return
      }
      const request = net.request({ url, method: 'GET', redirect: 'manual' })
      for (const [name, value] of Object.entries(init.headers)) request.setHeader(name, value)

      let settled = false
      let body: Readable | undefined
      const fail = (error: Error): void => {
        if (settled) return
        settled = true
        reject(error)
      }
      const onAbort = (): void => {
        request.abort()
        // 响应已经到了还在读 body 时，要让读取方立刻报错，不然会一直等下去。
        body?.destroy(new Error('请求已取消'))
        fail(new Error('请求已取消'))
      }
      init.signal.addEventListener('abort', onAbort, { once: true })

      request.on('redirect', (statusCode, _method, redirectUrl, responseHeaders) => {
        // 不调用 followRedirect，这次请求随即被取消；下一跳由服务校验后另发。
        settled = true
        init.signal.removeEventListener('abort', onAbort)
        request.abort()
        resolve({
          status: statusCode,
          headers: headerReader({ ...responseHeaders, location: redirectUrl }),
          body: null,
        })
      })
      request.on('response', response => {
        if (settled) return
        settled = true
        // Electron 的 IncomingMessage 实际是 Node Readable，net.fetch 内部也是这样转成 Web 流。
        body = response as unknown as Readable
        resolve({
          status: response.statusCode,
          headers: headerReader(response.headers),
          body: Readable.toWeb(body) as unknown as NonNullable<OnlineResponseLike['body']>,
        })
      })
      request.on('error', error => fail(error))
      request.end()
    })
}
