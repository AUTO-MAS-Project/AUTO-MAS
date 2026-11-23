import { ApiError, MaaService, type MaaStageOptionsIn } from '@/api'
import { requestApi } from '@/utils/apiResult'
import { translate as t } from '@/i18n'
import type { HomeOverviewResponse } from '@/types/home'

export async function getMaaStageOptions(type: MaaStageOptionsIn['type'], server = 'Official') {
  // 当前编辑器直接调用插件注册的接口，字段同时声明 endpoint，暂不改为动态 UI。
  return requestApi(
    () => MaaService.getMaaStageOptionsApiPluginMaaAdapterStagesOptionsPost({ type, server }),
    t('core.eventDepotPreview.loadFailed')
  )
}

export async function getMaaStageOverview(refresh = false) {
  // 关卡与活动始终读取插件缓存；插件停用时首页可继续展示宿主的其他模块。
  const response = await requestApi(
    () => MaaService.getMaaStageOverviewApiPluginMaaAdapterStagesOverviewPost(refresh),
    t('core.eventDepotPreview.loadFailed')
  )
  return response.data as HomeOverviewResponse['StageByServer']
}

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
