import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { getAnalyticsScriptType } from '@/utils/analytics'
import { MaaFwService, type MaaFWEmbeddedSourceItem } from '@/api'

export function useMaaFWEmbeddedApi() {
  /** 有健康副本的 MFW / M9A 脚本：新建脚本时「复用已有脚本的项目」的候选；传了 scriptId 就排除它自己。 */
  const listEmbeddedSources = async (scriptId?: string): Promise<MaaFWEmbeddedSourceItem[]> => {
    const response = await MaaFwService.listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost(
      scriptId ? { scriptId } : {}
    )
    if (response.code !== 200) {
      throw new Error(response.message || '读取可复用的脚本失败')
    }
    return response.data ?? []
  }

  /** 从另一个脚本的副本克隆：同一项目再建一个脚本，不用重新选目录投影。 */
  const cloneEmbedded = async (scriptId: string, sourceScriptId: string) => {
    const response = await observeFeature(
      'adapter_setup_finished',
      {
        script_type: getAnalyticsScriptType(scriptId),
        operation_kind: 'import',
        engine_kind: 'embedded',
      },
      () =>
        MaaFwService.cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost({
          scriptId,
          sourceScriptId,
        }),
      apiOutcome
    )
    if (response.code !== 200) throw new Error(response.message || '复用项目失败')
    return { message: response.message ?? '' }
  }

  return { listEmbeddedSources, cloneEmbedded }
}
