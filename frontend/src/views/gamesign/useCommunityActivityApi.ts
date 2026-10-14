import {
  Service,
  type CommunityActivitySnapshotOut,
  type CommunityActivityTaskOut,
  type CommunityActivityResourceOut,
} from '@/api'
import { requestApi } from '@/utils/apiResult'
import { parseSignResult } from './gameSignDisplay'

export type ActivitySnapshot = CommunityActivitySnapshotOut & {
  completed: number | null
  target: number | null
  tasks: CommunityActivityTaskOut[]
  resources: CommunityActivityResourceOut[]
  reason: string
  updatedAt: string
  roleName: string
  roleUid: string
  server: string
  source: string
}

export function useCommunityActivityApi() {
  const queryActivity = async (accountIds: string[] | null = null): Promise<ActivitySnapshot[]> => {
    const response = await requestApi(
      () => Service.queryCommunityActivityApiToolsCommunityActivityQueryPost({ accountIds }),
      '读取社区日常失败'
    )
    return (response.data ?? []).map(snapshot => ({
      ...snapshot,
      completed: snapshot.completed ?? null,
      target: snapshot.target ?? null,
      tasks: snapshot.tasks ?? [],
      resources: snapshot.resources ?? [],
      reason: snapshot.reason ?? '',
      updatedAt: snapshot.updatedAt ?? '',
      roleName: snapshot.roleName ?? '',
      roleUid: snapshot.roleUid ?? '',
      server: snapshot.server ?? '',
      source: snapshot.source ?? '',
    }))
  }
  const querySignResult = async () => {
    const response = await requestApi(() => Service.getToolsApiToolsGetPost(), '读取签到结果失败')
    return parseSignResult(response.data?.GameSign?.Result)
  }
  return { queryActivity, querySignResult }
}
