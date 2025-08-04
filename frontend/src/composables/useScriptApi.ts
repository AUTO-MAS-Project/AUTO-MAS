import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type {
  ScriptType,
  AddScriptResponse,
  MAAScriptConfig,
  GeneralScriptConfig,
  GetScriptsResponse,
  ScriptDetail,
  ScriptIndexItem,
  DeleteScriptResponse,
  UpdateScriptResponse
} from '../types/script.ts'

const API_BASE_URL = 'http://localhost:8000/api'

export function useScriptApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加脚本
  const addScript = async (type: ScriptType): Promise<AddScriptResponse | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE_URL}/add/scripts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ type }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data: AddScriptResponse = await response.json()
      
      // 检查API响应的code字段
      if (data.code !== 200) {
        const errorMsg = data.message || '添加脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }
      
      return data
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

  // 获取所有脚本
  const getScripts = async (): Promise<ScriptDetail[]> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE_URL}/scripts/get`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}), // 传空对象获取全部脚本
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const apiResponse: GetScriptsResponse = await response.json()

      // 转换API响应为前端需要的格式
      const scripts: ScriptDetail[] = apiResponse.index.map((item: ScriptIndexItem) => {
        const config = apiResponse.data[item.uid]
        const scriptType: ScriptType = item.type === 'MaaConfig' ? 'MAA' : 'General'

        // 从配置中获取脚本名称
        let name = ''
        if (scriptType === 'MAA') {
          name = (config as MAAScriptConfig).Info.Name || '未命名MAA脚本'
        } else {
          name = (config as GeneralScriptConfig).Info.Name || '未命名General脚本'
        }

        return {
          uid: item.uid,
          type: scriptType,
          name,
          config,
          createTime: new Date().toLocaleString() // 暂时使用当前时间，后续可从API获取
        }
      })

      return scripts
    } catch (err) {
      error.value = err instanceof Error ? err.message : '获取脚本列表失败'
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
      const response = await fetch(`${API_BASE_URL}/scripts/get`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ scriptId }), // 传scriptId获取单个脚本
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const apiResponse: GetScriptsResponse = await response.json()

      // 检查是否有数据返回
      if (apiResponse.index.length === 0) {
        throw new Error('脚本不存在')
      }

      const item = apiResponse.index[0]
      const config = apiResponse.data[item.uid]
      const scriptType: ScriptType = item.type === 'MaaConfig' ? 'MAA' : 'General'

      // 从配置中获取脚本名称
      let name = ''
      if (scriptType === 'MAA') {
        name = (config as MAAScriptConfig).Info.Name || '未命名MAA脚本'
      } else {
        name = (config as GeneralScriptConfig).Info.Name || '未命名General脚本'
      }

      return {
        uid: item.uid,
        type: scriptType,
        name,
        config,
        createTime: new Date().toLocaleString() // 暂时使用当前时间，后续可从API获取
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '获取脚本详情失败'
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新脚本
  const updateScript = async (scriptId: string, data: MAAScriptConfig | GeneralScriptConfig): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      // 创建数据副本并移除 SubConfigsInfo 字段
      const { SubConfigsInfo, ...dataToSend } = data

      const response = await fetch(`${API_BASE_URL}/scripts/update`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ scriptId, data: dataToSend }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const apiResponse: UpdateScriptResponse = await response.json()
      
      // 根据code判断是否成功（非200就是不成功）
      if (apiResponse.code !== 200) {
        const errorMsg = apiResponse.message || '更新脚本失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '更新脚本失败'
      error.value = errorMsg
      // 如果错误不是来自API响应（即没有显示过message.error），则显示错误消息
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        // API响应错误已经在上面显示了，这里只处理其他错误
      } else {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  // 删除脚本
  const deleteScript = async (scriptId: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE_URL}/scripts/delete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ scriptId }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const apiResponse: DeleteScriptResponse = await response.json()
      
      // 根据code判断是否成功（非200就是不成功）
      if (apiResponse.code !== 200) {
        throw new Error(apiResponse.message || '删除脚本失败')
      }

      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : '删除脚本失败'
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
    updateScript,
    deleteScript,
  }
}