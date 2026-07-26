import { ref, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api'

const logger = window.electronAPI.getLogger('调度队列逻辑')

export interface QueueSummary {
  id: string
  name: string
}

export interface QueueItemRecord {
  id: string
  script: string | null
  scheduleEnabled: boolean
  scheduleMode: 'fixed_time' | 'interval'
  scheduleDays: string[]
  scheduleTime: string
  intervalMinutes: number
  intervalAnchor: 'start' | 'finish'
  nextRunAt: string
  lastCycleStartedAt: string
  lastCycleFinishedAt: string
  cycleRunId: string
  cycleState: 'idle' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  cycleRevision: number
  cycleResult: string
  cycleError: string
  cycleUpdatedAt: string
}

interface QueueInfoSnapshot {
  Name: string
  StartUpEnabled: boolean
  TimeEnabled: boolean
  CycleEnabled: boolean
  AfterAccomplish: string
}

const normalizeCycleState = (value: unknown): QueueItemRecord['cycleState'] =>
  value === 'running' || value === 'succeeded' || value === 'failed' || value === 'cancelled'
    ? value
    : 'idle'

export function useQueueLogic() {
  // 卸载守卫
  let isMounted = true
  let loadGeneration = 0
  let timeSetGeneration = 0
  let queueItemGeneration = 0

  // 队列列表
  const queueList = ref<QueueSummary[]>([])
  const activeQueueId = ref<string>('')
  const currentQueueData = ref<Record<string, any> | null>(null)

  // 当前队列配置
  const currentQueueName = ref<string>('')
  const currentStartUpEnabled = ref<boolean>(false)
  const currentTimeEnabled = ref<boolean>(false)
  const currentCycleEnabled = ref<boolean>(false)
  const currentAfterAccomplish = ref<string>('NoAction')
  const isEditingQueueName = ref<boolean>(false)

  // 当前队列的子数据
  const currentTimeSets = ref<any[]>([])
  const currentQueueItems = ref<QueueItemRecord[]>([])

  const loading = ref(true)
  let queueNameSavePending = false
  let lastSyncedQueueInfo: QueueInfoSnapshot = {
    Name: '',
    StartUpEnabled: false,
    TimeEnabled: false,
    CycleEnabled: false,
    AfterAccomplish: 'NoAction',
  }

  // 完成后操作选项
  const afterAccomplishOptions = [
    { label: '无操作', value: 'NoAction' },
    { label: '关机', value: 'Shutdown' },
    { label: '强制关机', value: 'ShutdownForce' },
    { label: '重启', value: 'Reboot' },
    { label: '休眠', value: 'Hibernate' },
    { label: '睡眠', value: 'Sleep' },
    { label: '退出软件', value: 'KillSelf' },
    { label: '注销此账户', value: 'Logoff' },
  ]

  const applyQueueInfo = (info: Record<string, any> | null | undefined, fallbackName = '') => {
    const next: QueueInfoSnapshot = {
      Name: info?.Name || fallbackName,
      StartUpEnabled: info?.StartUpEnabled ?? false,
      TimeEnabled: info?.TimeEnabled ?? false,
      CycleEnabled: info?.CycleEnabled ?? false,
      AfterAccomplish: info?.AfterAccomplish ?? 'NoAction',
    }

    currentQueueName.value = next.Name
    currentStartUpEnabled.value = next.StartUpEnabled
    currentTimeEnabled.value = next.TimeEnabled
    currentCycleEnabled.value = next.CycleEnabled
    currentAfterAccomplish.value = next.AfterAccomplish
    lastSyncedQueueInfo = { ...next }
  }

  const restoreQueueInfoField = (key: string) => {
    switch (key) {
      case 'Name':
        currentQueueName.value = lastSyncedQueueInfo.Name
        break
      case 'StartUpEnabled':
        currentStartUpEnabled.value = lastSyncedQueueInfo.StartUpEnabled
        break
      case 'TimeEnabled':
        currentTimeEnabled.value = lastSyncedQueueInfo.TimeEnabled
        break
      case 'CycleEnabled':
        currentCycleEnabled.value = lastSyncedQueueInfo.CycleEnabled
        break
      case 'AfterAccomplish':
        currentAfterAccomplish.value = lastSyncedQueueInfo.AfterAccomplish
        break
    }
  }

  // 获取队列列表
  const fetchQueues = async () => {
    loading.value = true
    try {
      const response = await Service.getQueuesApiQueueGetPost({})
      if (!isMounted) return
      if (response.code === 200) {
        if (response.index && response.index.length > 0) {
          queueList.value = response.index.map((item: any, index: number) => {
            try {
              const queueId = item.uid
              const queueName = response.data[queueId]?.Info?.Name || '新调度队列'
              return { id: queueId, name: queueName }
            } catch (itemError) {
              const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
              logger.warn(`解析队列项失败: ${errorMsg}`)
              return { id: `queue_${index}`, name: '新调度队列' }
            }
          })

          if (queueList.value.length > 0 && !activeQueueId.value) {
            activeQueueId.value = queueList.value[0].id
            nextTick(() => {
              loadQueueData(activeQueueId.value).catch(error => {
                const errorMsg = error instanceof Error ? error.message : String(error)
                logger.error(`加载队列数据失败: ${errorMsg}`)
              })
            })
          }
        } else {
          queueList.value = []
          currentQueueData.value = null
        }
      } else {
        const errorMsg = response instanceof Error ? response.message : String(response)
        logger.error(`API响应错误: ${errorMsg}`)
        queueList.value = []
        currentQueueData.value = null
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`获取队列列表失败: ${errorMsg}`)
      queueList.value = []
      currentQueueData.value = null
    } finally {
      loading.value = false
    }
  }

  // 加载队列数据
  const loadQueueData = async (queueId: string): Promise<boolean> => {
    if (!queueId) return false
    const generation = ++loadGeneration
    try {
      const response = await Service.getQueuesApiQueueGetPost({})
      if (!isMounted || generation !== loadGeneration || activeQueueId.value !== queueId)
        return false
      if (response.code !== 200 || !response.data?.[queueId]) {
        throw new Error(response.message || '队列数据不存在')
      }

      currentQueueData.value = response.data
      const queueData = response.data[queueId]
      const currentQueue = queueList.value.find(queue => queue.id === queueId)

      await nextTick()
      if (!isMounted) return false

      applyQueueInfo(queueData.Info, currentQueue?.name || '')
      if (currentQueue && currentQueueName.value) {
        currentQueue.name = currentQueueName.value
      }

      await new Promise(resolve => setTimeout(resolve, 50))
      if (!isMounted) return false

      try {
        await refreshTimeSets(queueId)
      } catch (timeError) {
        const errorMsg = timeError instanceof Error ? timeError.message : String(timeError)
        logger.error(`刷新定时项失败: ${errorMsg}`)
      }
      try {
        await refreshQueueItems(queueId)
      } catch (itemError) {
        const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
        logger.error(`刷新队列项失败: ${errorMsg}`)
      }
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载队列数据失败: ${errorMsg}`)
      return false
    }
  }

  // 刷新定时项
  const refreshTimeSets = async (requestedQueueId = activeQueueId.value) => {
    if (!requestedQueueId) {
      currentTimeSets.value = []
      return
    }
    const generation = ++timeSetGeneration
    try {
      const response = await Service.getTimeSetApiQueueTimeGetPost({
        queueId: requestedQueueId,
      })
      if (
        !isMounted ||
        generation !== timeSetGeneration ||
        activeQueueId.value !== requestedQueueId
      )
        return
      if (response.code !== 200) {
        logger.error(`获取定时项数据失败: ${JSON.stringify(response)}`)
        return
      }

      const timeSets: any[] = []
      if (response.index && Array.isArray(response.index)) {
        response.index.forEach((item: any) => {
          try {
            const timeSetId = item.uid
            if (!timeSetId || !response.data || !response.data[timeSetId]) return
            const timeSetData = response.data[timeSetId]
            if (timeSetData?.Info) {
              const originalTimeString = timeSetData.Info.Time || '00:00'
              const [hours = 0, minutes = 0] = originalTimeString.split(':').map(Number)
              const validHours = Math.max(0, Math.min(23, hours))
              const validMinutes = Math.max(0, Math.min(59, minutes))
              const timeString = `${validHours.toString().padStart(2, '0')}:${validMinutes.toString().padStart(2, '0')}`
              timeSets.push({
                id: timeSetId,
                time: timeString,
                enabled: Boolean(timeSetData.Info.Enabled),
                days: timeSetData.Info.Days || [],
              })
            }
          } catch (itemError) {
            const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
            logger.warn(`解析单个定时项失败: ${errorMsg}`)
          }
        })
      }

      await nextTick()
      if (!isMounted) return
      currentTimeSets.value.splice(0, currentTimeSets.value.length, ...timeSets)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`刷新定时项列表失败: ${errorMsg}`)
    }
  }

  // 刷新队列项
  const refreshQueueItems = async (requestedQueueId = activeQueueId.value) => {
    if (!requestedQueueId) return
    const generation = ++queueItemGeneration
    try {
      const response = await Service.getItemApiQueueItemGetPost({
        queueId: requestedQueueId,
      })
      if (
        !isMounted ||
        generation !== queueItemGeneration ||
        activeQueueId.value !== requestedQueueId
      )
        return
      if (response.code !== 200) {
        logger.error(`获取队列项数据失败: ${JSON.stringify(response)}`)
        return
      }

      const queueItems: QueueItemRecord[] = []
      if (response.index && Array.isArray(response.index)) {
        response.index.forEach((item: any) => {
          try {
            const queueItemId = item.uid
            if (!queueItemId || !response.data || !response.data[queueItemId]) return
            const queueItemData = response.data[queueItemId]
            if (queueItemData?.Info) {
              const info = queueItemData.Info
              const schedule = queueItemData.Schedule ?? {}
              const cycleData = queueItemData.Data ?? {}
              const item: QueueItemRecord = {
                id: queueItemId,
                script: info.ScriptId === '-' ? null : info.ScriptId || null,
                scheduleEnabled: schedule.Enabled ?? true,
                scheduleMode: schedule.Mode ?? 'fixed_time',
                scheduleDays: [...(schedule.Days ?? [])],
                scheduleTime: schedule.Time ?? '00:00',
                intervalMinutes: schedule.IntervalMinutes ?? 480,
                intervalAnchor: schedule.IntervalAnchor ?? 'start',
                nextRunAt: schedule.NextRunAt ?? '2000-01-01 00:00:00',
                lastCycleStartedAt: cycleData.LastCycleStartedAt ?? '2000-01-01 00:00:00',
                lastCycleFinishedAt: cycleData.LastCycleFinishedAt ?? '2000-01-01 00:00:00',
                cycleRunId: cycleData.CycleRunId ?? '',
                cycleState: normalizeCycleState(cycleData.CycleState),
                cycleRevision:
                  typeof cycleData.CycleRevision === 'number' &&
                  Number.isInteger(cycleData.CycleRevision)
                    ? cycleData.CycleRevision
                    : 0,
                cycleResult: cycleData.CycleResult ?? '',
                cycleError: cycleData.CycleError ?? '',
                cycleUpdatedAt: cycleData.CycleUpdatedAt ?? '2000-01-01 00:00:00',
              }
              queueItems.push(item)
            }
          } catch (itemError) {
            const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
            logger.warn(`解析单个队列项失败: ${errorMsg}`)
          }
        })
      }

      await nextTick()
      if (!isMounted) return
      currentQueueItems.value.splice(0, currentQueueItems.value.length, ...queueItems)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`刷新队列项列表失败: ${errorMsg}`)
    }
  }

  // 队列名称编辑
  const onQueueNameBlur = async (): Promise<boolean> => {
    if (!activeQueueId.value) return false
    const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
    const previousName = lastSyncedQueueInfo.Name || currentQueue?.name || ''
    const nextName =
      currentQueueName.value.trim() ||
      (currentQueue ? `队列 ${queueList.value.indexOf(currentQueue) + 1}` : '新队列')
    currentQueueName.value = nextName

    const success = await handleSaveChange('Name', nextName)
    if (!success) {
      currentQueueName.value = previousName
      if (currentQueue) currentQueue.name = previousName
    }
    return success
  }

  const startEditQueueName = () => {
    isEditingQueueName.value = true
    setTimeout(() => {
      const input = document.querySelector('.queue-title-input input') as HTMLInputElement
      if (input) {
        input.focus()
        input.select()
      }
    }, 100)
  }

  const finishEditQueueName = async () => {
    if (queueNameSavePending) return
    queueNameSavePending = true
    try {
      const success = await onQueueNameBlur()
      if (success) isEditingQueueName.value = false
    } finally {
      queueNameSavePending = false
    }
  }

  // 配置变更
  const handleConfigChange = async (key: string, value: any): Promise<boolean> => {
    const success = await handleSaveChange(key, value)
    if (!success) restoreQueueInfoField(key)
    return success
  }

  const rollbackCreatedQueue = async (queueId: string, reason: string): Promise<boolean> => {
    logger.error(`循环队列初始化失败，正在回滚新队列 ${queueId}: ${reason}`)
    let rollbackSucceeded = false
    try {
      const rollbackResponse = await Service.deleteQueueApiQueueDeletePost({ queueId })
      rollbackSucceeded = rollbackResponse.code === 200
      if (!rollbackSucceeded) {
        logger.error(`循环队列初始化回滚失败 ${queueId}: ${rollbackResponse.message || '未知错误'}`)
      }
    } catch (rollbackError) {
      const rollbackMessage =
        rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
      logger.error(`循环队列初始化回滚异常 ${queueId}: ${rollbackMessage}`)
    }

    await fetchQueues()
    return rollbackSucceeded
  }

  // 添加队列
  const handleAddQueue = async (cycleEnabled = false): Promise<boolean> => {
    try {
      const response = await Service.addQueueApiQueueAddPost()
      if (response.code === 200 && response.queueId) {
        if (cycleEnabled) {
          try {
            const configureResponse = await Service.updateQueueApiQueueUpdatePost({
              queueId: response.queueId,
              data: {
                Info: {
                  CycleEnabled: true,
                },
              },
            })
            if (configureResponse.code !== 200) {
              const reason = configureResponse.message || '未知错误'
              const rolledBack = await rollbackCreatedQueue(response.queueId, reason)
              message.error(
                rolledBack
                  ? `循环队列初始化失败，已回滚: ${reason}`
                  : `${reason}；半成品队列清理失败，请刷新后手动删除`
              )
              return false
            }
          } catch (configureError) {
            const reason =
              configureError instanceof Error ? configureError.message : String(configureError)
            const rolledBack = await rollbackCreatedQueue(response.queueId, reason)
            message.error(
              rolledBack
                ? `循环队列初始化失败，已回滚: ${reason}`
                : `循环队列初始化失败且半成品清理失败，请刷新后手动删除: ${reason}`
            )
            return false
          }
        }

        try {
          const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
          const { playSound } = useAudioPlayer()
          await playSound('add_queue')
        } catch (audioError) {
          const audioMessage = audioError instanceof Error ? audioError.message : String(audioError)
          logger.warn(`队列已创建，但创建提示音播放失败: ${audioMessage}`)
        }

        const defaultName = '新队列'
        const newQueue: QueueSummary = {
          id: response.queueId,
          name: defaultName,
        }
        queueList.value.push(newQueue)
        activeQueueId.value = newQueue.id
        currentQueueName.value = defaultName
        await loadQueueData(newQueue.id)
        message.success(
          `已创建${cycleEnabled ? '循环队列' : '普通队列'}，建议修改为更有意义的名称`,
          3
        )
        return true
      } else {
        message.error('队列创建失败: ' + (response.message || '未知错误'))
        return false
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`添加队列失败: ${errorMsg}`)
      message.error(`添加队列失败: ${errorMsg}`)
      return false
    }
  }

  // 删除队列
  const handleRemoveQueue = async (queueId: string) => {
    try {
      const response = await Service.deleteQueueApiQueueDeletePost({ queueId })
      if (response.code === 200) {
        const index = queueList.value.findIndex(queue => queue.id === queueId)
        if (index > -1) {
          queueList.value.splice(index, 1)
          if (activeQueueId.value === queueId) {
            activeQueueId.value = queueList.value[0]?.id || ''
            if (activeQueueId.value) {
              await loadQueueData(activeQueueId.value)
            } else {
              currentQueueData.value = null
            }
          }
        }
        message.success('队列删除成功')
        try {
          const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
          const { playSound } = useAudioPlayer()
          await playSound('delete_queue')
        } catch (audioError) {
          const audioMessage = audioError instanceof Error ? audioError.message : String(audioError)
          logger.warn(`队列已删除，但删除提示音播放失败: ${audioMessage}`)
        }
      } else {
        message.error('删除队列失败: ' + (response.message || '未知错误'))
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`删除队列失败: ${errorMsg}`)
      message.error(`删除队列失败: ${errorMsg}`)
    }
  }

  // 队列切换
  const onQueueChange = async (queueId: string) => {
    if (!queueId || queueId === activeQueueId.value) return
    const previousState = {
      activeQueueId: activeQueueId.value,
      currentQueueData: currentQueueData.value,
      currentQueueName: currentQueueName.value,
      currentStartUpEnabled: currentStartUpEnabled.value,
      currentTimeEnabled: currentTimeEnabled.value,
      currentCycleEnabled: currentCycleEnabled.value,
      currentAfterAccomplish: currentAfterAccomplish.value,
      currentTimeSets: [...currentTimeSets.value],
      currentQueueItems: [...currentQueueItems.value],
      lastSyncedQueueInfo: { ...lastSyncedQueueInfo },
    }
    try {
      ++loadGeneration
      ++timeSetGeneration
      ++queueItemGeneration
      activeQueueId.value = queueId
      currentTimeSets.value = []
      currentQueueItems.value = []
      const loaded = await loadQueueData(queueId)
      if (!loaded && activeQueueId.value === queueId) {
        throw new Error('无法加载所选队列')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`队列切换失败: ${errorMsg}`)
      if (activeQueueId.value === queueId) {
        activeQueueId.value = previousState.activeQueueId
        currentQueueData.value = previousState.currentQueueData
        currentQueueName.value = previousState.currentQueueName
        currentStartUpEnabled.value = previousState.currentStartUpEnabled
        currentTimeEnabled.value = previousState.currentTimeEnabled
        currentCycleEnabled.value = previousState.currentCycleEnabled
        currentAfterAccomplish.value = previousState.currentAfterAccomplish
        currentTimeSets.value = previousState.currentTimeSets
        currentQueueItems.value = previousState.currentQueueItems
        lastSyncedQueueInfo = previousState.lastSyncedQueueInfo
        message.error(`切换队列失败: ${errorMsg}`)
      }
    }
  }

  // 刷新队列配置
  const refreshQueueConfig = async () => {
    if (!activeQueueId.value) return
    const queueId = activeQueueId.value
    try {
      const response = await Service.getQueuesApiQueueGetPost({})
      if (!isMounted || activeQueueId.value !== queueId) return
      if (response.code === 200 && response.data && response.data[queueId]) {
        currentQueueData.value = response.data
        const queueData = response.data[queueId]
        if (queueData.Info) {
          applyQueueInfo(queueData.Info)

          const currentQueue = queueList.value.find(queue => queue.id === queueId)
          if (currentQueue) {
            currentQueue.name = queueData.Info.Name || currentQueue.name
          }
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`刷新队列配置失败: ${errorMsg}`)
    }
  }

  // 即时保存
  const handleSaveChange = async (key: string, value: any): Promise<boolean> => {
    if (!activeQueueId.value) return false
    try {
      const queueData: Record<string, any> = {
        Info: { [key]: value },
      }
      const response = await Service.updateQueueApiQueueUpdatePost({
        queueId: activeQueueId.value,
        data: queueData,
      })
      if (response.code !== 200) {
        message.error(response.message || '保存失败')
        return false
      }
      await refreshQueueConfig()
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存队列数据失败: ${errorMsg}`)
      message.error(`保存队列数据失败: ${errorMsg}`)
      return false
    }
  }

  // 初始化
  const initialize = async () => {
    try {
      await fetchQueues()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`初始化失败: ${errorMsg}`)
      loading.value = false
    }
  }

  // 拖拽重排序（供 QueueItemManager 使用）
  // 失败时通过刷新恢复原顺序（回滚语义）
  const reorderQueueItems = async (
    queueId: string,
    sortedIds: string[],
    onRollback: () => Promise<void>
  ): Promise<boolean> => {
    try {
      const response = await Service.reorderItemApiQueueItemOrderPost({
        queueId,
        indexList: sortedIds,
      })

      if (response.code === 200) {
        return true
      } else {
        logger.error(`队列项排序失败: ${response.message || '未知错误'}`)
        // 失败回滚：刷新数据恢复原顺序
        try {
          await onRollback()
        } catch (rollbackError) {
          const errorMsg =
            rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
          logger.error(`拖拽回滚刷新失败: ${errorMsg}`)
        }
        return false
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`队列项排序请求失败: ${errorMsg}`)
      // 异常回滚：刷新数据恢复原顺序
      try {
        await onRollback()
      } catch (rollbackError) {
        const rollbackMsg =
          rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
        logger.error(`拖拽异常回滚刷新失败: ${rollbackMsg}`)
      }
      return false
    }
  }

  const cleanup = () => {
    isMounted = false
    ++loadGeneration
    ++timeSetGeneration
    ++queueItemGeneration
  }

  return {
    // 状态
    queueList,
    activeQueueId,
    currentQueueData,
    currentQueueName,
    currentStartUpEnabled,
    currentTimeEnabled,
    currentCycleEnabled,
    currentAfterAccomplish,
    isEditingQueueName,
    currentTimeSets,
    currentQueueItems,
    loading,
    afterAccomplishOptions,

    // 操作
    fetchQueues,
    loadQueueData,
    refreshTimeSets,
    refreshQueueItems,
    startEditQueueName,
    finishEditQueueName,
    handleConfigChange,
    handleAddQueue,
    handleRemoveQueue,
    onQueueChange,
    refreshQueueConfig,
    handleSaveChange,

    // 拖拽重排序
    reorderQueueItems,

    // 生命周期
    initialize,
    cleanup,
  }
}
