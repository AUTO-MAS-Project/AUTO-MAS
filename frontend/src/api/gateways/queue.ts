import {
  createQueueApiQueuePost,
  createQueueItemApiQueueQueueIdItemsPost,
  createTimeSetApiQueueQueueIdTimesPost,
  deleteQueueApiQueueQueueIdDelete,
  deleteQueueItemApiQueueQueueIdItemsQueueItemIdDelete,
  deleteTimeSetApiQueueQueueIdTimesTimeSetIdDelete,
  getQueueApiQueueQueueIdGet,
  getQueueItemApiQueueQueueIdItemsQueueItemIdGet,
  getTimeSetApiQueueQueueIdTimesTimeSetIdGet,
  listQueueItemsApiQueueQueueIdItemsGet,
  listQueuesApiQueueGet,
  listTimeSetsApiQueueQueueIdTimesGet,
  reorderQueueApiQueueOrderPatch,
  reorderQueueItemsApiQueueQueueIdItemsOrderPatch,
  reorderTimeSetsApiQueueQueueIdTimesOrderPatch,
  updateQueueApiQueueQueueIdPatch,
  updateQueueItemApiQueueQueueIdItemsQueueItemIdPatch,
  updateTimeSetApiQueueQueueIdTimesTimeSetIdPatch,
} from '../generated/sdk.gen'
import type { IndexOrderPatch, QueueItemRead, QueueRead, TimeSetRead } from '../generated/types.gen'

export const queueApi = {
  list() {
    return listQueuesApiQueueGet()
  },

  create() {
    return createQueueApiQueuePost()
  },

  get(queueId: string) {
    return getQueueApiQueueQueueIdGet({ path: { queue_id: queueId } })
  },

  update(queueId: string, payload: QueueRead) {
    return updateQueueApiQueueQueueIdPatch({
      path: { queue_id: queueId },
      body: payload,
    })
  },

  remove(queueId: string) {
    return deleteQueueApiQueueQueueIdDelete({ path: { queue_id: queueId } })
  },

  reorder(payload: IndexOrderPatch) {
    return reorderQueueApiQueueOrderPatch({ body: payload })
  },
}

export const timeSetApi = {
  list(queueId: string) {
    return listTimeSetsApiQueueQueueIdTimesGet({ path: { queue_id: queueId } })
  },

  create(queueId: string) {
    return createTimeSetApiQueueQueueIdTimesPost({ path: { queue_id: queueId } })
  },

  get(queueId: string, timeSetId: string) {
    return getTimeSetApiQueueQueueIdTimesTimeSetIdGet({
      path: { queue_id: queueId, time_set_id: timeSetId },
    })
  },

  update(queueId: string, timeSetId: string, payload: TimeSetRead) {
    return updateTimeSetApiQueueQueueIdTimesTimeSetIdPatch({
      path: { queue_id: queueId, time_set_id: timeSetId },
      body: payload,
    })
  },

  remove(queueId: string, timeSetId: string) {
    return deleteTimeSetApiQueueQueueIdTimesTimeSetIdDelete({
      path: { queue_id: queueId, time_set_id: timeSetId },
    })
  },

  reorder(queueId: string, payload: IndexOrderPatch) {
    return reorderTimeSetsApiQueueQueueIdTimesOrderPatch({
      path: { queue_id: queueId },
      body: payload,
    })
  },
}

export const queueItemApi = {
  list(queueId: string) {
    return listQueueItemsApiQueueQueueIdItemsGet({ path: { queue_id: queueId } })
  },

  create(queueId: string) {
    return createQueueItemApiQueueQueueIdItemsPost({ path: { queue_id: queueId } })
  },

  get(queueId: string, queueItemId: string) {
    return getQueueItemApiQueueQueueIdItemsQueueItemIdGet({
      path: { queue_id: queueId, queue_item_id: queueItemId },
    })
  },

  update(queueId: string, queueItemId: string, payload: QueueItemRead) {
    return updateQueueItemApiQueueQueueIdItemsQueueItemIdPatch({
      path: { queue_id: queueId, queue_item_id: queueItemId },
      body: payload,
    })
  },

  remove(queueId: string, queueItemId: string) {
    return deleteQueueItemApiQueueQueueIdItemsQueueItemIdDelete({
      path: { queue_id: queueId, queue_item_id: queueItemId },
    })
  },

  reorder(queueId: string, payload: IndexOrderPatch) {
    return reorderQueueItemsApiQueueQueueIdItemsOrderPatch({
      path: { queue_id: queueId },
      body: payload,
    })
  },
}
