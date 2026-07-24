import axios, { type InternalAxiosRequestConfig } from 'axios'

import { OpenAPI } from '@/api/core/OpenAPI'

export const HTTP_AUTH_HEADER = 'X-AUTO-MAS-Auth-Token'

const DEFAULT_HTTP_BASE = 'http://127.0.0.1:36163'
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const API_PATH_PATTERN = /^\/(?:api|plugin)(?:\/|$)/
const AUTH_RETRY_MARKER = '__autoMasHttpAuthRetried'

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  [AUTH_RETRY_MARKER]?: boolean
}

interface CachedToken {
  base: string
  token: string
}

let cachedToken: CachedToken | null = null
let pendingToken: { base: string; promise: Promise<string> } | null = null
let interceptorsInstalled = false
let tokenEpoch = 0

const nativeFetch = globalThis.fetch.bind(globalThis)

const normalizeBase = (base = OpenAPI.BASE): string =>
  (String(base || DEFAULT_HTTP_BASE).trim() || DEFAULT_HTTP_BASE).replace(/\/+$/, '')

const validateToken = (value: unknown): string => {
  const token = typeof value === 'string' ? value.trim() : ''
  if (!/^[A-Za-z0-9._~-]{32,512}$/.test(token)) {
    throw new Error('后端未返回有效的本机 HTTP 认证令牌')
  }
  return token
}

const requestUrl = (input: RequestInfo | URL): string =>
  input instanceof Request ? input.url : String(input)

const isProtectedRequest = (url: string, method: string, base = OpenAPI.BASE): boolean => {
  if (!UNSAFE_METHODS.has(method.toUpperCase())) return false

  try {
    const backend = new URL(normalizeBase(base))
    const target = new URL(url, backend)
    return target.origin === backend.origin && API_PATH_PATTERN.test(target.pathname)
  } catch {
    return false
  }
}

const fetchTokenFromMetadata = async (base: string): Promise<string> => {
  const response = await nativeFetch(`${base}/api/core/ws_meta`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  if (!response.ok) {
    throw new Error(`本机 HTTP 认证协商失败: ${response.status}`)
  }

  const metadata = (await response.json()) as { wsAuthToken?: unknown }
  return validateToken(metadata.wsAuthToken)
}

const acquireToken = async (base: string): Promise<string> => {
  const getElectronToken = window.electronAPI?.getBackendAuthToken
  if (typeof getElectronToken === 'function') {
    return validateToken(await getElectronToken())
  }
  return await fetchTokenFromMetadata(base)
}

/**
 * Return the process-scoped token for the configured backend.
 *
 * Electron obtains it through the isolated preload bridge. Browser/Vite
 * development obtains it from the loopback-only metadata endpoint.
 */
export const getLocalHttpAuthToken = async (base = OpenAPI.BASE): Promise<string> => {
  const normalizedBase = normalizeBase(base)
  if (cachedToken?.base === normalizedBase) return cachedToken.token
  if (pendingToken?.base === normalizedBase) return await pendingToken.promise

  const requestEpoch = tokenEpoch
  const promise = acquireToken(normalizedBase).then(token => {
    if (requestEpoch === tokenEpoch) cachedToken = { base: normalizedBase, token }
    return token
  })
  pendingToken = { base: normalizedBase, promise }

  try {
    return await promise
  } finally {
    if (pendingToken?.promise === promise) pendingToken = null
  }
}

export const invalidateLocalHttpAuthToken = (base = OpenAPI.BASE): void => {
  const normalizedBase = normalizeBase(base)
  tokenEpoch += 1
  if (cachedToken?.base === normalizedBase) cachedToken = null
  if (pendingToken?.base === normalizedBase) pendingToken = null
}

/** Fetch helper for the small number of non-Axios mutation calls. */
export const authenticatedApiFetch = async (
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> => {
  const method = String(
    init.method || (input instanceof Request ? input.method : 'GET')
  ).toUpperCase()
  const url = requestUrl(input)
  if (!isProtectedRequest(url, method)) return await nativeFetch(input, init)

  const base = normalizeBase()
  const execute = async (token: string, retryInput: RequestInfo | URL): Promise<Response> => {
    const headers = new Headers(input instanceof Request ? input.headers : undefined)
    new Headers(init.headers).forEach((value, key) => headers.set(key, value))
    headers.set(HTTP_AUTH_HEADER, token)
    return await nativeFetch(retryInput, { ...init, headers })
  }

  const retryInput = input instanceof Request ? input.clone() : input
  let response = await execute(await getLocalHttpAuthToken(base), input)
  if (response.status === 401) {
    invalidateLocalHttpAuthToken(base)
    response = await execute(await getLocalHttpAuthToken(base), retryInput)
  }
  return response
}

/** Install process-token authentication for generated and direct Axios calls. */
export const installLocalHttpSecurity = (): void => {
  if (interceptorsInstalled) return
  interceptorsInstalled = true

  axios.interceptors.request.use(async config => {
    const method = String(config.method || 'GET').toUpperCase()
    const url = String(config.url || '')
    if (!isProtectedRequest(url, method)) return config

    config.headers.set(HTTP_AUTH_HEADER, await getLocalHttpAuthToken())
    return config
  })

  axios.interceptors.response.use(undefined, async error => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) {
      throw error
    }

    const config = error.config as RetriableRequestConfig
    const method = String(config.method || 'GET').toUpperCase()
    if (config[AUTH_RETRY_MARKER] || !isProtectedRequest(String(config.url || ''), method)) {
      throw error
    }

    config[AUTH_RETRY_MARKER] = true
    invalidateLocalHttpAuthToken()
    return await axios.request(config)
  })
}
