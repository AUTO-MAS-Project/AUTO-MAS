import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

/**
 * MaaFW 项目更新客户端。
 *
 * `POST /api/scripts/maafw/update` 已进生成的 `MaaFwService`（2026-08-30 重跑
 * openapi），但这里仍参照 `useHSRPluginApi` 直接用 axios + `OpenAPI.BASE` 调用：
 * 下面的错误处理要从 `AxiosError.response.data.message` 里取后端给的文案，而生成的
 * 客户端抛的是 `ApiError`，直接换会把这条错误路径吃掉。切换要连错误处理一起改。
 */
export interface MaaFWUpdateResult {
  checked: boolean
  updated: boolean
  updateAvailable: boolean
  installable: boolean
  currentVersion: string | null
  latestVersion: string | null
  source: string | null
  message: string
}

interface MaaFWUpdateEnvelope {
  code: number
  status: string
  message: string
  data: Omit<MaaFWUpdateResult, 'message'> | null
}

const EMPTY_DATA: Omit<MaaFWUpdateResult, 'message'> = {
  checked: false,
  updated: false,
  updateAvailable: false,
  installable: false,
  currentVersion: null,
  latestVersion: null,
  source: null,
}

const endpoint = () => `${OpenAPI.BASE}/api/scripts/maafw/update`

export function useMaaFWUpdateApi() {
  const request = async (
    scriptId: string,
    action: 'check' | 'apply'
  ): Promise<MaaFWUpdateResult> => {
    let payload: MaaFWUpdateEnvelope
    try {
      const response = await axios.post<MaaFWUpdateEnvelope>(endpoint(), { scriptId, action })
      payload = response.data
    } catch (error) {
      if (axios.isAxiosError<MaaFWUpdateEnvelope>(error) && error.response?.data?.message) {
        throw new Error(error.response.data.message)
      }
      throw error instanceof Error ? error : new Error(String(error))
    }

    if (payload.code !== 200) {
      throw new Error(payload.message || 'MFW 项目更新请求失败')
    }
    return { ...EMPTY_DATA, ...(payload.data ?? {}), message: payload.message }
  }

  const checkMaaFWUpdate = (scriptId: string): Promise<MaaFWUpdateResult> =>
    request(scriptId, 'check')

  const applyMaaFWUpdate = (scriptId: string): Promise<MaaFWUpdateResult> =>
    request(scriptId, 'apply')

  return { checkMaaFWUpdate, applyMaaFWUpdate }
}
