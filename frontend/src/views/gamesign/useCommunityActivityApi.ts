import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'

export type ActivityStatus = 'success' | 'empty' | 'limited' | 'unavailable' | 'failed'

export interface ActivityTask {
  name: string
  completed: number
  target: number
  status: string
  period: string
}

export interface ActivityResource {
  name: string
  current: number
  target: number
  status: string
}

export interface ActivitySnapshot {
  account: string
  accountUid: string
  game: string
  platform: string
  status: ActivityStatus
  completed: number | null
  target: number | null
  tasks: ActivityTask[]
  resources: ActivityResource[]
  reason: string
  updatedAt: string
  roleName: string
  roleUid: string
  server: string
  source: string
}

interface ActivityEnvelope {
  code?: number
  status?: string
  message?: string
  data?: ActivitySnapshot[]
}

const activityUrl = () => `${OpenAPI.BASE.replace(/\/+$/, '')}/api/tools/community/activity/query`

export function useCommunityActivityApi() {
  const queryActivity = async (accountIds: string[] | null = null): Promise<ActivitySnapshot[]> => {
    try {
      const response = await axios.post<ActivityEnvelope>(activityUrl(), { accountIds })
      const payload = response.data
      if (payload.code !== undefined && payload.code !== 200) {
        throw new Error(payload.message || '日常便笺查询失败')
      }
      if (!Array.isArray(payload.data)) {
        throw new Error('日常便笺响应格式无效')
      }
      return payload.data
    } catch (error) {
      if (axios.isAxiosError<ActivityEnvelope>(error) && error.response?.data?.message) {
        throw new Error(String(error.response.data.message))
      }
      throw error instanceof Error ? error : new Error('日常便笺查询失败')
    }
  }

  return { queryActivity }
}
