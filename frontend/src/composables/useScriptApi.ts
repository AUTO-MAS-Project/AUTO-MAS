import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { type GeneralConfig, type MaaConfig, ScriptCreateIn, Service } from '@/api'
import type { ScriptDetail, ScriptType } from '@/types/script'

export function useScriptApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加脚本
  const addScript = async (type: ScriptType) => {
    loading.value = true
    error.value = null

    try {
      const requestData: ScriptCreateIn = {
        type: type === 'MAA' ? ScriptCreateIn.type.MAA : ScriptCreateIn.type.GENERAL,
      }

      const response = await Service.addScriptApiScriptsAddPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '添加脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return {
        scriptId: response.scriptId,
        message: response.message || '脚本添加成功',
        data: response.data,
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '添加脚本失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
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
      config: MaaConfig | GeneralConfig
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
        type: indexItem.type === 'MaaConfig' ? 'MAA' : 'General',
        name: response.data[indexItem.uid]?.Info?.Name || `${indexItem.type}脚本`,
        config: response.data[indexItem.uid],
      }))
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取脚本列表失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
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
        config: MaaConfig | GeneralConfig
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
              IfSkland: any
              SklandToken: any
            }
            Task: {
              IfWakeUp: any
              IfRecruiting: any
              IfBase: any
              IfCombat: any
              IfMall: any
              IfMission: any
              IfAutoRoguelike: any
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
              CustomWebhooks: any
            }
            Data: {
              LastAnnihilationDate: any
              LastProxyDate: any
              LastSklandDate: any
              IfPassCheck: any
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
              CustomWebhooks: any
            }
            Data: { LastProxyDate: any; ProxyTimes: any }
          }
          | null
        )[]
      }
      | { uid: string; type: string; name: string; config: MaaConfig | GeneralConfig; users: any[] }
      | {
        uid: string
        type: string
        name: string
        config: MaaConfig | GeneralConfig
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
                        IfSkland:
                          maaUserData.Info?.IfSkland !== undefined
                            ? maaUserData.Info.IfSkland
                            : false,
                        SklandToken:
                          maaUserData.Info?.SklandToken !== undefined
                            ? maaUserData.Info.SklandToken
                            : '',
                      },
                      Task: {
                        IfWakeUp:
                          maaUserData.Task?.IfWakeUp !== undefined
                            ? maaUserData.Task.IfWakeUp
                            : true,
                        IfRecruiting:
                          maaUserData.Task?.IfRecruiting !== undefined
                            ? maaUserData.Task.IfRecruiting
                            : true,
                        IfBase:
                          maaUserData.Task?.IfBase !== undefined ? maaUserData.Task.IfBase : true,
                        IfCombat:
                          maaUserData.Task?.IfCombat !== undefined
                            ? maaUserData.Task.IfCombat
                            : true,
                        IfMall:
                          maaUserData.Task?.IfMall !== undefined ? maaUserData.Task.IfMall : true,
                        IfMission:
                          maaUserData.Task?.IfMission !== undefined
                            ? maaUserData.Task.IfMission
                            : true,
                        IfAutoRoguelike:
                          maaUserData.Task?.IfAutoRoguelike !== undefined
                            ? maaUserData.Task.IfAutoRoguelike
                            : false,
                        IfReclamation:
                          maaUserData.Task?.IfReclamation !== undefined
                            ? maaUserData.Task.IfReclamation
                            : false,
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
                        CustomWebhooks:
                          maaUserData.Notify?.CustomWebhooks !== undefined
                            ? maaUserData.Notify.CustomWebhooks
                            : [],
                      },
                      Data: {
                        LastAnnihilationDate:
                          maaUserData.Data?.LastAnnihilationDate !== undefined
                            ? maaUserData.Data.LastAnnihilationDate
                            : '',
                        LastProxyDate:
                          maaUserData.Data?.LastProxyDate !== undefined
                            ? maaUserData.Data.LastProxyDate
                            : '',
                        LastSklandDate:
                          maaUserData.Data?.LastSklandDate !== undefined
                            ? maaUserData.Data.LastSklandDate
                            : '',
                        IfPassCheck:
                          maaUserData.Data?.IfPassCheck !== undefined
                            ? maaUserData.Data.IfPassCheck
                            : false,
                        ProxyTimes:
                          maaUserData.Data?.ProxyTimes !== undefined
                            ? maaUserData.Data.ProxyTimes
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
                        CustomWebhooks:
                          generalUserData.Notify?.CustomWebhooks !== undefined
                            ? generalUserData.Notify.CustomWebhooks
                            : [],
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
            console.warn(`获取脚本 ${script.uid} 的用户数据失败:`, err)
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
      if (!err.message?.includes('HTTP error')) {
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
      const scriptType: ScriptType = item.type === 'MaaConfig' ? 'MAA' : 'General'

      return {
        uid: item.uid,
        type: scriptType,
        name: config?.Info?.Name || `${item.type}脚本`,
        config,
        createTime: new Date().toLocaleString(),
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取脚本详情失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
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

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '删除脚本失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
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
      const { SubConfigsInfo, ...dataToSend } = data

      const response = await Service.updateScriptApiScriptsUpdatePost({
        scriptId,
        data: dataToSend,
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '更新脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      message.success(response.message || '脚本更新成功')
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '更新脚本失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    addScript,
    getScripts,
    getScriptsWithUsers,
    getScript,
    deleteScript,
    updateScript,
  }
}
