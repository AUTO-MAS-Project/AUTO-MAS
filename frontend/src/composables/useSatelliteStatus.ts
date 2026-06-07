import { Service } from '@/api'
import { satelliteModules } from '@/composables/satellite-config'
import type { ScriptType } from '@/types/script'

export interface SatelliteModuleStatus {
  queued: boolean
  running: boolean
  errorVisible: boolean
}

const SCHEDULER_TABS_KEY = 'scheduler-tabs-session'
const PENDING_TABS_KEY = 'scheduler-pending-tabs'
const supportedSatelliteTypes = new Set<ScriptType>(
  satelliteModules.map(module => module.scriptType)
)

interface SchedulerTabSnapshot {
  status?: string
  selectedTaskId?: string | null
  taskQueue?: Array<{ status?: string }>
  overviewData?: Array<{
    script_id?: string
    status?: string
    user_list?: Array<{ status?: string }>
    userList?: Array<{ status?: string }>
  }>
}

type OverviewItemSnapshot = NonNullable<SchedulerTabSnapshot['overviewData']>[number]

interface ScriptSummary {
  uid: string
  type: ScriptType
}

const createEmptyStatuses = () => {
  const statuses = new Map<ScriptType, SatelliteModuleStatus>()
  satelliteModules.forEach(module => {
    statuses.set(module.scriptType, {
      queued: false,
      running: false,
      errorVisible: false,
    })
  })
  return statuses
}

const getSupportedScriptType = (type: string): ScriptType | null => {
  const scriptType = type as ScriptType
  return supportedSatelliteTypes.has(scriptType) ? scriptType : null
}

const getScriptTypeFromConfigType = (type: string): ScriptType | null => {
  const typeMap: Record<string, ScriptType> = {
    MaaConfig: 'MAA',
    SrcConfig: 'SRC',
    OkwwConfig: 'Okww',
    MaaEndConfig: 'MaaEnd',
    M9AConfig: 'M9A',
    GeneralConfig: 'General',
  }

  return getSupportedScriptType(typeMap[type] ?? '')
}

const readSchedulerTabsSnapshot = (): SchedulerTabSnapshot[] => {
  try {
    const rawTabs = sessionStorage.getItem(SCHEDULER_TABS_KEY)
    if (!rawTabs) return []
    const parsed = JSON.parse(rawTabs)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const readPendingQueueIds = () => {
  const queueIds = new Set<string>()

  try {
    const rawTabs = localStorage.getItem(PENDING_TABS_KEY)
    if (!rawTabs) return queueIds

    const parsed = JSON.parse(rawTabs)
    if (!Array.isArray(parsed)) return queueIds

    parsed.forEach(item => {
      const queueId = typeof item === 'object' && item !== null ? item.queueId : null
      if (queueId) {
        queueIds.add(String(queueId))
      }
    })
  } catch {
    return queueIds
  }

  return queueIds
}

const isRunningStatus = (status?: string) => {
  return Boolean(status && /运行|进行|执行/.test(status))
}

const isErrorStatus = (status?: string) => {
  return Boolean(status && /异常|失败|错误|ERROR|Error|error/.test(status))
}

const isTabRunning = (status?: string) => {
  return status === '运行' || isRunningStatus(status)
}

const addTypeForScriptId = (
  target: Set<ScriptType>,
  scriptId: string | null | undefined,
  scriptTypeById: Map<string, ScriptType>
) => {
  if (!scriptId) return
  const type = scriptTypeById.get(scriptId)
  if (type) {
    target.add(type)
  }
}

const addTypeForOverviewItem = (
  target: Set<ScriptType>,
  item: OverviewItemSnapshot,
  index: number,
  selectedTaskId: string | null | undefined,
  queueScriptIds: string[] | undefined,
  scriptTypeById: Map<string, ScriptType>
) => {
  addTypeForScriptId(target, item.script_id, scriptTypeById)
  addTypeForScriptId(target, queueScriptIds?.[index], scriptTypeById)

  if (!queueScriptIds?.length) {
    addTypeForScriptId(target, selectedTaskId, scriptTypeById)
  }
}

const hasErrorUser = (item: OverviewItemSnapshot) => {
  const users = Array.isArray(item.user_list)
    ? item.user_list
    : Array.isArray(item.userList)
      ? item.userList
      : []

  return users.some(user => isErrorStatus(user.status))
}

async function getQueuedScriptIds() {
  const queuedScriptIds = new Set<string>()
  const queueScriptIdsByQueueId = new Map<string, string[]>()
  const queueIds = readPendingQueueIds()

  const queueResponse = await Service.getQueuesApiQueueGetPost({})
  if (queueResponse.code !== 200) {
    return { queuedScriptIds, queueScriptIdsByQueueId }
  }

  for (const queueIndex of queueResponse.index) {
    queueIds.add(queueIndex.uid)
  }

  for (const queueId of queueIds) {
    const queueItemsResponse = await Service.getItemApiQueueItemGetPost({
      queueId,
    })

    if (queueItemsResponse.code !== 200) {
      continue
    }

    const queueScriptIds: string[] = []
    for (const itemIndex of queueItemsResponse.index) {
      const scriptId = queueItemsResponse.data[itemIndex.uid]?.Info?.ScriptId
      if (!scriptId || scriptId === '-') {
        continue
      }
      queuedScriptIds.add(scriptId)
      queueScriptIds.push(scriptId)
    }
    queueScriptIdsByQueueId.set(queueId, queueScriptIds)
  }

  return { queuedScriptIds, queueScriptIdsByQueueId }
}

async function getScriptSummaries(): Promise<ScriptSummary[]> {
  const response = await Service.getScriptApiScriptsGetPost({})
  if (response.code !== 200) {
    return []
  }

  return response.index
    .map(item => {
      const type = getScriptTypeFromConfigType(item.type)
      return type ? { uid: item.uid, type } : null
    })
    .filter((item): item is ScriptSummary => item !== null)
}

const getRunningTypesFromSchedulerTabs = (
  scriptTypeById: Map<string, ScriptType>,
  queueScriptIdsByQueueId: Map<string, string[]>
) => {
  const runningTypes = new Set<ScriptType>()
  const tabs = readSchedulerTabsSnapshot().filter(tab => isTabRunning(tab.status))

  tabs.forEach(tab => {
    addTypeForScriptId(runningTypes, tab.selectedTaskId, scriptTypeById)

    const queueScriptIds = tab.selectedTaskId
      ? queueScriptIdsByQueueId.get(tab.selectedTaskId)
      : undefined

    const overviewData = Array.isArray(tab.overviewData) ? tab.overviewData : []
    overviewData.forEach((item, index) => {
      if (!isRunningStatus(item.status)) return
      addTypeForOverviewItem(
        runningTypes,
        item,
        index,
        tab.selectedTaskId,
        queueScriptIds,
        scriptTypeById
      )
    })

    if (overviewData.length > 0) {
      return
    }

    if (!queueScriptIds?.length) {
      return
    }

    const taskQueue = Array.isArray(tab.taskQueue) ? tab.taskQueue : []
    taskQueue.forEach((item, index) => {
      if (isRunningStatus(item.status)) {
        addTypeForScriptId(runningTypes, queueScriptIds[index], scriptTypeById)
      }
    })
  })

  return runningTypes
}

const getErrorTypesFromSchedulerTabs = (
  scriptTypeById: Map<string, ScriptType>,
  queueScriptIdsByQueueId: Map<string, string[]>
) => {
  const errorTypes = new Set<ScriptType>()
  const tabs = readSchedulerTabsSnapshot()

  tabs.forEach(tab => {
    if (isErrorStatus(tab.status)) {
      addTypeForScriptId(errorTypes, tab.selectedTaskId, scriptTypeById)
    }

    const queueScriptIds = tab.selectedTaskId
      ? queueScriptIdsByQueueId.get(tab.selectedTaskId)
      : undefined

    const overviewData = Array.isArray(tab.overviewData) ? tab.overviewData : []
    overviewData.forEach((item, index) => {
      if (!isErrorStatus(item.status) && !hasErrorUser(item)) return
      addTypeForOverviewItem(
        errorTypes,
        item,
        index,
        tab.selectedTaskId,
        queueScriptIds,
        scriptTypeById
      )
    })

    if (overviewData.length > 0) {
      return
    }

    if (!queueScriptIds?.length) {
      return
    }

    const taskQueue = Array.isArray(tab.taskQueue) ? tab.taskQueue : []
    taskQueue.forEach((item, index) => {
      if (isErrorStatus(item.status)) {
        addTypeForScriptId(errorTypes, queueScriptIds[index], scriptTypeById)
      }
    })
  })

  return errorTypes
}

export async function getSatelliteModuleStatuses() {
  const statuses = createEmptyStatuses()

  const scripts = await getScriptSummaries()
  const scriptTypeById = new Map<string, ScriptType>()

  scripts.forEach(script => {
    scriptTypeById.set(script.uid, script.type)
  })

  const { queuedScriptIds, queueScriptIdsByQueueId } = await getQueuedScriptIds()
  queuedScriptIds.forEach(scriptId => {
    const type = scriptTypeById.get(scriptId)
    if (type) {
      const status = statuses.get(type)
      if (status) status.queued = true
    }
  })

  getRunningTypesFromSchedulerTabs(scriptTypeById, queueScriptIdsByQueueId).forEach(type => {
    const status = statuses.get(type)
    if (status) status.running = true
  })

  getErrorTypesFromSchedulerTabs(scriptTypeById, queueScriptIdsByQueueId).forEach(type => {
    const status = statuses.get(type)
    if (status) status.errorVisible = true
  })

  return statuses
}
