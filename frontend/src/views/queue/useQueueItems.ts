import { nextTick, onScopeDispose, type Ref } from 'vue'
import { queueApi } from '@/composables/useQueueApi'
import { useConfigLoader } from '@/services/configUiSync'
import { useQueueScopedList } from './useQueueScopedList'

type QueueItemRow = { id: string; script: string; schedule: Record<string, any> }

export function useQueueItems(activeQueueId: Ref<string>, pageInstance: number) {
  const logger = window.electronAPI.getLogger('调度队列')
  let active = true
  onScopeDispose(() => {
    active = false
  })
  const queueItemList = useQueueScopedList<QueueItemRow>(activeQueueId)
  const currentQueueItems = queueItemList.items
  // 刷新队列项数据
  const refreshQueueItems = useConfigLoader(
    () => ['config', 'queue-items', activeQueueId.value, pageInstance],
    async read => {
      if (!activeQueueId.value) {
        // 不清空数组，避免骨架屏闪现
        return
      }

      const selected = activeQueueId.value
      try {
        // 使用专门的队列项API获取数据
        const response = await queueApi.getItems({
          queueId: selected,
        })

        read(response)
        if (response.code !== 200) {
          logger.error(`获取队列项数据失败: ${JSON.stringify(response)}`)
          // 已显示本队列内容时不清空，避免骨架屏闪现
          queueItemList.fail(selected)
          return
        }

        const queueItems: QueueItemRow[] = []

        // 处理队列项数据
        if (response.index && Array.isArray(response.index)) {
          response.index.forEach((item: any) => {
            try {
              const queueItemId = item.uid
              if (!queueItemId || !response.data || !response.data[queueItemId]) return

              const queueItemData = response.data[queueItemId]
              if (queueItemData?.Info) {
                queueItems.push({
                  id: queueItemId,
                  script: queueItemData.Info.ScriptId || '',
                  schedule: { ...(queueItemData.Schedule || {}) },
                })
              }
            } catch (itemError) {
              const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
              logger.warn(`解析单个队列项失败: ${errorMsg}, item: ${JSON.stringify(item)}`)
            }
          })
        }

        // 使用nextTick确保数据更新不会导致渲染问题
        await nextTick()
        if (!active) return
        // 已切走的队列只进缓存，不替换当前显示
        queueItemList.commit(selected, queueItems)
        logger.debug(`刷新后的队列项数据: ${JSON.stringify(queueItems)}`) // 调试日志
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`刷新队列项列表失败: ${errorMsg}`)
        // 已显示本队列内容时不清空，避免骨架屏闪现
        queueItemList.fail(selected)
      }
    }
  )

  // 子表就地保存成功后同步缓存和当前显示，同一队列里组件重挂载时不会显示保存前的值
  const onQueueItemSaved = (queueId: string, itemId: string, schedule: Record<string, any>) => {
    queueItemList.patch(queueId, itemId, item => {
      item.schedule = { ...item.schedule, ...JSON.parse(JSON.stringify(schedule)) }
    })
  }

  return { queueItemList, currentQueueItems, refreshQueueItems, onQueueItemSaved }
}
