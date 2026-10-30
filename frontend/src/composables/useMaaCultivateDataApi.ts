import { Service } from '@/api'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'

/** 手动刷新只观察后端完整数据更新的结果，自动查询不重复上报。 */
export function useMaaCultivateDataApi() {
  const refresh = async (scriptId: string) => {
    const response = await observeFeature(
      'adapter_setup_finished',
      { script_type: 'MAA', operation_kind: 'data_refresh', engine_kind: 'unknown' },
      () => Service.refreshMaaCultivateDataApiScriptsMaaCultivateRefreshPost({ scriptId }),
      apiOutcome
    )
    if (response.code !== 200) throw new Error(response.message || 'Cultivation refresh failed')
  }
  return { refresh }
}
