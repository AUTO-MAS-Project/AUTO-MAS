import { ApiError, Service } from '@/api'
import { signflowApi, type SignflowNoteSnapshot } from '@/services/signflowApi'
import { observeFeature } from '@/utils/featureAnalytics'
import { parseSignResult } from './gameSignDisplay'

/** 便笺状态取值，与 signflow-notes 插件下发的字符串枚举一致 */
export type ActivityStatus = 'success' | 'empty' | 'limited' | 'unavailable' | 'failed'

const ACTIVITY_STATUSES: readonly ActivityStatus[] = [
  'success',
  'empty',
  'limited',
  'unavailable',
  'failed',
]

interface ActivityTask {
  name: string
  completed: number
  target: number
  status: string
  period: string
}

interface ActivityResource {
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

/** 一次便笺查询的结果信封，供遥测判定取值 */
interface ActivityQueryResult {
  code: number
  message?: string
  data?: ActivitySnapshot[]
}

const resolveStatus = (status: string): ActivityStatus =>
  ACTIVITY_STATUSES.includes(status as ActivityStatus) ? (status as ActivityStatus) : 'failed'

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

const responseMessage = (error: ApiError): string => {
  const body = error.body as { message?: unknown } | undefined
  return typeof body?.message === 'string' ? body.message : error.message
}

/** 便笺只由 SignFlow 附属插件提供；插件未启用时按失败处理，不再回退宿主实现 */
const querySnapshots = async (accountIds: string[] | null): Promise<ActivityQueryResult> => {
  const plugin = await signflowApi.queryNotes(accountIds)
  return {
    code: plugin.code ?? 200,
    message: plugin.message,
    data: Array.isArray(plugin.data) ? plugin.data.map(fromPlugin) : undefined,
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
              : result.data.some(item => item.status !== 'success')
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
    return parseSignResult(response.data?.SignFlow?.Result)
  }

  return { queryActivity, querySignResult }
}
