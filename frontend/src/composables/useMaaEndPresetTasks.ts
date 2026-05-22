import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'

export interface MaaEndPresetTask {
  id: string
  taskName: string
  enabled: boolean
}

interface ApiResponse<T> {
  code: number
  message?: string
  data: T
}

const post = async <T>(path: string, body: Record<string, unknown>): Promise<ApiResponse<T>> => {
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return response.json()
}

export function useMaaEndPresetTasks() {
  const loading = ref(false)

  const loadPresetTasks = async (scriptId: string, userId: string = 'Default') => {
    loading.value = true
    try {
      const response = await post<MaaEndPresetTask[]>('/api/scripts/maaend/preset/tasks', {
        scriptId,
        userId,
      })
      if (response.code !== 200) {
        throw new Error(response.message || '加载 MaaEnd 预设任务失败')
      }
      return response.data
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载 MaaEnd 预设任务失败')
      return []
    } finally {
      loading.value = false
    }
  }

  const updatePresetTasks = async (
    scriptId: string,
    userId: string,
    taskIds: string[],
    enabled: boolean
  ) => {
    try {
      const response = await post<null>('/api/scripts/maaend/preset/tasks/update', {
        scriptId,
        userId,
        taskIds,
        enabled,
      })
      if (response.code !== 200) {
        throw new Error(response.message || '更新 MaaEnd 预设任务失败')
      }
      return true
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新 MaaEnd 预设任务失败')
      return false
    }
  }

  return { loading, loadPresetTasks, updatePresetTasks }
}
