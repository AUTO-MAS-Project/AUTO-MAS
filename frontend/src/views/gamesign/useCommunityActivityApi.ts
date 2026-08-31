import {
  ApiError,
  CommunityService,
  type CommunityActivityResourceOut,
  type CommunityActivitySnapshotOut,
  type CommunityActivityTaskOut,
} from '@/api'

export type ActivityStatus = CommunityActivitySnapshotOut['status']
export type ActivityTask = CommunityActivityTaskOut & { period: string }
export type ActivityResource = CommunityActivityResourceOut
export type ActivitySnapshot = Omit<
  CommunityActivitySnapshotOut,
  'completed' | 'target' | 'tasks' | 'resources'
> & {
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

const normalizeSnapshot = (snapshot: CommunityActivitySnapshotOut): ActivitySnapshot => ({
  ...snapshot,
  completed: snapshot.completed ?? null,
  target: snapshot.target ?? null,
  tasks: (snapshot.tasks ?? []).map(task => ({
    ...task,
    period: task.period ?? 'daily',
  })),
  resources: snapshot.resources ?? [],
  reason: snapshot.reason ?? '',
  updatedAt: snapshot.updatedAt ?? '',
  roleName: snapshot.roleName ?? '',
  roleUid: snapshot.roleUid ?? '',
  server: snapshot.server ?? '',
  source: snapshot.source ?? '',
})

const responseMessage = (error: ApiError): string => {
  const body = error.body as { message?: unknown } | undefined
  return typeof body?.message === 'string' ? body.message : error.message
}

export function useCommunityActivityApi() {
  const queryActivity = async (accountIds: string[] | null = null): Promise<ActivitySnapshot[]> => {
    try {
      const payload =
        await CommunityService.queryCommunityActivityApiToolsCommunityActivityQueryPost({
          accountIds,
        })
      if (payload.code !== undefined && payload.code !== 200) {
        throw new Error(payload.message || '日常便笺查询失败')
      }
      if (!Array.isArray(payload.data)) {
        throw new Error('日常便笺响应格式无效')
      }
      return payload.data.map(normalizeSnapshot)
    } catch (error) {
      if (error instanceof ApiError) {
        throw new Error(responseMessage(error))
      }
      throw error instanceof Error ? error : new Error('日常便笺查询失败')
    }
  }

  return { queryActivity }
}
