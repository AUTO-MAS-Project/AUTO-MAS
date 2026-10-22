import { ApiError } from '@/api'

/** 非 2xx 的后端说明在 ApiError.body；普通异常和非异常值使用各自的可读消息或兜底。 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (body && typeof body === 'object') {
      if ('message' in body && typeof body.message === 'string' && body.message.trim()) {
        return body.message
      }
      if ('detail' in body && typeof body.detail === 'string' && body.detail.trim()) {
        return body.detail
      }
    }
  }
  if (error instanceof Error && error.message.trim()) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return fallback
}

/** 创建账号等流程需要区分业务冲突；没有业务码时保留实际 HTTP 状态。 */
export function getApiErrorCode(error: unknown): number | null {
  if (!(error instanceof ApiError)) return null
  const body: unknown = error.body
  if (body && typeof body === 'object' && 'code' in body && typeof body.code === 'number') {
    return body.code
  }
  return error.status
}
