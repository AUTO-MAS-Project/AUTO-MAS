import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  type ScriptUpdateIn,
  type HSRStageOptionsData,
  type MaaEndOptionsOut,
  type MaaFWInterfacePreviewOut,
  type MaaFWAgentEnvPrepareOut,
  ScriptCreateIn,
  type ScriptReorderIn,
  type ZzzOdUserConfig,
  HsrService,
  MaaFwService,
  Service,
} from '@/api'
import type { ScriptDetail, ScriptType, User } from '@/types/script'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { getTaskRuntimeStates } from '@/composables/useTaskRuntimeState'
import { isScriptConfigLocked } from '@/utils/scriptConfigLock'

const logger = window.electronAPI.getLogger('脚本API')

type HSRStageEngine = 'M7A' | 'SRA'
type ScriptWithUsers = ScriptDetail & { users: User[] }
type LooseSection = Record<string, unknown>
type LooseUserConfig = Record<string, unknown> & {
  Info?: LooseSection | null
  Data?: LooseSection | null
  Task?: LooseSection | null
  Notify?: LooseSection | null
  Stage?: LooseSection | null
  TaskSwitch?: LooseSection | null
  TaskOpt?: LooseSection | null
}

const SCRIPT_CREATE_TYPE_BY_SCRIPT_TYPE: Record<ScriptType, ScriptCreateIn.type> = {
  MAA: ScriptCreateIn.type.MAA,
  SRC: ScriptCreateIn.type.SRC,
  MaaEnd: ScriptCreateIn.type.MAA_END,
  M9A: ScriptCreateIn.type.M9A,
  MaaFW: ScriptCreateIn.type.MAA_FW,
  Okww: ScriptCreateIn.type.OKWW,
  OkNte: ScriptCreateIn.type.OK_NTE,
  HSR: ScriptCreateIn.type.HSR,
  BetterGI: ScriptCreateIn.type.BETTER_GI,
  ZzzOd: ScriptCreateIn.type.ZZZ_OD,
  BAAH: ScriptCreateIn.type.BAAH,
  MSS: ScriptCreateIn.type.MSS,
  General: ScriptCreateIn.type.GENERAL,
}

const SCRIPT_TYPE_BY_CONFIG_TYPE: Record<string, ScriptType> = {
  MaaConfig: 'MAA',
  SrcConfig: 'SRC',
  OkwwConfig: 'Okww',
  OkNteConfig: 'OkNte',
  MaaEndConfig: 'MaaEnd',
  M9AConfig: 'M9A',
  MaaFWConfig: 'MaaFW',
  HSRConfig: 'HSR',
  BetterGIConfig: 'BetterGI',
  ZzzOdConfig: 'ZzzOd',
  BAAHConfig: 'BAAH',
  MSSConfig: 'MSS',
}

const resolveScriptType = (configType: string): ScriptType => {
  return SCRIPT_TYPE_BY_CONFIG_TYPE[configType] ?? 'General'
}

export function useScriptApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加脚本（支持从已有脚本复制创建）
  const addScript = async (type: ScriptType, scriptId?: string) => {
    loading.value = true
    error.value = null

    try {
      const requestData: ScriptCreateIn = {
        type: SCRIPT_CREATE_TYPE_BY_SCRIPT_TYPE[type],
        scriptId: scriptId || null,
      }

      const response = await Service.addScriptApiScriptsAddPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '添加脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 播放添加脚本成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_script_instance')

      return {
        scriptId: response.scriptId,
        message: response.message || '脚本添加成功',
        data: response.data,
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '添加脚本失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // 获取脚本列表（可选择是否管理 loading 状态，避免嵌套调用时提前结束 loading）
  const getScripts = async (manageLoading: boolean = true): Promise<ScriptDetail[]> => {
    if (manageLoading) {
      loading.value = true
      error.value = null
    } else {
      // 仅清理错误，不改变外部 loading
      error.value = null
    }

    try {
      const response = await Service.getScriptApiScriptsGetPost({})

      if (response.code !== 200) {
        const errorMsg = response.message || '获取脚本列表失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 将API响应转换为ScriptDetail数组
      return response.index.map(indexItem => ({
        uid: indexItem.uid,
        type: resolveScriptType(indexItem.type),
        name: response.data[indexItem.uid]?.Info?.Name || `${indexItem.type}脚本`,
        config: response.data[indexItem.uid],
      }))
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取脚本列表失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return []
    } finally {
      if (manageLoading) {
        loading.value = false
      }
    }
  }

  // 获取脚本列表及其用户数据（统一管理一次 loading）
  const getScriptsWithUsers = async (): Promise<ScriptWithUsers[]> => {
    loading.value = true
    error.value = null

    try {
      // 首先获取脚本列表，但不在内部结束 loading
      const scriptDetails = await getScripts(false)

      // 为每个脚本获取用户数据
      const scriptsWithUsers = await Promise.all(
        scriptDetails.map(async script => {
          try {
            // 获取该脚本下的用户列表
            const userResponse = await Service.getUserApiScriptsUserGetPost({
              scriptId: script.uid,
            })

            if (userResponse.code === 200) {
              // 将用户数据转换为User格式
              const users = userResponse.index
                .map(userIndex => {
                  const userData = userResponse.data[userIndex.uid]

                  if (userIndex.type === 'MaaUserConfig' && userData) {
                    const maaUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: maaUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          maaUserData.Info?.Name !== undefined
                            ? maaUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Id: maaUserData.Info?.Id !== undefined ? maaUserData.Info.Id : '',
                        Mode: maaUserData.Info?.Mode !== undefined ? maaUserData.Info.Mode : '脚本',
                        StageMode:
                          maaUserData.Info?.StageMode !== undefined
                            ? maaUserData.Info.StageMode
                            : 'Fixed',
                        Server:
                          maaUserData.Info?.Server !== undefined
                            ? maaUserData.Info.Server
                            : 'Official',
                        Status:
                          maaUserData.Info?.Status !== undefined ? maaUserData.Info.Status : true,
                        RemainedDay:
                          maaUserData.Info?.RemainedDay !== undefined
                            ? maaUserData.Info.RemainedDay
                            : -1,
                        Annihilation:
                          maaUserData.Info?.Annihilation !== undefined
                            ? maaUserData.Info.Annihilation
                            : 'Annihilation',
                        InfrastMode:
                          maaUserData.Info?.InfrastMode !== undefined
                            ? maaUserData.Info.InfrastMode
                            : 'Normal',
                        InfrastName:
                          maaUserData.Info?.InfrastName !== undefined
                            ? maaUserData.Info.InfrastName
                            : '',
                        Password:
                          maaUserData.Info?.Password !== undefined ? maaUserData.Info.Password : '',
                        Notes: maaUserData.Info?.Notes !== undefined ? maaUserData.Info.Notes : '',
                        MedicineNumb:
                          maaUserData.Info?.MedicineNumb !== undefined
                            ? maaUserData.Info.MedicineNumb
                            : 0,
                        SeriesNumb:
                          maaUserData.Info?.SeriesNumb !== undefined
                            ? maaUserData.Info.SeriesNumb
                            : '0',
                        Stage: maaUserData.Info?.Stage !== undefined ? maaUserData.Info.Stage : '-',
                        Stage_1:
                          maaUserData.Info?.Stage_1 !== undefined ? maaUserData.Info.Stage_1 : '-',
                        Stage_2:
                          maaUserData.Info?.Stage_2 !== undefined ? maaUserData.Info.Stage_2 : '-',
                        Stage_3:
                          maaUserData.Info?.Stage_3 !== undefined ? maaUserData.Info.Stage_3 : '-',
                        Tag: maaUserData.Info?.Tag !== undefined ? maaUserData.Info.Tag : null,
                      },
                      Task: {
                        IfStartUp:
                          maaUserData.Task?.IfStartUp !== undefined
                            ? maaUserData.Task.IfStartUp
                            : true,
                        IfRecruit:
                          maaUserData.Task?.IfRecruit !== undefined
                            ? maaUserData.Task.IfRecruit
                            : true,
                        IfInfrast:
                          maaUserData.Task?.IfInfrast !== undefined
                            ? maaUserData.Task.IfInfrast
                            : true,
                        IfFight:
                          maaUserData.Task?.IfFight !== undefined ? maaUserData.Task.IfFight : true,
                        IfMall:
                          maaUserData.Task?.IfMall !== undefined ? maaUserData.Task.IfMall : true,
                        IfAward:
                          maaUserData.Task?.IfAward !== undefined ? maaUserData.Task.IfAward : true,
                        IfSwitchTheme:
                          maaUserData.Task?.IfSwitchTheme !== undefined
                            ? maaUserData.Task.IfSwitchTheme
                            : false,
                        IfReclamation:
                          maaUserData.Task?.IfReclamation !== undefined
                            ? maaUserData.Task.IfReclamation
                            : false,
                        IfDepotMaintain:
                          maaUserData.Task?.IfDepotMaintain !== undefined
                            ? maaUserData.Task.IfDepotMaintain
                            : false,
                        IfActivityFirst:
                          maaUserData.Task?.IfActivityFirst !== undefined
                            ? maaUserData.Task.IfActivityFirst
                            : false,
                        ActivityStageIndex:
                          maaUserData.Task?.ActivityStageIndex !== undefined
                            ? maaUserData.Task.ActivityStageIndex
                            : 1,
                        ActivityMedicineNumb:
                          maaUserData.Task?.ActivityMedicineNumb !== undefined
                            ? maaUserData.Task.ActivityMedicineNumb
                            : (maaUserData.Info?.MedicineNumb ?? 0),
                      },
                      Notify: {
                        Enabled:
                          maaUserData.Notify?.Enabled !== undefined
                            ? maaUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          maaUserData.Notify?.IfSendStatistic !== undefined
                            ? maaUserData.Notify.IfSendStatistic
                            : false,
                        IfSendSixStar:
                          maaUserData.Notify?.IfSendSixStar !== undefined
                            ? maaUserData.Notify.IfSendSixStar
                            : false,
                        IfSendMail:
                          maaUserData.Notify?.IfSendMail !== undefined
                            ? maaUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          maaUserData.Notify?.ToAddress !== undefined
                            ? maaUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          maaUserData.Notify?.IfServerChan !== undefined
                            ? maaUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          maaUserData.Notify?.ServerChanKey !== undefined
                            ? maaUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          maaUserData.Data?.LastProxyDate !== undefined
                            ? maaUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          maaUserData.Data?.ProxyTimes !== undefined
                            ? maaUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'SrcUserConfig' && userData) {
                    const srcUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: srcUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          srcUserData.Info?.Name !== undefined
                            ? srcUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Id: srcUserData.Info?.Id !== undefined ? srcUserData.Info.Id : '',
                        Password:
                          srcUserData.Info?.Password !== undefined ? srcUserData.Info.Password : '',
                        Mode: srcUserData.Info?.Mode !== undefined ? srcUserData.Info.Mode : '脚本',
                        Server:
                          srcUserData.Info?.Server !== undefined
                            ? srcUserData.Info.Server
                            : 'CN-Official',
                        Status:
                          srcUserData.Info?.Status !== undefined ? srcUserData.Info.Status : true,
                        RemainedDay:
                          srcUserData.Info?.RemainedDay !== undefined
                            ? srcUserData.Info.RemainedDay
                            : -1,
                        Notes: srcUserData.Info?.Notes !== undefined ? srcUserData.Info.Notes : '',
                        Tag: srcUserData.Info?.Tag !== undefined ? srcUserData.Info.Tag : null,
                      },
                      Stage: {
                        Channel:
                          srcUserData.Stage?.Channel !== undefined
                            ? srcUserData.Stage.Channel
                            : 'Relic',
                        Relic:
                          srcUserData.Stage?.Relic !== undefined ? srcUserData.Stage.Relic : '-',
                        Materials:
                          srcUserData.Stage?.Materials !== undefined
                            ? srcUserData.Stage.Materials
                            : '-',
                        Ornament:
                          srcUserData.Stage?.Ornament !== undefined
                            ? srcUserData.Stage.Ornament
                            : '-',
                        ExtractReservedTrailblazePower:
                          srcUserData.Stage?.ExtractReservedTrailblazePower !== undefined
                            ? srcUserData.Stage.ExtractReservedTrailblazePower
                            : false,
                        UseFuel:
                          srcUserData.Stage?.UseFuel !== undefined
                            ? srcUserData.Stage.UseFuel
                            : false,
                        FuelReserve:
                          srcUserData.Stage?.FuelReserve !== undefined
                            ? srcUserData.Stage.FuelReserve
                            : 5,
                        EchoOfWar:
                          srcUserData.Stage?.EchoOfWar !== undefined
                            ? srcUserData.Stage.EchoOfWar
                            : '-',
                        SimulatedUniverseWorld:
                          srcUserData.Stage?.SimulatedUniverseWorld !== undefined
                            ? srcUserData.Stage.SimulatedUniverseWorld
                            : '-',
                      },
                      Notify: {
                        Enabled:
                          srcUserData.Notify?.Enabled !== undefined
                            ? srcUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          srcUserData.Notify?.IfSendStatistic !== undefined
                            ? srcUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          srcUserData.Notify?.IfSendMail !== undefined
                            ? srcUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          srcUserData.Notify?.ToAddress !== undefined
                            ? srcUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          srcUserData.Notify?.IfServerChan !== undefined
                            ? srcUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          srcUserData.Notify?.ServerChanKey !== undefined
                            ? srcUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          srcUserData.Data?.LastProxyDate !== undefined
                            ? srcUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          srcUserData.Data?.ProxyTimes !== undefined
                            ? srcUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'GeneralUserConfig' && userData) {
                    const generalUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: generalUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          generalUserData.Info?.Name !== undefined
                            ? generalUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          generalUserData.Info?.Status !== undefined
                            ? generalUserData.Info.Status
                            : true,
                        RemainedDay:
                          generalUserData.Info?.RemainedDay !== undefined
                            ? generalUserData.Info.RemainedDay
                            : -1,
                        IfUseMasConfig:
                          generalUserData.Info?.IfUseMasConfig !== undefined
                            ? generalUserData.Info.IfUseMasConfig
                            : true,
                        IfScriptBeforeTask:
                          generalUserData.Info?.IfScriptBeforeTask !== undefined
                            ? generalUserData.Info.IfScriptBeforeTask
                            : false,
                        ScriptBeforeTask:
                          generalUserData.Info?.ScriptBeforeTask !== undefined
                            ? generalUserData.Info.ScriptBeforeTask
                            : '',
                        IfScriptAfterTask:
                          generalUserData.Info?.IfScriptAfterTask !== undefined
                            ? generalUserData.Info.IfScriptAfterTask
                            : false,
                        ScriptAfterTask:
                          generalUserData.Info?.ScriptAfterTask !== undefined
                            ? generalUserData.Info.ScriptAfterTask
                            : '',
                        Notes:
                          generalUserData.Info?.Notes !== undefined
                            ? generalUserData.Info.Notes
                            : '',
                        Tag:
                          generalUserData.Info?.Tag !== undefined ? generalUserData.Info.Tag : null,
                      },
                      Notify: {
                        Enabled:
                          generalUserData.Notify?.Enabled !== undefined
                            ? generalUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          generalUserData.Notify?.IfSendStatistic !== undefined
                            ? generalUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          generalUserData.Notify?.IfSendMail !== undefined
                            ? generalUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          generalUserData.Notify?.ToAddress !== undefined
                            ? generalUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          generalUserData.Notify?.IfServerChan !== undefined
                            ? generalUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          generalUserData.Notify?.ServerChanKey !== undefined
                            ? generalUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          generalUserData.Data?.LastProxyDate !== undefined
                            ? generalUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          generalUserData.Data?.ProxyTimes !== undefined
                            ? generalUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'MaaEndUserConfig' && userData) {
                    const maaEndUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: maaEndUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          maaEndUserData.Info?.Name !== undefined
                            ? maaEndUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Id: maaEndUserData.Info?.Id !== undefined ? maaEndUserData.Info.Id : '',
                        Password:
                          maaEndUserData.Info?.Password !== undefined
                            ? maaEndUserData.Info.Password
                            : '',
                        Mode:
                          maaEndUserData.Info?.Mode !== undefined
                            ? maaEndUserData.Info.Mode
                            : '脚本',
                        SanityMode:
                          maaEndUserData.Info?.SanityMode !== undefined
                            ? maaEndUserData.Info.SanityMode
                            : 'Fixed',
                        Resource:
                          maaEndUserData.Info?.Resource !== undefined
                            ? maaEndUserData.Info.Resource
                            : '',
                        Status:
                          maaEndUserData.Info?.Status !== undefined
                            ? maaEndUserData.Info.Status
                            : true,
                        RemainedDay:
                          maaEndUserData.Info?.RemainedDay !== undefined
                            ? maaEndUserData.Info.RemainedDay
                            : -1,
                        Notes:
                          maaEndUserData.Info?.Notes !== undefined ? maaEndUserData.Info.Notes : '',
                        Tag:
                          maaEndUserData.Info?.Tag !== undefined ? maaEndUserData.Info.Tag : null,
                      },
                      Task: {
                        SanityTaskType:
                          maaEndUserData.Task?.SanityTaskType != null
                            ? maaEndUserData.Task.SanityTaskType
                            : 'OperatorProgression',
                        OperatorProgression:
                          maaEndUserData.Task?.OperatorProgression != null
                            ? maaEndUserData.Task.OperatorProgression
                            : 'OperatorEXP',
                        WeaponProgression:
                          maaEndUserData.Task?.WeaponProgression != null
                            ? maaEndUserData.Task.WeaponProgression
                            : 'WeaponEXP',
                        CrisisDrills:
                          maaEndUserData.Task?.CrisisDrills != null
                            ? maaEndUserData.Task.CrisisDrills
                            : 'AdvancedProgression1',
                        RewardsSetOption:
                          maaEndUserData.Task?.RewardsSetOption != null
                            ? maaEndUserData.Task.RewardsSetOption
                            : 'RewardsSetA',
                        AutoEssenceSpecifiedLocation:
                          maaEndUserData.Task?.AutoEssenceSpecifiedLocation != null
                            ? maaEndUserData.Task.AutoEssenceSpecifiedLocation
                            : '',
                        AutoEssenceMenu:
                          maaEndUserData.Task?.AutoEssenceMenu === 'Random' ||
                          maaEndUserData.Task?.AutoEssenceMenu === 'Target'
                            ? maaEndUserData.Task.AutoEssenceMenu
                            : 'Location',
                        AutoEssenceTargetWeapons: Array.isArray(
                          maaEndUserData.Task?.AutoEssenceTargetWeapons
                        )
                          ? Array.from(
                              new Set(
                                maaEndUserData.Task.AutoEssenceTargetWeapons.filter(
                                  (item): item is string =>
                                    typeof item === 'string' && item.length > 0
                                )
                              )
                            )
                          : [],
                        IfSanity:
                          maaEndUserData.Task?.IfSanity != null
                            ? maaEndUserData.Task.IfSanity
                            : true,
                        IfAutoUseSpMedication:
                          maaEndUserData.Task?.IfAutoUseSpMedication != null
                            ? maaEndUserData.Task.IfAutoUseSpMedication
                            : true,
                        IfDijiangRewards:
                          maaEndUserData.Task?.IfDijiangRewards != null
                            ? maaEndUserData.Task.IfDijiangRewards
                            : true,
                        IfDeliveryJobs:
                          maaEndUserData.Task?.IfDeliveryJobs != null
                            ? maaEndUserData.Task.IfDeliveryJobs
                            : true,
                        IfSellProduct:
                          maaEndUserData.Task?.IfSellProduct != null
                            ? maaEndUserData.Task.IfSellProduct
                            : true,
                        IfAutoStockpile:
                          maaEndUserData.Task?.IfAutoStockpile != null
                            ? maaEndUserData.Task.IfAutoStockpile
                            : true,
                        IfAutoStockStaple:
                          maaEndUserData.Task?.IfAutoStockStaple != null
                            ? maaEndUserData.Task.IfAutoStockStaple
                            : true,
                        IfVisitFriends:
                          maaEndUserData.Task?.IfVisitFriends != null
                            ? maaEndUserData.Task.IfVisitFriends
                            : true,
                        IfCreditShoppingN2:
                          maaEndUserData.Task?.IfCreditShoppingN2 != null
                            ? maaEndUserData.Task.IfCreditShoppingN2
                            : true,
                        IfSeizeDeliveryJobs:
                          maaEndUserData.Task?.IfSeizeDeliveryJobs != null
                            ? maaEndUserData.Task.IfSeizeDeliveryJobs
                            : true,
                        SeizeDeliveryJobsReward:
                          maaEndUserData.Task?.SeizeDeliveryJobsReward != null
                            ? maaEndUserData.Task.SeizeDeliveryJobsReward
                            : 15.9,
                        SeizeDeliveryJobsCommissionSource:
                          maaEndUserData.Task?.SeizeDeliveryJobsCommissionSource != null
                            ? maaEndUserData.Task.SeizeDeliveryJobsCommissionSource
                            : 'Unlimited',
                        IfAutoEcoFarm:
                          maaEndUserData.Task?.IfAutoEcoFarm != null
                            ? maaEndUserData.Task.IfAutoEcoFarm
                            : true,
                        IfAutoSell:
                          maaEndUserData.Task?.IfAutoSell != null
                            ? maaEndUserData.Task.IfAutoSell
                            : true,
                        IfEnvironmentMonitoring:
                          maaEndUserData.Task?.IfEnvironmentMonitoring != null
                            ? maaEndUserData.Task.IfEnvironmentMonitoring
                            : true,
                        IfAutoCollect:
                          maaEndUserData.Task?.IfAutoCollect != null
                            ? maaEndUserData.Task.IfAutoCollect
                            : true,
                        AutoCollectMode:
                          maaEndUserData.Task?.AutoCollectMode === 'Concentrated'
                            ? 'Concentrated'
                            : 'Distributed',
                        AutoCollectRoutes: maaEndUserData.Task?.AutoCollectRoutes ?? null,
                        AutoCollectCommonRoutes:
                          maaEndUserData.Task?.AutoCollectCommonRoutes ?? null,
                        IfTrialOfSwordmancy:
                          maaEndUserData.Task?.IfTrialOfSwordmancy != null
                            ? maaEndUserData.Task.IfTrialOfSwordmancy
                            : true,
                        IfDailyRewards:
                          maaEndUserData.Task?.IfDailyRewards != null
                            ? maaEndUserData.Task.IfDailyRewards
                            : true,
                        IfResourceRecycleStation:
                          maaEndUserData.Task?.IfResourceRecycleStation != null
                            ? maaEndUserData.Task.IfResourceRecycleStation
                            : true,
                        IfPullCountCalculator:
                          maaEndUserData.Task?.IfPullCountCalculator != null
                            ? maaEndUserData.Task.IfPullCountCalculator
                            : false,
                      },
                      Notify: {
                        Enabled:
                          maaEndUserData.Notify?.Enabled !== undefined
                            ? maaEndUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          maaEndUserData.Notify?.IfSendStatistic !== undefined
                            ? maaEndUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          maaEndUserData.Notify?.IfSendMail !== undefined
                            ? maaEndUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          maaEndUserData.Notify?.ToAddress !== undefined
                            ? maaEndUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          maaEndUserData.Notify?.IfServerChan !== undefined
                            ? maaEndUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          maaEndUserData.Notify?.ServerChanKey !== undefined
                            ? maaEndUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          maaEndUserData.Data?.LastProxyDate !== undefined
                            ? maaEndUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          maaEndUserData.Data?.ProxyTimes !== undefined
                            ? maaEndUserData.Data.ProxyTimes
                            : 0,
                        LastProxyStatus:
                          maaEndUserData.Data?.LastProxyStatus !== undefined
                            ? maaEndUserData.Data.LastProxyStatus
                            : '未知',
                      },
                    }
                  } else if (userIndex.type === 'M9AUserConfig' && userData) {
                    const m9aUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: m9aUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          m9aUserData.Info?.Name !== undefined
                            ? m9aUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          m9aUserData.Info?.Status !== undefined ? m9aUserData.Info.Status : true,
                        RemainedDay:
                          m9aUserData.Info?.RemainedDay !== undefined
                            ? m9aUserData.Info.RemainedDay
                            : -1,
                        Notes: m9aUserData.Info?.Notes !== undefined ? m9aUserData.Info.Notes : '',
                        Tag: m9aUserData.Info?.Tag !== undefined ? m9aUserData.Info.Tag : null,
                        Resource:
                          m9aUserData.Info?.Resource !== undefined
                            ? m9aUserData.Info.Resource
                            : '官服',
                        Account:
                          m9aUserData.Info?.Account !== undefined ? m9aUserData.Info.Account : '',
                        EmulatorId:
                          m9aUserData.Info?.EmulatorId !== undefined
                            ? m9aUserData.Info.EmulatorId
                            : '',
                        EmulatorIndex:
                          m9aUserData.Info?.EmulatorIndex !== undefined
                            ? m9aUserData.Info.EmulatorIndex
                            : 0,
                      },
                      Task: {
                        AvailableTasks:
                          m9aUserData.Task?.AvailableTasks !== undefined
                            ? m9aUserData.Task.AvailableTasks
                            : '[]',
                        Queue:
                          m9aUserData.Task?.Queue !== undefined ? m9aUserData.Task.Queue : '[]',
                      },
                      Notify: {
                        Enabled:
                          m9aUserData.Notify?.Enabled !== undefined
                            ? m9aUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          m9aUserData.Notify?.IfSendStatistic !== undefined
                            ? m9aUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          m9aUserData.Notify?.IfSendMail !== undefined
                            ? m9aUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          m9aUserData.Notify?.ToAddress !== undefined
                            ? m9aUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          m9aUserData.Notify?.IfServerChan !== undefined
                            ? m9aUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          m9aUserData.Notify?.ServerChanKey !== undefined
                            ? m9aUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          m9aUserData.Data?.LastProxyDate !== undefined
                            ? m9aUserData.Data.LastProxyDate
                            : '2000-01-01',
                        LastPsychubeDate:
                          m9aUserData.Data?.LastPsychubeDate !== undefined
                            ? m9aUserData.Data.LastPsychubeDate
                            : '',
                        LastLimboMonth:
                          m9aUserData.Data?.LastLimboMonth !== undefined
                            ? m9aUserData.Data.LastLimboMonth
                            : '',
                        LastLucidscapeMonth:
                          m9aUserData.Data?.LastLucidscapeMonth !== undefined
                            ? m9aUserData.Data.LastLucidscapeMonth
                            : '',
                        ProxyTimes:
                          m9aUserData.Data?.ProxyTimes !== undefined
                            ? m9aUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (
                    (userIndex.type === 'OkwwUserConfig' || userIndex.type === 'OkNteUserConfig') &&
                    userData
                  ) {
                    const okwwUserData = userData as unknown as LooseUserConfig
                    const isOkwwUser = userIndex.type === 'OkwwUserConfig'
                    return {
                      id: userIndex.uid,
                      name: okwwUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          okwwUserData.Info?.Name !== undefined
                            ? okwwUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          okwwUserData.Info?.Status !== undefined ? okwwUserData.Info.Status : true,
                        Id: okwwUserData.Info?.Id !== undefined ? okwwUserData.Info.Id : '',
                        Password:
                          okwwUserData.Info?.Password !== undefined
                            ? okwwUserData.Info.Password
                            : '',
                        Mode:
                          okwwUserData.Info?.Mode !== undefined ? okwwUserData.Info.Mode : '脚本',
                        IfQuickConfig: isOkwwUser
                          ? okwwUserData.Info?.IfQuickConfig !== undefined
                            ? okwwUserData.Info.IfQuickConfig
                            : true
                          : undefined,
                        Resource:
                          okwwUserData.Info?.Resource !== undefined
                            ? okwwUserData.Info.Resource
                            : '官服',
                        RemainedDay:
                          okwwUserData.Info?.RemainedDay !== undefined
                            ? okwwUserData.Info.RemainedDay
                            : -1,
                        IfScriptBeforeTask:
                          okwwUserData.Info?.IfScriptBeforeTask !== undefined
                            ? okwwUserData.Info.IfScriptBeforeTask
                            : false,
                        ScriptBeforeTask:
                          okwwUserData.Info?.ScriptBeforeTask !== undefined
                            ? okwwUserData.Info.ScriptBeforeTask
                            : '',
                        IfScriptAfterTask:
                          okwwUserData.Info?.IfScriptAfterTask !== undefined
                            ? okwwUserData.Info.IfScriptAfterTask
                            : false,
                        ScriptAfterTask:
                          okwwUserData.Info?.ScriptAfterTask !== undefined
                            ? okwwUserData.Info.ScriptAfterTask
                            : '',
                        Notes:
                          okwwUserData.Info?.Notes !== undefined ? okwwUserData.Info.Notes : '',
                        Tag: okwwUserData.Info?.Tag !== undefined ? okwwUserData.Info.Tag : null,
                      },
                      Task: {
                        TaskIndex:
                          okwwUserData.Task?.TaskIndex !== undefined
                            ? okwwUserData.Task.TaskIndex
                            : userIndex.type === 'OkNteUserConfig'
                              ? 2
                              : 1,
                        ExitOnFinish:
                          okwwUserData.Task?.ExitOnFinish !== undefined
                            ? okwwUserData.Task.ExitOnFinish
                            : true,
                      },
                      Notify: {
                        Enabled:
                          okwwUserData.Notify?.Enabled !== undefined
                            ? okwwUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          okwwUserData.Notify?.IfSendStatistic !== undefined
                            ? okwwUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          okwwUserData.Notify?.IfSendMail !== undefined
                            ? okwwUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          okwwUserData.Notify?.ToAddress !== undefined
                            ? okwwUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          okwwUserData.Notify?.IfServerChan !== undefined
                            ? okwwUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          okwwUserData.Notify?.ServerChanKey !== undefined
                            ? okwwUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          okwwUserData.Data?.LastProxyDate !== undefined
                            ? okwwUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          okwwUserData.Data?.ProxyTimes !== undefined
                            ? okwwUserData.Data.ProxyTimes
                            : 0,
                        LastProxyStatus:
                          okwwUserData.Data?.LastProxyStatus !== undefined
                            ? okwwUserData.Data.LastProxyStatus
                            : '未知',
                      },
                    }
                  } else if (userIndex.type === 'MaaFWUserConfig' && userData) {
                    const maafwUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: maafwUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name: maafwUserData.Info?.Name || `用户${userIndex.uid}`,
                        Status: maafwUserData.Info?.Status ?? true,
                        RemainedDay: maafwUserData.Info?.RemainedDay ?? -1,
                        Notes: maafwUserData.Info?.Notes ?? '',
                        Tag: maafwUserData.Info?.Tag ?? null,
                      },
                      Task: maafwUserData.Task ?? {},
                      Notify: maafwUserData.Notify ?? {},
                      Data: {
                        LastProxyDate: maafwUserData.Data?.LastProxyDate ?? '2000-01-01',
                        ProxyTimes: maafwUserData.Data?.ProxyTimes ?? 0,
                        IfPassCheck: maafwUserData.Data?.IfPassCheck ?? true,
                      },
                    } as unknown as User
                  } else if (userIndex.type === 'HSRUserConfig' && userData) {
                    const hsrUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: hsrUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          hsrUserData.Info?.Name !== undefined
                            ? hsrUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          hsrUserData.Info?.Status !== undefined ? hsrUserData.Info.Status : true,
                        Id: hsrUserData.Info?.Id !== undefined ? hsrUserData.Info.Id : '',
                        Password:
                          hsrUserData.Info?.Password !== undefined ? hsrUserData.Info.Password : '',
                        Server:
                          hsrUserData.Info?.Server !== undefined
                            ? hsrUserData.Info.Server
                            : 'CN-Official',
                        RemainedDay:
                          hsrUserData.Info?.RemainedDay !== undefined
                            ? hsrUserData.Info.RemainedDay
                            : -1,
                        Notes: hsrUserData.Info?.Notes !== undefined ? hsrUserData.Info.Notes : '',
                        Tag: hsrUserData.Info?.Tag !== undefined ? hsrUserData.Info.Tag : null,
                      },
                      Stage: {
                        Channel:
                          hsrUserData.Stage?.Channel !== undefined
                            ? hsrUserData.Stage.Channel
                            : 'CalyxGolden',
                        ScriptStage:
                          hsrUserData.Stage?.ScriptStage !== undefined
                            ? hsrUserData.Stage.ScriptStage
                            : '{ }',
                        ScriptEchoOfWar:
                          hsrUserData.Stage?.ScriptEchoOfWar !== undefined
                            ? hsrUserData.Stage.ScriptEchoOfWar
                            : '{ }',
                      },
                      TaskSwitch: {
                        Daily:
                          hsrUserData.TaskSwitch?.Daily !== undefined
                            ? hsrUserData.TaskSwitch.Daily
                            : true,
                        ReceiveRewards:
                          hsrUserData.TaskSwitch?.ReceiveRewards !== undefined
                            ? hsrUserData.TaskSwitch.ReceiveRewards
                            : true,
                        DivergentUniverse:
                          hsrUserData.TaskSwitch?.DivergentUniverse !== undefined
                            ? hsrUserData.TaskSwitch.DivergentUniverse
                            : true,
                        CurrencyWars:
                          hsrUserData.TaskSwitch?.CurrencyWars !== undefined
                            ? hsrUserData.TaskSwitch.CurrencyWars
                            : false,
                      },
                      TaskOpt: {
                        EchoOfWarWeekday:
                          hsrUserData.TaskOpt?.EchoOfWarWeekday !== undefined
                            ? hsrUserData.TaskOpt.EchoOfWarWeekday
                            : 'Monday',
                      },
                      Notify: {
                        Enabled:
                          hsrUserData.Notify?.Enabled !== undefined
                            ? hsrUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          hsrUserData.Notify?.IfSendStatistic !== undefined
                            ? hsrUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          hsrUserData.Notify?.IfSendMail !== undefined
                            ? hsrUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          hsrUserData.Notify?.ToAddress !== undefined
                            ? hsrUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          hsrUserData.Notify?.IfServerChan !== undefined
                            ? hsrUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          hsrUserData.Notify?.ServerChanKey !== undefined
                            ? hsrUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          hsrUserData.Data?.LastProxyDate !== undefined
                            ? hsrUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          hsrUserData.Data?.ProxyTimes !== undefined
                            ? hsrUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'BetterGIUserConfig' && userData) {
                    const bettergiUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: bettergiUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          bettergiUserData.Info?.Name !== undefined
                            ? bettergiUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          bettergiUserData.Info?.Status !== undefined
                            ? bettergiUserData.Info.Status
                            : true,
                        Id: bettergiUserData.Info?.Id !== undefined ? bettergiUserData.Info.Id : '',
                        Password:
                          bettergiUserData.Info?.Password !== undefined
                            ? bettergiUserData.Info.Password
                            : '',
                        RemainedDay:
                          bettergiUserData.Info?.RemainedDay !== undefined
                            ? bettergiUserData.Info.RemainedDay
                            : -1,
                        IfScriptBeforeTask:
                          bettergiUserData.Info?.IfScriptBeforeTask !== undefined
                            ? bettergiUserData.Info.IfScriptBeforeTask
                            : false,
                        ScriptBeforeTask:
                          bettergiUserData.Info?.ScriptBeforeTask !== undefined
                            ? bettergiUserData.Info.ScriptBeforeTask
                            : '',
                        IfScriptAfterTask:
                          bettergiUserData.Info?.IfScriptAfterTask !== undefined
                            ? bettergiUserData.Info.IfScriptAfterTask
                            : false,
                        ScriptAfterTask:
                          bettergiUserData.Info?.ScriptAfterTask !== undefined
                            ? bettergiUserData.Info.ScriptAfterTask
                            : '',
                        Notes:
                          bettergiUserData.Info?.Notes !== undefined
                            ? bettergiUserData.Info.Notes
                            : '',
                        Tag:
                          bettergiUserData.Info?.Tag !== undefined
                            ? bettergiUserData.Info.Tag
                            : null,
                      },
                      Task: {
                        OneDragonConfigName:
                          bettergiUserData.Task?.OneDragonConfigName !== undefined
                            ? bettergiUserData.Task.OneDragonConfigName
                            : '',
                      },
                      Notify: {
                        Enabled:
                          bettergiUserData.Notify?.Enabled !== undefined
                            ? bettergiUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          bettergiUserData.Notify?.IfSendStatistic !== undefined
                            ? bettergiUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          bettergiUserData.Notify?.IfSendMail !== undefined
                            ? bettergiUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          bettergiUserData.Notify?.ToAddress !== undefined
                            ? bettergiUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          bettergiUserData.Notify?.IfServerChan !== undefined
                            ? bettergiUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          bettergiUserData.Notify?.ServerChanKey !== undefined
                            ? bettergiUserData.Notify.ServerChanKey
                            : '',
                        CustomWebhooks:
                          bettergiUserData.Notify?.CustomWebhooks !== undefined
                            ? bettergiUserData.Notify.CustomWebhooks
                            : [],
                      },
                      Data: {
                        LastProxyDate:
                          bettergiUserData.Data?.LastProxyDate !== undefined
                            ? bettergiUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          bettergiUserData.Data?.ProxyTimes !== undefined
                            ? bettergiUserData.Data.ProxyTimes
                            : 0,
                        LastProxyStatus:
                          bettergiUserData.Data?.LastProxyStatus !== undefined
                            ? bettergiUserData.Data.LastProxyStatus
                            : '未知',
                      },
                    }
                  } else if (userIndex.type === 'ZzzOdUserConfig' && userData) {
                    const zzzodUserData = userData as unknown as ZzzOdUserConfig
                    return {
                      id: userIndex.uid,
                      name: zzzodUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          zzzodUserData.Info?.Name !== undefined
                            ? zzzodUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          zzzodUserData.Info?.Status !== undefined
                            ? zzzodUserData.Info.Status
                            : true,
                        Mode:
                          zzzodUserData.Info?.Mode !== undefined ? zzzodUserData.Info.Mode : '用户',
                        RemainedDay:
                          zzzodUserData.Info?.RemainedDay !== undefined
                            ? zzzodUserData.Info.RemainedDay
                            : -1,
                        IfScriptBeforeTask:
                          zzzodUserData.Info?.IfScriptBeforeTask !== undefined
                            ? zzzodUserData.Info.IfScriptBeforeTask
                            : false,
                        ScriptBeforeTask:
                          zzzodUserData.Info?.ScriptBeforeTask !== undefined
                            ? zzzodUserData.Info.ScriptBeforeTask
                            : '',
                        IfScriptAfterTask:
                          zzzodUserData.Info?.IfScriptAfterTask !== undefined
                            ? zzzodUserData.Info.IfScriptAfterTask
                            : false,
                        ScriptAfterTask:
                          zzzodUserData.Info?.ScriptAfterTask !== undefined
                            ? zzzodUserData.Info.ScriptAfterTask
                            : '',
                        Notes:
                          zzzodUserData.Info?.Notes !== undefined ? zzzodUserData.Info.Notes : '',
                        Tag: zzzodUserData.Info?.Tag !== undefined ? zzzodUserData.Info.Tag : null,
                      },
                      Game: {
                        GameRegion:
                          zzzodUserData.Game?.GameRegion !== undefined
                            ? zzzodUserData.Game.GameRegion
                            : 'cn',
                        GamePath:
                          zzzodUserData.Game?.GamePath !== undefined
                            ? zzzodUserData.Game.GamePath
                            : '',
                        GameLanguage:
                          zzzodUserData.Game?.GameLanguage !== undefined
                            ? zzzodUserData.Game.GameLanguage
                            : 'cn',
                        Account:
                          zzzodUserData.Game?.Account !== undefined
                            ? zzzodUserData.Game.Account
                            : '',
                        Password:
                          zzzodUserData.Game?.Password !== undefined
                            ? zzzodUserData.Game.Password
                            : '',
                        BilibiliAccountName:
                          zzzodUserData.Game?.BilibiliAccountName !== undefined
                            ? zzzodUserData.Game.BilibiliAccountName
                            : '',
                      },
                      OneDragon: {
                        AppList:
                          zzzodUserData.OneDragon?.AppList !== undefined
                            ? zzzodUserData.OneDragon.AppList
                            : '[]',
                      },
                      Notify: {
                        Enabled:
                          zzzodUserData.Notify?.Enabled !== undefined
                            ? zzzodUserData.Notify.Enabled
                            : false,
                        PushLogMode:
                          zzzodUserData.Notify?.PushLogMode !== undefined
                            ? zzzodUserData.Notify.PushLogMode
                            : '汇总',
                        IfSendStatistic:
                          zzzodUserData.Notify?.IfSendStatistic !== undefined
                            ? zzzodUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          zzzodUserData.Notify?.IfSendMail !== undefined
                            ? zzzodUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          zzzodUserData.Notify?.ToAddress !== undefined
                            ? zzzodUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          zzzodUserData.Notify?.IfServerChan !== undefined
                            ? zzzodUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          zzzodUserData.Notify?.ServerChanKey !== undefined
                            ? zzzodUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          zzzodUserData.Data?.LastProxyDate !== undefined
                            ? zzzodUserData.Data.LastProxyDate
                            : '2000-01-01',
                        ProxyTimes:
                          zzzodUserData.Data?.ProxyTimes !== undefined
                            ? zzzodUserData.Data.ProxyTimes
                            : 0,
                        LastProxyStatus:
                          zzzodUserData.Data?.LastProxyStatus !== undefined
                            ? zzzodUserData.Data.LastProxyStatus
                            : '未知',
                      },
                    }
                  } else if (userIndex.type === 'BAAHUserConfig' && userData) {
                    const baahUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: baahUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          baahUserData.Info?.Name !== undefined
                            ? baahUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          baahUserData.Info?.Status !== undefined ? baahUserData.Info.Status : true,
                        RemainedDay:
                          baahUserData.Info?.RemainedDay !== undefined
                            ? baahUserData.Info.RemainedDay
                            : -1,
                        ConfigName:
                          baahUserData.Info?.ConfigName !== undefined
                            ? baahUserData.Info.ConfigName
                            : '',
                        ActivityConfigName:
                          baahUserData.Info?.ActivityConfigName !== undefined
                            ? baahUserData.Info.ActivityConfigName
                            : '',
                        IfActivityAdapt:
                          baahUserData.Info?.IfActivityAdapt != null
                            ? baahUserData.Info.IfActivityAdapt
                            : false,
                        ActivityLineType:
                          baahUserData.Info?.ActivityLineType != null
                            ? baahUserData.Info.ActivityLineType
                            : 'CN',
                        Notes:
                          baahUserData.Info?.Notes !== undefined ? baahUserData.Info.Notes : '',
                        Tag: baahUserData.Info?.Tag !== undefined ? baahUserData.Info.Tag : null,
                      },
                      Notify: {
                        Enabled:
                          baahUserData.Notify?.Enabled !== undefined
                            ? baahUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          baahUserData.Notify?.IfSendStatistic !== undefined
                            ? baahUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          baahUserData.Notify?.IfSendMail !== undefined
                            ? baahUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          baahUserData.Notify?.ToAddress !== undefined
                            ? baahUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          baahUserData.Notify?.IfServerChan !== undefined
                            ? baahUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          baahUserData.Notify?.ServerChanKey !== undefined
                            ? baahUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          baahUserData.Data?.LastProxyDate !== undefined
                            ? baahUserData.Data.LastProxyDate
                            : '',
                        ProxyTimes:
                          baahUserData.Data?.ProxyTimes !== undefined
                            ? baahUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'MSSUserConfig' && userData) {
                    const mssUserData = userData as unknown as LooseUserConfig
                    return {
                      id: userIndex.uid,
                      name: mssUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          mssUserData.Info?.Name !== undefined
                            ? mssUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Status:
                          mssUserData.Info?.Status !== undefined ? mssUserData.Info.Status : true,
                        RemainedDay:
                          mssUserData.Info?.RemainedDay !== undefined
                            ? mssUserData.Info.RemainedDay
                            : -1,
                        Mode: mssUserData.Info?.Mode !== undefined ? mssUserData.Info.Mode : '用户',
                        PlanMode:
                          mssUserData.Info?.PlanMode !== undefined
                            ? mssUserData.Info.PlanMode
                            : 'Fixed',
                        IfActivityFirst:
                          mssUserData.Info?.IfActivityFirst !== undefined
                            ? mssUserData.Info.IfActivityFirst
                            : true,
                        ClimbMode:
                          mssUserData.Info?.ClimbMode !== undefined
                            ? mssUserData.Info.ClimbMode
                            : 'Close',
                        ClimbStartWeekday:
                          mssUserData.Info?.ClimbStartWeekday !== undefined
                            ? mssUserData.Info.ClimbStartWeekday
                            : 'Monday',
                        ClimbTimes:
                          mssUserData.Info?.ClimbTimes !== undefined
                            ? mssUserData.Info.ClimbTimes
                            : 5,
                        Notes: mssUserData.Info?.Notes !== undefined ? mssUserData.Info.Notes : '',
                        Tag: mssUserData.Info?.Tag !== undefined ? mssUserData.Info.Tag : null,
                      },
                      Notify: {
                        Enabled:
                          mssUserData.Notify?.Enabled !== undefined
                            ? mssUserData.Notify.Enabled
                            : false,
                        IfSendStatistic:
                          mssUserData.Notify?.IfSendStatistic !== undefined
                            ? mssUserData.Notify.IfSendStatistic
                            : false,
                        IfSendMail:
                          mssUserData.Notify?.IfSendMail !== undefined
                            ? mssUserData.Notify.IfSendMail
                            : false,
                        ToAddress:
                          mssUserData.Notify?.ToAddress !== undefined
                            ? mssUserData.Notify.ToAddress
                            : '',
                        IfServerChan:
                          mssUserData.Notify?.IfServerChan !== undefined
                            ? mssUserData.Notify.IfServerChan
                            : false,
                        ServerChanKey:
                          mssUserData.Notify?.ServerChanKey !== undefined
                            ? mssUserData.Notify.ServerChanKey
                            : '',
                      },
                      Data: {
                        LastProxyDate:
                          mssUserData.Data?.LastProxyDate !== undefined
                            ? mssUserData.Data.LastProxyDate
                            : '',
                        ProxyTimes:
                          mssUserData.Data?.ProxyTimes !== undefined
                            ? mssUserData.Data.ProxyTimes
                            : 0,
                        ClimbCompletedWeek:
                          mssUserData.Data?.ClimbCompletedWeek !== undefined
                            ? mssUserData.Data.ClimbCompletedWeek
                            : '',
                      },
                    }
                  }

                  return null
                })
                .filter((user): user is User => user !== null)

              return {
                ...script,
                users,
              }
            } else {
              // 如果获取用户失败，返回空用户列表的脚本
              return {
                ...script,
                users: [],
              }
            }
          } catch (err) {
            const errorMsg = err instanceof Error ? err.message : String(err)
            logger.warn(`获取脚本 ${script.uid} 的用户数据失败: ${errorMsg}`)
            return {
              ...script,
              users: [],
            }
          }
        })
      )

      return scriptsWithUsers
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取脚本列表失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return []
    } finally {
      loading.value = false
    }
  }

  // 获取单个脚本
  const getScript = async (scriptId: string): Promise<ScriptDetail | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.getScriptApiScriptsGetPost({ scriptId })

      if (response.code !== 200) {
        const errorMsg = response.message || '获取脚本详情失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 检查是否有数据返回
      if (response.index.length === 0) {
        throw new Error('脚本不存在')
      }

      const item = response.index[0]
      const config = response.data[item.uid]
      const scriptType = resolveScriptType(item.type)

      return {
        uid: item.uid,
        type: scriptType,
        name: config?.Info?.Name || `${item.type}脚本`,
        config,
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取脚本详情失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const getHsrStageOptions = async (
    scriptId: string,
    engine: HSRStageEngine
  ): Promise<HSRStageOptionsData | null> => {
    try {
      const payload = await HsrService.getHsrStageOptionsApiApiScriptsHsrStageOptionsGet(
        scriptId,
        engine
      )
      if (payload?.code !== 200) {
        throw new Error(payload?.message || '接口返回异常')
      }
      return payload.data ?? null
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取 HSR 体力副本选项失败'
      error.value = errorMsg
      logger.error(`获取 HSR 体力副本选项失败: ${errorMsg}`)
      return null
    }
  }

  // 预览 MaaFW 项目 interface：返回后端原始响应，让编辑页把 code=400 的 message 原样呈现
  const previewMaaFWInterface = async (path: string): Promise<MaaFWInterfacePreviewOut | null> => {
    try {
      return await MaaFwService.previewMaafwInterfaceApiScriptsMaafwPreviewPost({ path })
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err)
      logger.error(`预览 MaaFW interface 失败: ${errorMsg}`)
      return null
    }
  }

  const prepareMaaFWAgentEnv = async (
    path: string,
    scriptId?: string,
    force = false
  ): Promise<MaaFWAgentEnvPrepareOut | null> => {
    try {
      return await MaaFwService.prepareMaafwAgentEnvApiScriptsMaafwAgentEnvPreparePost({
        path,
        scriptId,
        force,
      })
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err)
      logger.error(`准备 MaaFW 运行环境失败: ${errorMsg}`)
      return null
    }
  }

  const getMaaEndOptions = async (scriptId: string): Promise<MaaEndOptionsOut | null> => {
    try {
      const response = await Service.getMaaendOptionsApiScriptsMaaendOptionsPost({ scriptId })
      if (response?.code !== 200) throw new Error(response?.message || '接口返回异常')
      return response
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取 MaaEnd 动态选项失败'
      error.value = errorMsg
      logger.error(`获取 MaaEnd 动态选项失败: ${errorMsg}`)
      message.error(t('misc.maaendIncompleteUninstallIt'))
      return null
    }
  }

  // 删除脚本
  const deleteScript = async (scriptId: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.deleteScriptApiScriptsDeletePost({ scriptId })

      if (response.code !== 200) {
        const errorMsg = response.message || '删除脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 播放删除脚本成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_script_instance')

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '删除脚本失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  // 更新脚本
  const updateScript = async (
    scriptId: string,
    data: Record<string, unknown>
  ): Promise<boolean> => {
    if (isScriptConfigLocked(getTaskRuntimeStates(), scriptId)) {
      const errorMsg = t('edit.configLocked')
      error.value = errorMsg
      message.warning(errorMsg)
      return false
    }

    loading.value = true
    error.value = null

    try {
      // 创建数据副本并移除 SubConfigsInfo 字段
      const dataToSend = { ...data }
      delete dataToSend.SubConfigsInfo

      const response = await Service.updateScriptApiScriptsUpdatePost({
        scriptId,
        data: dataToSend as ScriptUpdateIn['data'],
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '更新脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '更新脚本失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  // 重新排序脚本
  const reorderScript = async (scriptIds: string[]): Promise<boolean> => {
    // loading.value = true // 排序通常不需要全屏loading，或者可以使用局部loading
    error.value = null

    try {
      const requestData: ScriptReorderIn = {
        indexList: scriptIds,
      }

      const response = await Service.reorderScriptApiScriptsOrderPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '脚本排序失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '脚本排序失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      // loading.value = false
    }
  }

  const importScriptConfigFile = (scriptId: string, userId: string | null) =>
    Service.importScriptConfigFileApiScriptsConfigImportPost({ scriptId, userId })

  return {
    loading,
    error,
    addScript,
    getScripts,
    getScriptsWithUsers,
    getScript,
    getHsrStageOptions,
    getMaaEndOptions,
    previewMaaFWInterface,
    prepareMaaFWAgentEnv,
    deleteScript,
    updateScript,
    reorderScript,
    importScriptConfigFile,
  }
}
