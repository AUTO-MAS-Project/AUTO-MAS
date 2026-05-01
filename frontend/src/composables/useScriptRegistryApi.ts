import { ref } from 'vue'
import axios from 'axios'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api/core/OpenAPI'
import type {
  ScriptRecord,
  ScriptRecordCreateOut,
  ScriptRecordGetOut,
  ScriptTypeDescriptor,
  ScriptTypeGetOut,
  ScriptUserRecord,
  ScriptUserRecordCreateOut,
  ScriptUserRecordGetOut,
} from '@/types/scriptRegistry'

const logger = window.electronAPI.getLogger('脚本注册表API')

const post = async <T>(path: string, payload: Record<string, unknown>) => {
  const response = await axios.post<T>(`${OpenAPI.BASE}${path}`, payload)
  return response.data
}

export function useScriptRegistryApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const getScriptTypes = async (): Promise<ScriptTypeDescriptor[]> => {
    const data = await post<ScriptTypeGetOut>('/api/script-types/get', {})
    if (data.code !== 200) {
      throw new Error(data.message || '获取脚本类型失败')
    }
    return data.data || []
  }

  const getScripts = async (scriptId?: string | null): Promise<ScriptRecord[]> => {
    const data = await post<ScriptRecordGetOut>('/api/scripts2/get', {
      scriptId: scriptId || null,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '获取脚本列表失败')
    }
    return data.records || []
  }

  const addScript = async (type: string, scriptId?: string | null): Promise<ScriptRecord> => {
    const data = await post<ScriptRecordCreateOut>('/api/scripts2/add', {
      type,
      scriptId: scriptId || null,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '创建脚本失败')
    }
    return data.record
  }

  const updateScript = async (scriptId: string, config: Record<string, any>): Promise<void> => {
    const data = await post<{ code: number; message: string }>('/api/scripts2/update', {
      scriptId,
      config,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '更新脚本失败')
    }
  }

  const deleteScript = async (scriptId: string): Promise<void> => {
    const data = await post<{ code: number; message: string }>('/api/scripts2/delete', { scriptId })
    if (data.code !== 200) {
      throw new Error(data.message || '删除脚本失败')
    }
  }

  const reorderScripts = async (indexList: string[]): Promise<void> => {
    const data = await post<{ code: number; message: string }>('/api/scripts2/order', { indexList })
    if (data.code !== 200) {
      throw new Error(data.message || '脚本排序失败')
    }
  }

  const getUsers = async (scriptId: string, userId?: string | null): Promise<ScriptUserRecord[]> => {
    const data = await post<ScriptUserRecordGetOut>('/api/scripts2/users/get', {
      scriptId,
      userId: userId || null,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '获取用户失败')
    }
    return data.records || []
  }

  const addUser = async (scriptId: string): Promise<ScriptUserRecord> => {
    const data = await post<ScriptUserRecordCreateOut>('/api/scripts2/users/add', { scriptId })
    if (data.code !== 200) {
      throw new Error(data.message || '创建用户失败')
    }
    return data.record
  }

  const updateUser = async (
    scriptId: string,
    userId: string,
    config: Record<string, any>
  ): Promise<void> => {
    const data = await post<{ code: number; message: string }>('/api/scripts2/users/update', {
      scriptId,
      userId,
      config,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '更新用户失败')
    }
  }

  const deleteUser = async (scriptId: string, userId: string): Promise<void> => {
    const data = await post<{ code: number; message: string }>('/api/scripts2/users/delete', {
      scriptId,
      userId,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '删除用户失败')
    }
  }

  const reorderUsers = async (scriptId: string, indexList: string[]): Promise<void> => {
    const data = await post<{ code: number; message: string }>('/api/scripts2/users/order', {
      scriptId,
      indexList,
    })
    if (data.code !== 200) {
      throw new Error(data.message || '用户排序失败')
    }
  }

  const runAction = async <T>(action: () => Promise<T>, failureText: string) => {
    loading.value = true
    error.value = null
    try {
      return await action()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : failureText
      error.value = errorMsg
      logger.error(`${failureText}: ${errorMsg}`)
      message.error(errorMsg)
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    getScriptTypes,
    getScripts,
    addScript,
    updateScript,
    deleteScript,
    reorderScripts,
    getUsers,
    addUser,
    updateUser,
    deleteUser,
    reorderUsers,
    runAction,
  }
}
