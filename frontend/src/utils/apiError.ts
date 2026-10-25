import { ApiError } from '@/api'
import type { OutBase } from '@/api'
import { translate } from '@/i18n'

/** 后端失败响应里带语言无关的错误码与占位符参数，见 app/models/error_codes.py。 */
type LocalizedFailure = Pick<OutBase, 'message' | 'errorCode' | 'errorParams'>

const localizeErrorCode = (
  errorCode: string | null | undefined,
  errorParams: OutBase['errorParams']
): string | null => {
  if (!errorCode) return null
  const key = `apiErrors.${errorCode}`
  const named =
    errorParams && typeof errorParams === 'object'
      ? (errorParams as Record<string, unknown>)
      : undefined
  const localized = translate(key, named)
  // 词表里没有这条码时 i18n 会原样返回 key，视为取不到，交由下层兜底
  return localized && localized !== key ? localized : null
}

/**
 * 把后端响应里的说明转成当前语言的文案。
 *
 * 后端失败多走 HTTP 200 + `code: 500`，响应正常返回，所以非 2xx 的 ApiError 通道覆盖不到，
 * 调用点要自己调这个函数：优先 `errorCode` 对应的词条，其次后端 message（中文兜底），
 * 最后才是调用点的兜底词条。
 */
export function resolveOutBaseMessage(
  response: Partial<LocalizedFailure> | null | undefined,
  fallbackKey: string
): string {
  const localized = localizeErrorCode(response?.errorCode, response?.errorParams)
  if (localized) return localized
  const message = response?.message
  if (typeof message === 'string' && message.trim()) return message
  return translate(fallbackKey)
}

/** 非 2xx 的后端说明在 ApiError.body；普通异常和非异常值使用各自的可读消息或兜底。 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (body && typeof body === 'object') {
      const failure = body as Partial<LocalizedFailure>
      const localized = localizeErrorCode(failure.errorCode, failure.errorParams)
      if (localized) return localized
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
