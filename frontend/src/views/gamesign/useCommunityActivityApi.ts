import { Service } from '@/api'
import { parseSignResult } from './gameSignDisplay'

type ActivityTask = { period: string; [key: string]: unknown }
type ActivityResource = Record<string, unknown>

export type ActivitySnapshot = {
  game?: string
  platform?: string
  status?: string
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
  [key: string]: unknown
}

export function useCommunityActivityApi() {
  const queryActivity = async (accountIds: string[] | null = null): Promise<ActivitySnapshot[]> => {
    void accountIds
    // 社区活动服务属于后续专项迁移范围，先返回空结果让主页保持可用。
    return []
  }

  const querySignResult = async () => {
    const response = await Service.getToolsApiToolsGetPost()
    if (response.code !== 200) {
      throw new Error(response.message || '读取签到结果失败')
    }
    return parseSignResult(response.data?.GameSign?.Result)
  }

  return { queryActivity, querySignResult }
}
