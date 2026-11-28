const HEALTH_RETRY_BUDGET_MS = 60_000
const HEALTH_REQUEST_TIMEOUT_MS = 5_000
export const HEALTH_POLL_INTERVAL_MS = 500

export interface StartupHealth {
  version?: string
  businessStatus?: string
  backgroundStatus?: string
  backgroundError?: string | null
  businessMessage?: string | null
}

export class StartupHealthTimeout extends Error {
  constructor(cause: unknown) {
    super('后端健康检查超时', { cause })
  }
}

export async function waitForHealthPoll(delayMs: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted()
  let timer: ReturnType<typeof setTimeout> | undefined
  let onAbort: (() => void) | undefined
  try {
    await new Promise<void>((resolve, reject) => {
      timer = setTimeout(resolve, delayMs)
      onAbort = () => reject(signal.reason)
      signal.addEventListener('abort', onAbort)
    })
  } finally {
    clearTimeout(timer)
    if (onAbort) signal.removeEventListener('abort', onAbort)
  }
}

/** 对同一个后端重试暂时失联。业务等待的总截止时间可以进一步缩短本次预算。 */
export async function readStartupHealth(
  baseUrl: string,
  signal: AbortSignal,
  businessDeadline = Infinity
): Promise<StartupHealth> {
  const deadline = Math.min(Date.now() + HEALTH_RETRY_BUDGET_MS, businessDeadline)
  let pause = HEALTH_POLL_INTERVAL_MS
  let lastFailure: unknown
  while (Date.now() < deadline) {
    signal.throwIfAborted()
    const request = new AbortController()
    const timer = setTimeout(
      () => request.abort(new Error('单次健康检查请求超时')),
      Math.min(HEALTH_REQUEST_TIMEOUT_MS, deadline - Date.now())
    )
    let response: Response | undefined
    let health: unknown
    try {
      response = await fetch(`${baseUrl}/api/core/health`, {
        signal: AbortSignal.any([signal, request.signal]),
      })
      if (response.ok) health = await response.json()
    } catch (error) {
      signal.throwIfAborted()
      if (error instanceof SyntaxError) throw new Error('后端健康检查响应无效', { cause: error })
      lastFailure = error
      response = undefined
    } finally {
      clearTimeout(timer)
    }

    signal.throwIfAborted()
    if (response?.ok) {
      if (!health || typeof health !== 'object' || Array.isArray(health))
        throw new Error('后端健康检查响应无效')
      return health as StartupHealth
    }
    if (response) {
      const error = new Error(`读取后端健康检查失败 (${response.status})`)
      if (![502, 503, 504].includes(response.status)) throw error
      lastFailure = error
    }
    const remaining = deadline - Date.now()
    if (remaining <= 0) break
    await waitForHealthPoll(Math.min(pause, remaining), signal)
    pause = 1_000
  }
  signal.throwIfAborted()
  throw new StartupHealthTimeout(lastFailure)
}
