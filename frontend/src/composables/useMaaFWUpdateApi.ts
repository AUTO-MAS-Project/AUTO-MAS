import { ApiError, MaaFwService, MaaFWProjectUpdateIn, type MaaFWProjectUpdateOut } from '@/api'

/** MaaFW 项目更新：复用生成客户端，统一页面结果与错误提示。 */
export interface MaaFWUpdateResult {
  checked: boolean
  updated: boolean
  updateAvailable: boolean
  installable: boolean
  currentVersion: string | null
  latestVersion: string | null
  /** 实际选用的下载来源：`mirrorchyan` / `github`。 */
  source: string | null
  message: string
  // 以下字段由后端 MaaFW 更新接口新增，旧后端不返回，读取时一律走可选链。
  /** Mirror 酱返回的版本名（可能与 latestVersion 不同）。 */
  versionName?: string | null
  /** `ok` / `absent` / `expired` / `invalid` / `quota` / `mismatched` / `blocked`。 */
  cdkStatus?: string | null
  /** 后端给的中文一句话说明。 */
  cdkMessage?: string | null
  /** CDK 到期时间，unix 秒。 */
  cdkExpiredTime?: number | null
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

export function useMaaFWUpdateApi() {
  const request = async (
    scriptId: string,
    action: 'check' | 'apply'
  ): Promise<MaaFWUpdateResult> => {
    let payload: MaaFWProjectUpdateOut
    try {
      payload = await MaaFwService.updateMaafwProjectApiScriptsMaafwUpdatePost({
        scriptId,
        action:
          action === 'check'
            ? MaaFWProjectUpdateIn.action.CHECK
            : MaaFWProjectUpdateIn.action.APPLY,
      })
    } catch (error) {
      if (error instanceof ApiError) {
        const body: unknown = error.body
        if (
          body &&
          typeof body === 'object' &&
          'message' in body &&
          typeof body.message === 'string' &&
          body.message
        ) {
          throw new Error(body.message)
        }
      }
      throw error instanceof Error ? error : new Error(String(error))
    }

    if (payload.code !== 200) {
      throw new Error(payload.message || 'MFW 项目更新请求失败')
    }
    return { ...EMPTY_DATA, ...(payload.data ?? {}), message: payload.message ?? '' }
  }

  const checkMaaFWUpdate = (scriptId: string): Promise<MaaFWUpdateResult> =>
    request(scriptId, 'check')

  const applyMaaFWUpdate = (scriptId: string): Promise<MaaFWUpdateResult> =>
    request(scriptId, 'apply')

  return { checkMaaFWUpdate, applyMaaFWUpdate }
}
