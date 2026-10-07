// 统一的请求错误分类。
//
// 生成物 frontend/src/api/core/request.ts 只负责把 HTTP 失败翻成 ApiError，不认识
// 「网络断了 / 后端没起来 / 数据被别的操作改过」这些用户能处理的差别；技术原文
// （状态码、statusText、body）由这里收进 detail 与 console，主文案交给 error.kind.*。
import { ApiError } from '@/api/core/ApiError'

export type AppErrorKind =
  | 'network_unavailable'
  | 'backend_unavailable'
  | 'invalid_input'
  | 'conflict'
  | 'protected_discard'
  | 'external_program'
  | 'permission_denied'
  | 'unknown'

/** 默认是否值得原样重试；调用方可用 init.retryable 覆盖。 */
const RETRYABLE: Record<AppErrorKind, boolean> = {
  network_unavailable: true,
  backend_unavailable: true,
  invalid_input: false,
  conflict: true,
  protected_discard: false,
  external_program: true,
  permission_denied: false,
  unknown: true,
}

const KIND_BY_STATUS: Record<number, AppErrorKind> = {
  400: 'invalid_input',
  401: 'permission_denied',
  403: 'permission_denied',
  409: 'conflict',
  422: 'invalid_input',
}

/** 后端 reason / 错误码（统一小写）里能直接判定的分类。 */
const KIND_BY_REASON: Record<string, AppErrorKind> = {
  protected_discard: 'protected_discard',
  structure: 'protected_discard',
  unreadable: 'protected_discard',
  external_program: 'external_program',
  not_written: 'external_program',
}

const TRANSPORT_CODES = new Set([
  'ECONNREFUSED',
  'ECONNABORTED',
  'ETIMEDOUT',
  'ERR_NETWORK',
  'ERR_CONNECTION_REFUSED',
  'ERR_CANCELED',
])

const NO_RESPONSE_PATTERN = /network error|failed to fetch|timeout|超时/i

export interface AppRequestErrorInit {
  /** 技术原文，只进详情区与日志，不做主文案。 */
  detail?: string
  retryable?: boolean
  context?: Record<string, unknown>
}

export class AppRequestError extends Error {
  readonly kind: AppErrorKind
  readonly detail?: string
  readonly retryable: boolean
  readonly context?: Record<string, unknown>

  constructor(kind: AppErrorKind, init: AppRequestErrorInit = {}) {
    super(kind)

    this.name = 'AppRequestError'
    this.kind = kind
    this.detail = init.detail
    this.retryable = init.retryable ?? RETRYABLE[kind]
    this.context = init.context
  }
}

export function isAppRequestError(e: unknown): e is AppRequestError {
  return e instanceof AppRequestError
}

const asRecord = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : undefined

interface ErrorFacts {
  message: string
  /** 一个请求是否真的发出去并收到了响应。 */
  hasResponse: boolean
  /** 传输层异常（连接被拒、超时、取消）才为 true，普通 Error 不算。 */
  transportLike: boolean
  status?: number
  reason?: string
  transportCode?: string
  url?: string
  body?: unknown
}

/** 从后端业务信封 { code, message, reason } 里取机器可读状态与原因。 */
function collectEnvelope(body: Record<string, unknown> | undefined, facts: ErrorFacts): void {
  if (!body) return

  const { code, reason } = body
  if (typeof code === 'number') facts.status ??= code
  else if (typeof code === 'string' && code) facts.reason ??= code
  if (typeof reason === 'string' && reason) facts.reason ??= reason

  const detail = asRecord(body.detail)
  if (detail && typeof detail.code === 'string') facts.reason ??= detail.code
}

function readFacts(e: unknown): ErrorFacts {
  if (typeof e === 'string') {
    return { message: e, hasResponse: false, transportLike: NO_RESPONSE_PATTERN.test(e) }
  }

  const obj = asRecord(e)
  if (!obj) return { message: String(e), hasResponse: false, transportLike: false }

  const message = typeof obj.message === 'string' ? obj.message : String(e)
  const facts: ErrorFacts = { message, hasResponse: false, transportLike: false }

  if (e instanceof ApiError) {
    facts.hasResponse = true
    facts.status = e.status
    facts.url = e.url
    facts.body = e.body
    collectEnvelope(asRecord(e.body), facts)
  }

  const response = asRecord(obj.response)
  if (response) {
    facts.hasResponse = true
    if (typeof response.status === 'number') facts.status = response.status
    facts.body ??= response.data
    collectEnvelope(asRecord(response.data), facts)
  }

  if (typeof obj.code === 'string') {
    facts.transportCode = obj.code
    if (TRANSPORT_CODES.has(obj.code)) facts.transportLike = true
  }
  if (obj.isAxiosError === true || obj.request !== undefined || obj.config !== undefined) {
    facts.transportLike = true
  }
  if (!facts.hasResponse && NO_RESPONSE_PATTERN.test(message)) facts.transportLike = true

  return facts
}

function classify(facts: ErrorFacts): AppErrorKind {
  if (!facts.hasResponse) {
    if (!facts.transportLike) return 'unknown'

    const { transportCode, message } = facts
    if (transportCode === 'ERR_CANCELED') return 'unknown'
    if (transportCode === 'ECONNREFUSED' || /ERR_CONNECTION_REFUSED|ECONNREFUSED/i.test(message)) {
      return 'backend_unavailable'
    }
    if (
      transportCode === 'ECONNABORTED' ||
      transportCode === 'ETIMEDOUT' ||
      /timeout|超时/i.test(message)
    ) {
      return 'network_unavailable'
    }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return 'network_unavailable'
    return 'network_unavailable'
  }

  if (facts.reason) {
    const byReason = KIND_BY_REASON[facts.reason.toLowerCase()]
    if (byReason) return byReason
  }

  if (facts.status !== undefined) {
    const byStatus = KIND_BY_STATUS[facts.status]
    if (byStatus) return byStatus
  }

  return 'unknown'
}

/** 技术原文：状态码、传输码、URL、异常 message 与响应体。 */
function buildDetail(facts: ErrorFacts): string | undefined {
  const parts: string[] = []
  if (facts.status !== undefined) parts.push(`HTTP ${facts.status}`)
  if (facts.transportCode) parts.push(facts.transportCode)
  if (facts.url) parts.push(facts.url)
  if (facts.message) parts.push(facts.message)
  if (facts.body !== undefined) {
    try {
      parts.push(JSON.stringify(facts.body))
    } catch {
      // 响应体不可序列化时只保留其余部分
    }
  }

  const detail = parts.filter(Boolean).join(' | ')
  return detail || undefined
}

/**
 * 把任意抛出物收敛成 AppRequestError。
 *
 * 已经是 AppRequestError 的原样返回；其余按「无响应/超时 → network_unavailable，
 * 连接被拒 → backend_unavailable，HTTP 400/422 → invalid_input，403/401 →
 * permission_denied，409 → conflict，其余 5xx → unknown」分类。
 */
export function toAppError(e: unknown): AppRequestError {
  if (isAppRequestError(e)) return e

  const facts = readFacts(e)
  const kind = classify(facts)
  const detail = buildDetail(facts)

  const context: Record<string, unknown> = {}
  if (facts.status !== undefined) context.status = facts.status
  if (facts.reason) context.code = facts.reason
  if (facts.transportCode) context.transportCode = facts.transportCode
  if (facts.url) context.url = facts.url

  // 技术原文只进 detail 与 console，主文案由 error.kind.* 渲染。
  console.error('[appError]', kind, detail, e)

  return new AppRequestError(kind, {
    detail,
    context: Object.keys(context).length > 0 ? context : undefined,
  })
}
