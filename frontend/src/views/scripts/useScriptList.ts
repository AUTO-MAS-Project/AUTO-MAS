import { useConfigLoader, type ConfigSnapshot } from '@/services/configUiSync'
import { Service, type ScriptGetOut } from '@/api'
import type { UnavailableConfigCard } from '@/components/UnavailableConfigCards.vue'
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
  const scripts = ref<ScriptListItem[]>([])
  const unavailable = ref<UnavailableConfigCard[]>([])
  const loadedOnce = ref(false)

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
  const getScriptsWithUsers = async (
    read?: (snapshot: ConfigSnapshot) => void
  ): Promise<ScriptListItem[]> => {
    loading.value = true
    try {
      let snapshot: ScriptGetOut | null = null
      // 列表页呈现失败原因与重试，避免请求层再弹同一错误。
      const scripts = await getScripts(false, {
        showError: false,
        read: response => {
          snapshot = response as ScriptGetOut
          read?.(response)
        },
      })
      error.value = requestError.value
      // 所属插件不可用（没装上、解析不了或已停用）的托管只给只读卡片，不进可运行的列表。
      const disabled = new Set(
        (snapshot as ScriptGetOut | null)?.index
          .filter(item => item.pluginAvailable === false)
          .map(item => item.uid) ?? []
      )
      unavailable.value = [
        ...((snapshot as ScriptGetOut | null)?.unavailable ?? []).map(item => ({
          uid: item.uid,
          name: item.name ?? '',
          typeLabel: item.typeLabel,
          reason: item.reason,
          plugin: item.plugin,
          detail: item.detail,
        })),
        ...scripts
          .filter(script => disabled.has(script.uid))
          .map(script => ({
            uid: script.uid,
            name: script.name,
            typeLabel: String(script.type),
            reason: 'plugin_disabled' as const,
          })),
      ]
      return await Promise.all(
        scripts
          .filter(script => !disabled.has(script.uid))
          .map(async script => {
            const result = await getScriptUsers(script.uid)
            return toScriptListItem(script, result.users, result.error)
          })
      )
    } finally {
      loading.value = false
    }
  }

  const loadScripts = useConfigLoader(['config', 'script-list'], async read => {
    try {
      const result = await getScriptsWithUsers(read)
      if (!error.value) scripts.value = result
    } catch (failure) {
      const errorMsg = getApiErrorMessage(failure, t('core.apiErrors.scriptListFailed'))
      logger.error(`加载脚本列表失败: ${errorMsg}`)
      error.value = errorMsg
    } finally {
      // 首次加载结束（不论成功失败）后置位，避免初始闪烁
      loadedOnce.value = true
    }
  })

  return { scripts, unavailable, loadedOnce, loadScripts, getScriptUsers, loading, error }
}
