import { Service } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { toScriptListItem, toScriptListUser, type ScriptListItem } from './scriptListModel'

const logger = window.electronAPI.getLogger('脚本列表')

export function useScriptList() {
  const { getScripts, loading, error } = useScriptApi()

  // 列表仅获取并组合展示数据，不重建专项配置或参与配置保存。
  const getScriptsWithUsers = async (): Promise<ScriptListItem[]> => {
    loading.value = true
    error.value = null
    try {
      const scripts = await getScripts(false)
      return await Promise.all(
        scripts.map(async script => {
          try {
            const response = await Service.getUserApiScriptsUserGetPost({ scriptId: script.uid })
            if (response.code !== 200) return toScriptListItem(script, [], true)
            const users = response.index.flatMap(index => {
              const user = toScriptListUser(script.uid, index, response.data[index.uid])
              return user ? [user] : []
            })
            return toScriptListItem(script, users)
          } catch (err) {
            const errorMsg = err instanceof Error ? err.message : String(err)
            logger.warn(`获取脚本 ${script.uid} 的用户数据失败: ${errorMsg}`)
            return toScriptListItem(script, [], true)
          }
        })
      )
    } finally {
      loading.value = false
    }
  }

  return { getScriptsWithUsers, loading, error }
}
