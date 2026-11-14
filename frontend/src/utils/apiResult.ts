type ResponseWithCode = { code?: number; message?: string | null }

/** 只显示后端错误文案及校验位置，不泄露请求中的密码和密钥。 */
export { getApiErrorMessage as apiErrorMessage } from '@/utils/apiError'
import { getApiErrorMessage as apiErrorMessage } from '@/utils/apiError'

/** 统一检查后端响应信封。 */
export const responseError = (response: ResponseWithCode, fallback: string): Error | null =>
  /* 把非成功业务响应转换为错误，成功响应返回空值供调用方继续读取数据。 */ response.code === 200
    ? null
    : new Error(response.message || fallback)

/** 生成客户端请求统一校验结果，失败时保留安全的后端原因。 */
export const requestApi = async <T extends ResponseWithCode>(
  request: () => PromiseLike<T>,
  fallback: string
): Promise<T> => {
  // 执行生成客户端请求并统一检查业务结果，将请求或业务异常转换为可展示的错误消息。
  try {
    const response = await request()
    const error = responseError(response, fallback)
    if (error) throw error
    return response
  } catch (error) {
    throw new Error(apiErrorMessage(error, fallback))
  }
}
