import { ApiError } from '@/api'

type ResponseWithCode = { code?: number; message?: string | null }

/** 只显示后端错误文案及校验位置，不泄露请求中的密码和密钥。 */
export const apiErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof ApiError) {
    const body: Record<string, unknown> | undefined = error.body && typeof error.body === 'object'
      ? error.body
      : undefined
    if (typeof body?.message === 'string' && body.message) return body.message
    if (typeof body?.detail === 'string' && body.detail) return body.detail
    if (Array.isArray(body?.detail)) {
      const details = body.detail
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const value = item as { loc?: unknown; msg?: unknown }
          const location = Array.isArray(value.loc) ? value.loc.join('.') : ''
          return `${location}: ${typeof value.msg === 'string' ? value.msg : ''}`.replace(/^: /, '')
        })
        .filter(Boolean)
      if (details.length) return details.join('; ')
    }
  }
  return error instanceof Error && error.message ? error.message : fallback
}

/** 统一检查后端响应信封。 */
export const responseError = (response: ResponseWithCode, fallback: string): Error | null =>
  response.code === 200 ? null : new Error(response.message || fallback)

/** 生成客户端请求统一校验结果，失败时保留安全的后端原因。 */
export const requestApi = async <T extends ResponseWithCode>(
  request: () => PromiseLike<T>,
  fallback: string,
): Promise<T> => {
  try {
    const response = await request()
    const error = responseError(response, fallback)
    if (error) throw error
    return response
  } catch (error) {
    throw new Error(apiErrorMessage(error, fallback))
  }
}

