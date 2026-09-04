// BetterGI 一条龙「设置项」API（右栏按任务分组展示/编辑）
// 走自写 axios + OpenAPI.BASE，不依赖 OpenAPI 生成（新增后端接口时无需重跑生成器）。
import axios from 'axios'
import { OpenAPI } from '@/api'

const logger = window.electronAPI.getLogger('BetterGI一条龙设置')

interface Envelope<T> {
  code: number
  status: string
  message?: string
  data?: T
}

const url = (path: string) => `${OpenAPI.BASE}/api/scripts/bettergi${path}`

const unwrap = <T>(payload: Envelope<T>): T => {
  if (payload && typeof payload === 'object' && 'code' in payload) {
    if (payload.code !== 200) {
      throw new Error(payload.message || 'BetterGI 一条龙设置请求失败')
    }
    return (payload.data === undefined ? ({} as T) : payload.data) as T
  }
  return payload as T
}

/**
 * 读取某用户一条龙配置的设置项（per-user 副本 → BGI 实配 → 内置模板的种子顺序）。
 */
export const fetchOneDragonSettings = async (
  scriptId: string,
  userId: string,
  configName: string
): Promise<Record<string, unknown>> => {
  try {
    const response = await axios.get<Envelope<Record<string, unknown>>>(url('/one-dragon/settings'), {
      params: { scriptId, userId, configName },
    })
    return unwrap(response.data)
  } catch (error) {
    if (axios.isAxiosError<Envelope<unknown>>(error) && error.response?.data?.message) {
      throw new Error(String(error.response.data.message))
    }
    throw error instanceof Error ? error : new Error(String(error))
  }
}

/**
 * 把右栏编辑的设置项写回该用户一条龙配置副本（不触碰 BGI 同名实配）。
 * 返回是否成功；失败时抛错由调用方提示。
 */
export const saveOneDragonSettings = async (
  scriptId: string,
  userId: string,
  configName: string,
  settings: Record<string, unknown>
): Promise<void> => {
  try {
    const response = await axios.post<Envelope<unknown>>(url('/one-dragon/settings'), {
      scriptId,
      userId,
      configName,
      settings,
    })
    unwrap(response.data)
  } catch (error) {
    logger.error(error instanceof Error ? error.message : String(error))
    if (axios.isAxiosError<Envelope<unknown>>(error) && error.response?.data?.message) {
      throw new Error(String(error.response.data.message))
    }
    throw error instanceof Error ? error : new Error(String(error))
  }
}
