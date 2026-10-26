import { Service } from '@/api'
import { analyticsCountBucket, beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps, AnalyticsQueueKind } from '@/types/analytics'

// 只复用已读取的配置，在有界本机内存中关联类别，不为统计额外查询。
const queueKinds = new Map<string, AnalyticsQueueKind>()
const scheduleModes = new Map<string, 'fixed_time' | 'interval' | 'unknown'>()
function remember<T>(cache: Map<string, T>, id: string, value: T): void {
  if (!cache.has(id) && cache.size >= 128) cache.delete(cache.keys().next().value!)
  cache.set(id, value)
}
const queueKind = (cycle: unknown): AnalyticsQueueKind =>
  typeof cycle === 'boolean' ? (cycle ? 'cycle' : 'normal') : 'unknown'
const scheduleMode = (mode: unknown) =>
  mode === 'fixed_time' || mode === 'interval' ? mode : 'unknown'

async function manage<T extends { code?: number }>(
  action: AnalyticsEventProps['queue_manage_finished']['action'],
  kind: AnalyticsQueueKind | ((response: T) => AnalyticsQueueKind),
  request: () => Promise<T>,
  count = 1,
  complete: (response: T) => boolean = () => true
): Promise<T> {
  const operation = beginAnalyticsOperation('queue_manage_finished')
  const dimensions = { action, count_bucket: analyticsCountBucket(count) }
  try {
    const response = await request()
    operation.finish({
      ...dimensions,
      queue_kind: typeof kind === 'function' ? kind(response) : kind,
      outcome: response.code === 200 && complete(response) ? 'success' : 'failure',
    })
    return response
  } catch (error) {
    operation.finish({
      ...dimensions,
      queue_kind: typeof kind === 'string' ? kind : 'unknown',
      outcome: 'failure',
    })
    throw error
  }
}

async function schedule<T extends { code?: number }>(
  dimensions: Pick<AnalyticsEventProps['queue_schedule_changed'], 'schedule_kind' | 'action'>,
  request: () => Promise<T>
): Promise<T> {
  const operation = beginAnalyticsOperation('queue_schedule_changed')
  try {
    const response = await request()
    operation.finish({ ...dimensions, outcome: response.code === 200 ? 'success' : 'failure' })
    return response
  } catch (error) {
    operation.finish({ ...dimensions, outcome: 'failure' })
    throw error
  }
}

type SchedulePatch = NonNullable<
  Parameters<typeof Service.updateItemApiQueueItemUpdatePost>[0]['data']['Schedule']
>
function scheduleAction(
  data: SchedulePatch
): AnalyticsEventProps['queue_schedule_changed']['action'] {
  if (Object.keys(data).length !== 1) return 'configure'
  if (data.Enabled !== undefined) return data.Enabled ? 'enable' : 'disable'
  if (data.NextRunAt !== undefined) return 'run_once'
  if (data.Mode !== undefined) return 'mode'
  if (data.IntervalMinutes !== undefined || data.IntervalAnchor !== undefined) return 'interval'
  if (data.Time !== undefined) return 'time'
  if (data.Days !== undefined) return 'days'
  return 'configure'
}

/** 保留生成 API 的原参数、响应与异常，页面继续拥有回读和提示流程。 */
export const queueApi = {
  async getQueues(params: Parameters<typeof Service.getQueuesApiQueueGetPost>[0]) {
    const response = await Service.getQueuesApiQueueGetPost(params)
    if (response.code === 200) {
      for (const [id, data] of Object.entries(response.data))
        remember(queueKinds, id, queueKind(data.Info?.CycleEnabled))
    }
    return response
  },
  async getItems(params: Parameters<typeof Service.getItemApiQueueItemGetPost>[0]) {
    const response = await Service.getItemApiQueueItemGetPost(params)
    if (response.code === 200) {
      for (const [id, data] of Object.entries(response.data))
        remember(scheduleModes, id, scheduleMode(data.Schedule?.Mode))
    }
    return response
  },
  async createQueue() {
    const response = await manage(
      'create',
      result => queueKind(result.data?.Info?.CycleEnabled),
      () => Service.addQueueApiQueueAddPost(),
      1,
      result => Boolean(result.queueId)
    )
    if (response.code === 200 && response.queueId)
      remember(queueKinds, response.queueId, queueKind(response.data.Info?.CycleEnabled))
    return response
  },
  async deleteQueue(params: Parameters<typeof Service.deleteQueueApiQueueDeletePost>[0]) {
    const response = await manage('delete', queueKinds.get(params.queueId) ?? 'unknown', () =>
      Service.deleteQueueApiQueueDeletePost(params)
    )
    if (response.code === 200) queueKinds.delete(params.queueId)
    return response
  },
  async updateQueue(params: Parameters<typeof Service.updateQueueApiQueueUpdatePost>[0]) {
    const info = params.data.Info
    const request = async () => {
      const response = await Service.updateQueueApiQueueUpdatePost(params)
      if (response.code === 200 && typeof info?.CycleEnabled === 'boolean')
        remember(queueKinds, params.queueId, queueKind(info.CycleEnabled))
      return response
    }
    if (typeof info?.TimeEnabled === 'boolean')
      return schedule(
        { schedule_kind: 'queue_time', action: info.TimeEnabled ? 'enable' : 'disable' },
        request
      )
    if (typeof info?.CycleEnabled === 'boolean')
      return schedule(
        { schedule_kind: 'cycle', action: info.CycleEnabled ? 'enable' : 'disable' },
        request
      )
    if (info?.StartUpMode !== undefined)
      return schedule({ schedule_kind: 'startup', action: 'configure' }, request)
    return manage('update', queueKinds.get(params.queueId) ?? 'unknown', request)
  },
  async updateItem(params: Parameters<typeof Service.updateItemApiQueueItemUpdatePost>[0]) {
    const data = params.data.Schedule
    const request = async () => {
      const response = await Service.updateItemApiQueueItemUpdatePost(params)
      if (response.code === 200 && data?.Mode)
        remember(scheduleModes, params.queueItemId, scheduleMode(data.Mode))
      return response
    }
    if (data)
      return schedule(
        {
          schedule_kind: data.Mode
            ? scheduleMode(data.Mode)
            : (scheduleModes.get(params.queueItemId) ?? 'unknown'),
          action: scheduleAction(data),
        },
        request
      )
    return manage('item_update', queueKinds.get(params.queueId) ?? 'unknown', request)
  },
  updateSchedule(queueId: string, queueItemId: string, data: SchedulePatch) {
    return queueApi.updateItem({ queueId, queueItemId, data: { Schedule: data } })
  },
  async addItem(params: Parameters<typeof Service.addItemApiQueueItemAddPost>[0]) {
    return manage(
      'item_add',
      queueKinds.get(params.queueId) ?? 'unknown',
      () => Service.addItemApiQueueItemAddPost(params),
      1,
      result => Boolean(result.queueItemId)
    )
  },
  async deleteItem(params: Parameters<typeof Service.deleteItemApiQueueItemDeletePost>[0]) {
    const response = await manage('item_remove', queueKinds.get(params.queueId) ?? 'unknown', () =>
      Service.deleteItemApiQueueItemDeletePost(params)
    )
    if (response.code === 200) scheduleModes.delete(params.queueItemId)
    return response
  },
  async reorderItems(params: Parameters<typeof Service.reorderItemApiQueueItemOrderPost>[0]) {
    return manage(
      'item_reorder',
      queueKinds.get(params.queueId) ?? 'unknown',
      () => Service.reorderItemApiQueueItemOrderPost(params),
      params.indexList.length
    )
  },
}
