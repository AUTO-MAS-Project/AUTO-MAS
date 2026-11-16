import type { CancelablePromise } from '@/api'

/** 将 Query 的取消传到生成客户端的底层请求，并在完成后释放监听。 */
export async function queryRequest<T>(
  signal: AbortSignal,
  createRequest: () => CancelablePromise<T>
): Promise<T> {
  signal.throwIfAborted()
  const request = createRequest()
  const cancel = () => request.cancel()
  signal.addEventListener('abort', cancel, { once: true })
  try {
    return await request
  } finally {
    signal.removeEventListener('abort', cancel)
  }
}
