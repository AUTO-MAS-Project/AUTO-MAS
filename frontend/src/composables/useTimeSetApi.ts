import { Service as Api } from '@/api'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { analyticsCountBucket } from '@/utils/analytics'

/** 时间集合每次实际写入计一条，不上传日期、时刻或条目标识。 */
export const Service = {
  addTimeSetApiQueueTimeAddPost(input: Parameters<typeof Api.addTimeSetApiQueueTimeAddPost>[0]) {
    return observeFeature(
      'queue_time_set_changed',
      { action: 'create', count_bucket: '1' },
      () => Api.addTimeSetApiQueueTimeAddPost(input),
      result => (result.code === 200 && result.timeSetId ? 'success' : 'failure')
    )
  },
  updateTimeSetApiQueueTimeUpdatePost(
    input: Parameters<typeof Api.updateTimeSetApiQueueTimeUpdatePost>[0]
  ) {
    return observeFeature(
      'queue_time_set_changed',
      { action: 'update', count_bucket: '1' },
      () => Api.updateTimeSetApiQueueTimeUpdatePost(input),
      apiOutcome
    )
  },
  deleteTimeSetApiQueueTimeDeletePost(
    input: Parameters<typeof Api.deleteTimeSetApiQueueTimeDeletePost>[0]
  ) {
    return observeFeature(
      'queue_time_set_changed',
      { action: 'delete', count_bucket: '1' },
      () => Api.deleteTimeSetApiQueueTimeDeletePost(input),
      apiOutcome
    )
  },
  reorderTimeSetApiQueueTimeOrderPost(
    input: Parameters<typeof Api.reorderTimeSetApiQueueTimeOrderPost>[0]
  ) {
    return observeFeature(
      'queue_time_set_changed',
      { action: 'reorder', count_bucket: analyticsCountBucket(input.indexList.length) },
      () => Api.reorderTimeSetApiQueueTimeOrderPost(input),
      apiOutcome
    )
  },
}
