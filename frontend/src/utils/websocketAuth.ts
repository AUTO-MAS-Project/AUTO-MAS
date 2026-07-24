import { getLocalHttpAuthToken, invalidateLocalHttpAuthToken } from '@/utils/httpSecurity'

const WS_META_PATH = '/api/core/ws_meta'
const WS_AUTH_SUBPROTOCOL_PREFIX = 'auto-mas-auth.'
const DEFAULT_TIMEOUT_MS = 3000

interface WebSocketMeta {
  devMode?: boolean
  wsPath?: string
}

export interface AuthenticatedWebSocketHandshake {
  authProtocol: string
  devMode: boolean
  wsPath?: string
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
type TokenProvider = (base?: string) => Promise<string>

export const createWebSocketAuthProtocol = (token: unknown): string | undefined => {
  if (typeof token !== 'string') return undefined
  const normalized = token.trim()
  return normalized ? `${WS_AUTH_SUBPROTOCOL_PREFIX}${normalized}` : undefined
}

export const buildWebSocketMetaUrl = (apiBase: string): string => {
  let normalized = String(apiBase || '').trim()
  if (normalized.startsWith('ws://')) {
    normalized = `http://${normalized.slice('ws://'.length)}`
  } else if (normalized.startsWith('wss://')) {
    normalized = `https://${normalized.slice('wss://'.length)}`
  }
  return normalized ? `${normalized.replace(/\/+$/, '')}${WS_META_PATH}` : WS_META_PATH
}

export const fetchAuthenticatedWebSocketHandshake = async (
  apiBase: string,
  fetcher: Fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = DEFAULT_TIMEOUT_MS,
  tokenProvider: TokenProvider = getLocalHttpAuthToken
): Promise<AuthenticatedWebSocketHandshake> => {
  invalidateLocalHttpAuthToken(apiBase)

  // A failed WS handshake has no HTTP 401 response to invalidate the old process token.
  const controller = new AbortController()
  let rejectTimeout: ((reason?: unknown) => void) | undefined
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    rejectTimeout = reject
  })
  const timeout = globalThis.setTimeout(() => {
    controller.abort()
    rejectTimeout?.(new Error('WebSocket 本机认证协商超时'))
  }, timeoutMs)
  try {
    const handshake = Promise.all([
      tokenProvider(apiBase),
      fetcher(buildWebSocketMetaUrl(apiBase), {
        method: 'GET',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      }),
    ])
    const [token, response] = await Promise.race([handshake, timeoutPromise])
    if (!response.ok) {
      throw new Error(`WebSocket 元信息请求失败: HTTP ${response.status}`)
    }

    const meta = (await response.json()) as WebSocketMeta
    const authProtocol = createWebSocketAuthProtocol(token)
    if (!authProtocol) {
      throw new Error('后端未返回本地 WebSocket 握手令牌')
    }
    const wsPath = typeof meta.wsPath === 'string' ? meta.wsPath.trim() : ''
    return {
      authProtocol,
      devMode: meta.devMode === true,
      ...(wsPath ? { wsPath } : {}),
    }
  } finally {
    globalThis.clearTimeout(timeout)
  }
}
