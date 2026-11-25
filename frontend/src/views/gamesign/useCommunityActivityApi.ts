import { observeFeature } from '@/utils/featureAnalytics'
import {
  ApiError,
  CommunityActivitySnapshotOut,
  CommunityService,
  Service,
  type CommunityActivityResourceOut,
  type CommunityActivityTaskOut,
} from '@/api'
import { SignflowError, signflowApi, type SignflowNoteSnapshot } from '@/services/signflowApi'
import { parseSignResult } from './gameSignDisplay'

type ActivityTask = CommunityActivityTaskOut & { period: string }
type ActivityResource = CommunityActivityResourceOut
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

/** 一次便笺查询的结果；插件与宿主两条来源归一成同一形状再交给调用方 */
interface ActivityQueryResult {
  code: number
  message?: string
  data?: ActivitySnapshot[]
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

/** 插件快照已经把字段投影成驼峰，这里只做数值与枚举的收口，避免把松散字典直接当合同用 */
const resolveStatus = (status: string): CommunityActivitySnapshotOut.status => {
  const known = Object.values(CommunityActivitySnapshotOut.status) as string[]
  return known.includes(status)
    ? (status as CommunityActivitySnapshotOut.status)
    : CommunityActivitySnapshotOut.status.FAILED
}

const asNumber = (value: unknown, fallback: number): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

const asText = (value: unknown): string => (typeof value === 'string' ? value : '')

const normalizeTask = (task: Record<string, unknown>): ActivityTask => {
  const period = asText(task.period)
  return {
    name: asText(task.name),
    completed: asNumber(task.completed, 0),
    target: asNumber(task.target, 0),
    status: asText(task.status),
    period: period || 'daily',
  }
}

const normalizeResource = (resource: Record<string, unknown>): ActivityResource => ({
  name: asText(resource.name),
  current: asNumber(resource.current, 0),
  target: asNumber(resource.target, 0),
  status: asText(resource.status),
})

const fromPlugin = (note: SignflowNoteSnapshot): ActivitySnapshot => ({
  account: note.account,
  accountUid: note.accountUid,
  game: note.game,
  platform: note.platform,
  status: resolveStatus(note.status),
  completed: note.completed ?? null,
  target: note.target ?? null,
  tasks: (note.tasks ?? []).map(normalizeTask),
  resources: (note.resources ?? []).map(normalizeResource),
  reason: note.reason ?? '',
  updatedAt: note.updatedAt ?? '',
  roleName: note.roleName ?? '',
  roleUid: note.roleUid ?? '',
  server: note.server ?? '',
  source: note.source ?? '',
})

/** 插件未启用时网关给 404，服务缺失时插件给 400 且文案含「未启用」 */
const isPluginUnavailable = (error: unknown): boolean =>
  error instanceof SignflowError &&
  (error.code === 404 || (error.code === 400 && error.message.includes('未启用')))

const responseMessage = (error: ApiError): string => {
  const body = error.body as { message?: unknown } | undefined
  return typeof body?.message === 'string' ? body.message : error.message
}

/**
 * 便笺查询优先走 SignFlow 附属插件，插件未启用时回退宿主内置的社区查询。
 *
 * 两条路径都还在：插件已装但没启用的用户升级后不会突然查不到便笺，
 * 而插件一旦启用就由它承担责任（宿主那份实现后续会迁出）。
 */
const querySnapshots = async (accountIds: string[] | null): Promise<ActivityQueryResult> => {
  try {
    const plugin = await signflowApi.queryNotes(accountIds)
    return {
      code: plugin.code ?? 200,
      message: plugin.message,
      data: Array.isArray(plugin.data) ? plugin.data.map(fromPlugin) : undefined,
    }
  } catch (error) {
    if (!isPluginUnavailable(error)) throw error
  }
  const host = await CommunityService.queryCommunityActivityApiToolsCommunityActivityQueryPost({
    accountIds,
  })
  return {
    code: host.code ?? 500,
    message: host.message,
    data: Array.isArray(host.data) ? host.data.map(normalizeSnapshot) : undefined,
  }
}

export function useCommunityActivityApi() {
  const queryActivity = async (accountIds: string[] | null = null): Promise<ActivitySnapshot[]> => {
    try {
      const payload = await observeFeature(
        'community_activity_requested',
        { operation_kind: 'refresh' },
        () => querySnapshots(accountIds),
        result =>
          result.code === 409
            ? 'blocked'
            : result.code !== 200 || !Array.isArray(result.data)
              ? 'failure'
              : result.data.some(
                    item => item.status !== CommunityActivitySnapshotOut.status.SUCCESS
                  )
                ? 'partial'
                : 'success'
      )
      if (payload.code !== undefined && payload.code !== 200) {
        throw new Error(payload.message || '日常便笺查询失败')
      }
      if (!Array.isArray(payload.data)) {
        throw new Error('日常便笺响应格式无效')
      }
      return payload.data
    } catch (error) {
      if (error instanceof ApiError) {
        throw new Error(responseMessage(error))
      }
      throw error instanceof Error ? error : new Error('日常便笺查询失败')
    }
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
