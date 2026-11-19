import { nextTick, onScopeDispose, ref, type Ref } from 'vue'
import { Service, type TimeSet_Info } from '@/api'
import { useConfigLoader } from '@/services/configUiSync'

type QueueTimeSet = {
  id: string
  time: string
  enabled: boolean
  days: NonNullable<TimeSet_Info['Days']>
}

export function useQueueTimeSets(activeQueueId: Ref<string>) {
  const logger = window.electronAPI.getLogger('调度队列')
  const currentTimeSets = ref<QueueTimeSet[]>([])
  let active = true
  onScopeDispose(() => {
    active = false
  })
  // 刷新定时项数据
  const refreshTimeSets = useConfigLoader(
    () => ['config', 'queue-times', activeQueueId.value],
    async read => {
      if (!activeQueueId.value) {
        currentTimeSets.value = []
        return
      }

      const selected = activeQueueId.value
      try {
        // 使用专门的定时项API获取数据
        const response = await Service.getTimeSetApiQueueTimeGetPost({
          queueId: selected,
        })

        read(response)
        if (selected !== activeQueueId.value) return
        if (response.code !== 200) {
          logger.error(`获取定时项数据失败: ${JSON.stringify(response)}`)
          // 不清空数组，避免骨架屏闪现
          return
        }

        const timeSets: QueueTimeSet[] = []

        // 处理定时项数据
        if (response.index && Array.isArray(response.index)) {
          response.index.forEach(item => {
            try {
              const timeSetId = item.uid
              if (!timeSetId || !response.data || !response.data[timeSetId]) return

              const timeSetData = response.data[timeSetId]
              if (timeSetData?.Info) {
                const timeString = timeSetData.Info.Time || '00:00'

                timeSets.push({
                  id: timeSetId,
                  time: timeString,
                  enabled: Boolean(timeSetData.Info.Enabled),
                  days: timeSetData.Info.Days || [],
                })
              }
            } catch (itemError) {
              const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
              logger.warn(`解析单个定时项失败: ${errorMsg}, item: ${JSON.stringify(item)}`)
            }
          })
        }

        // 使用nextTick确保数据更新不会导致渲染问题
        await nextTick()
        if (!active || selected !== activeQueueId.value) return
        // 直接替换数组内容，而不是清空再赋值，避免骨架屏闪现
        currentTimeSets.value.splice(0, currentTimeSets.value.length, ...timeSets)
        logger.debug(`刷新后的定时项数据: ${JSON.stringify(timeSets)}`) // 调试日志
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`刷新定时项列表失败: ${errorMsg}`)
        // 不清空数组，避免骨架屏闪现
      }
    }
  )

  return { currentTimeSets, refreshTimeSets }
}
