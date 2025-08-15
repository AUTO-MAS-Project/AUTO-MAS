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
    getScript,
    deleteScript,
    updateScript,
  }
}
