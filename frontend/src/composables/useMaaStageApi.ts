import { ApiError, MaaService } from '@/api'
import { translate as t } from '@/i18n'
import type { HomeOverviewResponse } from '@/types/home'

export async function getOptionalMaaStageOverview() {
  // 仅插件接口未挂载视为没有该模块，网络或业务失败继续交给调用方展示。
  try {
    const response =
      await MaaService.getMaaStageOverviewApiPluginMaaAdapterStagesOverviewPost(false)
    if (response.code !== 200)
      throw new Error(response.message || t('core.eventDepotPreview.loadFailed'))
    return response.data as HomeOverviewResponse['StageByServer']
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return {}
    throw error
  }
}
