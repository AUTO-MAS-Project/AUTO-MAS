import { computed, ref } from 'vue'
import { Service } from '@/api'
import { translate as t } from '@/i18n'
import type { HomeOverviewResponse } from '@/types/home'
import type { getDefaultMAAUserData } from './userDefaults'

const logger = window.electronAPI.getLogger('MAA 关卡选项')

/** 当前区服的关卡选项、活动目标与空档占位共用一次总览加载。 */
export function useMaaStageOptions(
  getFormData: () => Pick<ReturnType<typeof getDefaultMAAUserData>, 'Info' | 'Stage'>
) {
  const stageOptions = ref<any[]>([{ label: t('core.edit.none'), value: '' }])
  const activityStageLoading = ref(false)
  const activityStageError = ref('')
  const stageOverviewByServer = ref<HomeOverviewResponse['StageByServer']>({})
  const activityStages = computed(() => {
    const server = getFormData().Info.Server === 'Bilibili' ? 'Official' : getFormData().Info.Server
    return stageOverviewByServer.value[server]?.Activity ?? []
  })

  // 判断值是否为自定义关卡
  const isCustomStage = (value: string) => {
    if (!value || value === '' || value === '-') return false

    // 检查是否在从API加载的关卡列表中
    const predefinedStage = stageOptions.value.find(
      option => option.value === value && !option.isCustom
    )

    return !predefinedStage
  }
  const activityTemplate = computed(() => {
    const server = getFormData().Info.Server === 'Bilibili' ? 'Official' : getFormData().Info.Server
    return stageOverviewByServer.value[server]?.ActivityTemplate ?? []
  })

  const appendConfiguredCustomStages = () => {
    const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3'] as const
    stageFields.forEach(field => {
      const stageValue = getFormData().Stage[field]
      if (stageValue && isCustomStage(stageValue)) {
        const exists = stageOptions.value.find((option: any) => option.value === stageValue)
        if (!exists) {
          stageOptions.value.push({
            label: stageValue,
            value: stageValue,
            isCustom: true,
          })
        }
      }
    })
  }

  const applyServerStageOptions = () => {
    const server = getFormData().Info.Server === 'Bilibili' ? 'Official' : getFormData().Info.Server
    const stageOverview = stageOverviewByServer.value[server]
    if (!stageOverview) {
      stageOptions.value = []
      return
    }

    stageOptions.value = stageOverview.Options.map(option => ({
      ...option,
      isCustom: false,
    }))
    appendConfiguredCustomStages()
    activityStageError.value =
      stageOverview.ActivityStatus === 'stale'
        ? t('core.eventDepotPreview.staleData')
        : stageOverview.ActivityStatus === 'unavailable'
          ? t('core.eventDepotPreview.dataUnavailable')
          : ''
  }

  const loadActivityStageOptions = async (refresh = false) => {
    activityStageLoading.value = true
    activityStageError.value = ''
    try {
      const response = await Service.getOverviewApiInfoGetOverviewPost(refresh)
      if (response.code !== 200) {
        activityStageError.value = response.message || t('core.eventDepotPreview.loadFailed')
        return
      }

      const overview = response.data as Partial<HomeOverviewResponse> | undefined
      if (!overview?.StageByServer) {
        // 不能直接赋值: 字段缺席会把 stageOverviewByServer 的 {} 默认值抹成 undefined,
        // 之后服务器切换的 watcher 一跑 applyServerStageOptions 就会整页崩
        logger.error('活动关卡数据缺少 StageByServer 字段，后端版本可能与前端不匹配')
        activityStageError.value = t('core.eventDepotPreview.invalidData')
        return
      }

      for (const [server, stages] of Object.entries(overview.StageByServer)) {
        const previous = stageOverviewByServer.value[server]
        // 同区服暂不可用时保留上次成功的选项，避免目标显示被清空。
        stageOverviewByServer.value[server] =
          stages.ActivityStatus === 'unavailable' && previous
            ? { ...previous, ActivityStatus: 'unavailable' }
            : stages
      }
      applyServerStageOptions()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载活动关卡失败: ${errorMsg}`)
      activityStageError.value = t('core.eventDepotPreview.loadFailed')
    } finally {
      activityStageLoading.value = false
    }
  }

  return {
    stageOptions,
    activityStages,
    activityTemplate,
    activityStageLoading,
    activityStageError,
    appendConfiguredCustomStages,
    applyServerStageOptions,
    loadActivityStageOptions,
  }
}
