import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  type GeneralConfig,
  type MaaConfig,
  type MaaEndConfig,
  type M9AConfig,
  type MaaFWConfig,
  type OkwwConfig,
  type OkNteConfig,
  type SrcConfig,
  type HSRConfig,
  type BetterGIConfig,
  type HSRStageOptionsData,
  type MaaEndOptionsOut,
  type MaaFWInterfacePreviewOut,
  type MaaFWAgentEnvPrepareOut,
  ScriptCreateIn,
  type ScriptReorderIn,
  HsrService,
  MaaFwService,
  Service,
} from '@/api'
import type { ScriptDetail, ScriptType } from '@/types/script'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = window.electronAPI.getLogger('脚本API')

type ScriptListConfig =
  | MaaConfig
  | GeneralConfig
  | OkwwConfig
  | OkNteConfig
  | SrcConfig
  | MaaEndConfig
  | M9AConfig
  | MaaFWConfig
  | HSRConfig
  | BetterGIConfig

type HSRStageEngine = 'M7A' | 'SRA'

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
  const getScripts = async (
    manageLoading: boolean = true
  ): Promise<
    {
      uid: string
      type: string
      name: string
      config: ScriptListConfig
    }[]
  > => {
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
  const getScriptsWithUsers = async (): Promise<
    Awaited<
      | {
          uid: string
          type: string
          name: string
          config: ScriptListConfig
          users: (
            | {
                id: string
                name: any
                Info: {
                  Name: any
                  Id: any
                  Mode: any
                  StageMode: any
                  Server: any
                  Status: any
                  RemainedDay: any
                  Annihilation: any
                  InfrastMode: any
                  InfrastName: any
                  InfrastIndex: any
                  Password: any
                  Notes: any
                  MedicineNumb: any
                  SeriesNumb: any
                  Stage: any
                  Stage_1: any
                  Stage_2: any
                  Stage_3: any
                  Stage_Remain: any
                }
                Task: {
                  IfStartUp: any
                  IfRecruit: any
                  IfInfrast: any
                  IfFight: any
                  IfMall: any
                  IfAward: any
                  IfRoguelike: any
                  IfReclamation: any
                }
                Notify: {
                  Enabled: any
                  IfSendStatistic: any
                  IfSendSixStar: any
                  IfSendMail: any
                  ToAddress: any
                  IfServerChan: any
                  ServerChanKey: any
                }
                Data: {
                  LastProxyDate: any
                  ProxyTimes: any
                }
              }
            | {
                id: string
                name: any
                Info: {
                  Name: any
                  Status: any
                  RemainedDay: any
                  IfScriptBeforeTask: any
                  ScriptBeforeTask: any
                  IfScriptAfterTask: any
                  ScriptAfterTask: any
                  Notes: any
                }
                Notify: {
                  Enabled: any
                  IfSendStatistic: any
                  IfSendMail: any
                  ToAddress: any
                  IfServerChan: any
                  ServerChanKey: any
                }
                Data: { LastProxyDate: any; ProxyTimes: any }
              }
            | null
          )[]
        }
      | {
          uid: string
          type: string
          name: string
          config: ScriptListConfig
          users: any[]
        }
      | {
          uid: string
          type: string
          name: string
          config: ScriptListConfig
          users: any[]
        }
    >[]
  > => {
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
                    const maaUserData = userData as any
                    return {
                      id: userIndex.uid,
                      name: maaUserData.Info?.Name || `用户${userIndex.uid}`,
                      Info: {
                        Name:
                          maaUserData.Info?.Name !== undefined
                            ? maaUserData.Info.Name
                            : `用户${userIndex.uid}`,
                        Id: maaUserData.Info?.Id !== undefined ? maaUserData.Info.Id : '',
                        Mode: maaUserData.Info?.Mode !== undefined ? maaUserData.Info.Mode : '简洁',
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
                        InfrastIndex:
                          maaUserData.Info?.InfrastIndex !== undefined
                            ? maaUserData.Info.InfrastIndex
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
                        Stage_Remain:
                          maaUserData.Info?.Stage_Remain !== undefined
                            ? maaUserData.Info.Stage_Remain
                            : '-',
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
                        IfRoguelike:
                          maaUserData.Task?.IfRoguelike !== undefined
                            ? maaUserData.Task.IfRoguelike
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
                        DepotMaintainPlans:
                          maaUserData.Task?.DepotMaintainPlans !== undefined
                            ? maaUserData.Task.DepotMaintainPlans
                            : '[]',
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
                            : '',
                        ProxyTimes:
                          maaUserData.Data?.ProxyTimes !== undefined
                            ? maaUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'SrcUserConfig' && userData) {
                    const srcUserData = userData as any
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
                        Mode: srcUserData.Info?.Mode !== undefined ? srcUserData.Info.Mode : '简洁',
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
                            : '',
                        ProxyTimes:
                          srcUserData.Data?.ProxyTimes !== undefined
                            ? srcUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'GeneralUserConfig' && userData) {
                    const generalUserData = userData as any
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
                            : '',
                        ProxyTimes:
                          generalUserData.Data?.ProxyTimes !== undefined
                            ? generalUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'MaaEndUserConfig' && userData) {
                    const maaEndUserData = userData as any
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
                            : '简洁',
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
                        IfSeizeEntrustTask:
                          maaEndUserData.Task?.IfSeizeEntrustTask != null
                            ? maaEndUserData.Task.IfSeizeEntrustTask
                            : true,
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
                            : '',
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
                    const m9aUserData = userData as any
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
                            : '',
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
                    const okwwUserData = userData as any
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
                          okwwUserData.Info?.Mode !== undefined
                            ? okwwUserData.Info.Mode
                            : isOkwwUser
                              ? '脚本'
                              : '简洁',
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
                            : '',
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
                  } else if (String(userIndex.type) === 'MaaFWUserConfig' && userData) {
                    const maafwUserData = userData as any
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
                        LastProxyDate: maafwUserData.Data?.LastProxyDate ?? '',
                        ProxyTimes: maafwUserData.Data?.ProxyTimes ?? 0,
                        IfPassCheck: maafwUserData.Data?.IfPassCheck ?? false,
                        LastSklandDate: '',
                      },
                    } as any
                  } else if (userIndex.type === 'HSRUserConfig' && userData) {
                    const hsrUserData = userData as any
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
                            : '',
                        ProxyTimes:
                          hsrUserData.Data?.ProxyTimes !== undefined
                            ? hsrUserData.Data.ProxyTimes
                            : 0,
                      },
                    }
                  } else if (userIndex.type === 'BetterGIUserConfig' && userData) {
                    const bettergiUserData = userData as any
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
                            : '',
                        ProxyTimes:
                          bettergiUserData.Data?.ProxyTimes !== undefined
                            ? bettergiUserData.Data.ProxyTimes
                            : 0,
                        LastProxyStatus:
                          bettergiUserData.Data?.LastProxyStatus !== undefined
                            ? bettergiUserData.Data.LastProxyStatus
                            : '未知',
                        LastOneDragonConfig:
                          bettergiUserData.Data?.LastOneDragonConfig !== undefined
                            ? bettergiUserData.Data.LastOneDragonConfig
                            : '',
                      },
                    }
                  } else if (userIndex.type === 'BetterGIUserConfig' && userData) {
                    const bettergiUserData = userData as any
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
                            : '',
                        ProxyTimes:
                          bettergiUserData.Data?.ProxyTimes !== undefined
                            ? bettergiUserData.Data.ProxyTimes
                            : 0,
                        LastProxyStatus:
                          bettergiUserData.Data?.LastProxyStatus !== undefined
                            ? bettergiUserData.Data.LastProxyStatus
                            : '未知',
                        LastOneDragonConfig:
                          bettergiUserData.Data?.LastOneDragonConfig !== undefined
                            ? bettergiUserData.Data.LastOneDragonConfig
                            : '',
                      },
                    }
                  }

                  return null
                })
                .filter(user => user !== null)

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
    scriptId?: string
  ): Promise<MaaFWAgentEnvPrepareOut | null> => {
    try {
      return await MaaFwService.prepareMaafwAgentEnvApiScriptsMaafwAgentEnvPreparePost({
        path,
        scriptId,
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
  const updateScript = async (scriptId: string, data: any): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      // 创建数据副本并移除 SubConfigsInfo 字段
      const dataToSend = { ...data }
      delete dataToSend.SubConfigsInfo

      const response = await Service.updateScriptApiScriptsUpdatePost({
        scriptId,
        data: dataToSend,
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
