import {
  Service,
  type MaaCopilotAnalyzeIn,
  type MaaCopilotAnalyzeOut,
  type MaaCopilotSourceIn,
} from '@/api'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'

/** 作业站请求统一经 MAS 后端，森空岛凭据不进入页面或公共数据缓存。 */
export function useMaaCopilotApi() {
  const checked = <T extends { code?: number; message?: string | null }>(response: T): T => {
    if (response.code !== 200) throw new Error(response.message || '作业数据请求失败')
    return response
  }
  const loadSource = async (request: MaaCopilotSourceIn) =>
    checked(await Service.loadMaaCopilotSourceApiScriptsMaaCopilotSourcePost(request))
  const searchAuthors = async (keyword: string) =>
    checked(await Service.searchMaaCopilotAuthorsApiScriptsMaaCopilotAuthorsPost({ keyword }))
  const analyze = async (request: MaaCopilotAnalyzeIn): Promise<MaaCopilotAnalyzeOut> =>
    checked(
      await observeFeature(
        'adapter_setup_finished',
        { script_type: 'MAA', operation_kind: 'preview', engine_kind: 'unknown' },
        () => Service.analyzeMaaCopilotTrainingApiScriptsMaaCopilotAnalyzePost(request),
        apiOutcome
      )
    )
  return { loadSource, searchAuthors, analyze }
}
