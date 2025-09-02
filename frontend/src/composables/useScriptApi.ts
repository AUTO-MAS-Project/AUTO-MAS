import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, ScriptCreateIn } from '@/api'
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

  // 获取脚本列表
  const getScripts = async (): Promise<ScriptDetail[]> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.getScriptsApiScriptsGetPost({})

      if (response.code !== 200) {
        const errorMsg = response.message || '获取脚本列表失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 将API响应转换为ScriptDetail数组
      const scriptDetails: ScriptDetail[] = response.index.map(indexItem => ({
        uid: indexItem.uid,
        type: indexItem.type === 'MaaConfig' ? 'MAA' : 'General',
        name: response.data[indexItem.uid]?.Info?.Name || `${indexItem.type}脚本`,
        config: response.data[indexItem.uid],
      }))

      return scriptDetails
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

  // 获取脚本列表及其用户数据
  const getScriptsWithUsers = async (): Promise<ScriptDetail[]> => {
    loading.value = true
    error.value = null

    try {
      // 首先获取脚本列表
      const scriptDetails = await getScripts()

      // 为每个脚本获取用户数据
      const scriptsWithUsers = await Promise.all(
        scriptDetails.map(async (script) => {
          try {
            // 获取该脚本下的用户列表
            const userResponse = await Service.getUserApiScriptsUserGetPost({
              scriptId: script.uid
            })

            if (userResponse.code === 200) {
              // 将用户数据转换为User格式
              const users = userResponse.index.map(userIndex => {
                const userData = userResponse.data[userIndex.uid]

                if (userIndex.type === 'MaaUserConfig' && userData) {
                  const maaUserData = userData as any
                  return {
                    id: userIndex.uid,
                    name: maaUserData.Info?.Name || `用户${userIndex.uid}`,
                    Info: {
                      Name: maaUserData.Info?.Name || `用户${userIndex.uid}`,
                      Id: maaUserData.Info?.Id || '',
                      Password: maaUserData.Info?.Password || '',
                      Server: maaUserData.Info?.Server || '官服',
                      MedicineNumb: maaUserData.Info?.MedicineNumb || 0,
                      RemainedDay: maaUserData.Info?.RemainedDay || -1,
                      SeriesNumb: maaUserData.Info?.SeriesNumb || '',
                      Notes: maaUserData.Info?.Notes || '',
                      Status: maaUserData.Info?.Status !== undefined ? maaUserData.Info.Status : true,
                      Mode: maaUserData.Info?.Mode || 'MAA',
                      InfrastMode: maaUserData.Info?.InfrastMode || '默认',
                      Routine: maaUserData.Info?.Routine !== undefined ? maaUserData.Info.Routine : true,
                      Annihilation: maaUserData.Info?.Annihilation || '当期',
                      Stage: maaUserData.Info?.Stage || '1-7',
                      StageMode: maaUserData.Info?.StageMode || '刷完即停',
                      Stage_1: maaUserData.Info?.Stage_1 || '',
                      Stage_2: maaUserData.Info?.Stage_2 || '',
                      Stage_3: maaUserData.Info?.Stage_3 || '',
                      Stage_Remain: maaUserData.Info?.Stage_Remain || '',
                      IfSkland: maaUserData.Info?.IfSkland || false,
                      SklandToken: maaUserData.Info?.SklandToken || '',
                    },
                    Task: {
                      IfBase: maaUserData.Task?.IfBase !== undefined ? maaUserData.Task.IfBase : true,
                      IfCombat: maaUserData.Task?.IfCombat !== undefined ? maaUserData.Task.IfCombat : true,
                      IfMall: maaUserData.Task?.IfMall !== undefined ? maaUserData.Task.IfMall : true,
                      IfMission: maaUserData.Task?.IfMission !== undefined ? maaUserData.Task.IfMission : true,
                      IfRecruiting: maaUserData.Task?.IfRecruiting !== undefined ? maaUserData.Task.IfRecruiting : true,
                      IfReclamation: maaUserData.Task?.IfReclamation || false,
                      IfAutoRoguelike: maaUserData.Task?.IfAutoRoguelike || false,
                      IfWakeUp: maaUserData.Task?.IfWakeUp || false,
                    },
                    Notify: {
                      Enabled: maaUserData.Notify?.Enabled || false,
                      ToAddress: maaUserData.Notify?.ToAddress || '',
                      IfSendMail: maaUserData.Notify?.IfSendMail || false,
                      IfSendSixStar: maaUserData.Notify?.IfSendSixStar || false,
                      IfSendStatistic: maaUserData.Notify?.IfSendStatistic || false,
                      IfServerChan: maaUserData.Notify?.IfServerChan || false,
                      IfCompanyWebHookBot: maaUserData.Notify?.IfCompanyWebHookBot || false,
                      ServerChanKey: maaUserData.Notify?.ServerChanKey || '',
                      ServerChanChannel: maaUserData.Notify?.ServerChanChannel || '',
                      ServerChanTag: maaUserData.Notify?.ServerChanTag || '',
                      CompanyWebHookBotUrl: maaUserData.Notify?.CompanyWebHookBotUrl || '',
                    },
                    Data: {
                      CustomInfrastPlanIndex: maaUserData.Data?.CustomInfrastPlanIndex || '',
                      IfPassCheck: maaUserData.Data?.IfPassCheck || false,
                      LastAnnihilationDate: maaUserData.Data?.LastAnnihilationDate || '',
                      LastProxyDate: maaUserData.Data?.LastProxyDate || '',
                      LastSklandDate: maaUserData.Data?.LastSklandDate || '',
                      ProxyTimes: maaUserData.Data?.ProxyTimes || 0,
                    },
                    QFluentWidgets: {
                      ThemeColor: maaUserData.QFluentWidgets?.ThemeColor || 'blue',
                      ThemeMode: maaUserData.QFluentWidgets?.ThemeMode || 'system',
                    },
                  }
                } else if (userIndex.type === 'GeneralUserConfig' && userData) {
                  const generalUserData = userData as any
                  return {
                    id: userIndex.uid,
                    name: generalUserData.Info?.Name || `用户${userIndex.uid}`,
                    Info: {
                      Name: generalUserData.Info?.Name || `用户${userIndex.uid}`,
                      Id: generalUserData.Info?.Id || '',
                      Password: generalUserData.Info?.Password || '',
                      Server: generalUserData.Info?.Server || '官服',
                      MedicineNumb: 0,
                      RemainedDay: -1,
                      SeriesNumb: '',
                      Notes: generalUserData.Info?.Notes || '',
                      Status: generalUserData.Info?.Status !== undefined ? generalUserData.Info.Status : true,
                      Mode: 'General',
                      InfrastMode: '默认',
                      Routine: true,
                      Annihilation: '当期',
                      Stage: '1-7',
                      StageMode: '刷完即停',
                      Stage_1: '',
                      Stage_2: '',
                      Stage_3: '',
                      Stage_Remain: '',
                      IfSkland: false,
                      SklandToken: '',
                    },
                    Task: {
                      IfBase: true,
                      IfCombat: true,
                      IfMall: true,
                      IfMission: true,
                      IfRecruiting: true,
                      IfReclamation: false,
                      IfAutoRoguelike: false,
                      IfWakeUp: false,
                    },
                    Notify: {
                      Enabled: false,
                      ToAddress: '',
                      IfSendMail: false,
                      IfSendSixStar: false,
                      IfSendStatistic: false,
                      IfServerChan: false,
                      IfCompanyWebHookBot: false,
                      ServerChanKey: '',
                      ServerChanChannel: '',
                      ServerChanTag: '',
                      CompanyWebHookBotUrl: '',
                    },
                    Data: {
                      CustomInfrastPlanIndex: '',
                      IfPassCheck: false,
                      LastAnnihilationDate: '',
                      LastProxyDate: '',
                      LastSklandDate: '',
                      ProxyTimes: 0,
                    },
                    QFluentWidgets: {
                      ThemeColor: 'blue',
                      ThemeMode: 'system',
                    },
                  }
                }

                return null
              }).filter(user => user !== null)

              return {
                ...script,
                users
              }
            } else {
              // 如果获取用户失败，返回空用户列表的脚本
              return {
                ...script,
                users: []
              }
            }
          } catch (err) {
            console.warn(`获取脚本 ${script.uid} 的用户数据失败:`, err)
            return {
              ...script,
              users: []
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
      const response = await Service.getScriptsApiScriptsGetPost({ scriptId })

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
