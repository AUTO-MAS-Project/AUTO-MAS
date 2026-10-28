import { Service } from '@/api'
import { ref } from 'vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { translate as t } from '@/i18n'
import { getApiErrorMessage } from '@/utils/apiError'
import {
  toScriptListItem,
  toScriptListUser,
  type ScriptListItem,
  type ScriptListUser,
} from './scriptListModel'

const logger = window.electronAPI.getLogger('脚本列表')

export function useScriptList() {
  const { getScripts, loading, error: requestError } = useScriptApi()
  const error = ref<string | null>(null)

  const getScriptUsers = async (
    scriptId: string
  ): Promise<{ users: ScriptListUser[]; error: string | null }> => {
    try {
      const response = await Service.getUserApiScriptsUserGetPost({ scriptId })
      if (response.code !== 200)
        throw new Error(response.message || t('core.apiErrors.userListFailed'))
      const users = response.index.flatMap(index => {
        const user = toScriptListUser(scriptId, index, response.data[index.uid])
        return user ? [user] : []
      })
      return { users, error: null }
    } catch (err) {
      const detail = getApiErrorMessage(err, t('core.apiErrors.userListFailed'))
      logger.warn(`获取脚本 ${scriptId} 的用户数据失败: ${detail}`)
      return { users: [], error: detail }
    }
  }

  // 列表仅获取并组合展示数据，不重建专项配置或参与配置保存。
  const getScriptsWithUsers = async (): Promise<ScriptListItem[]> => {
    loading.value = true
    try {
      // 列表页呈现失败原因与重试，避免请求层再弹同一错误。
      const scripts = await getScripts(false, { showError: false })
      error.value = requestError.value
      return await Promise.all(
        scripts.map(async script => {
          const result = await getScriptUsers(script.uid)
          return toScriptListItem(script, result.users, result.error)
        })
      )
    } finally {
      loading.value = false
    }
  }

  return { getScriptsWithUsers, getScriptUsers, loading, error }
}
