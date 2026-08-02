import { computed, ref } from 'vue'
import axios from 'axios'
import { OpenAPI } from '@/api/core/OpenAPI'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import type { ScriptRecord } from '@/types/scriptRegistry'

const logger = window.electronAPI.getLogger('MaaFW项目管理')

const MANAGED_BASE_PATH = '/plugin/maafw-managed'

export const MAAFW_MANAGED_API_VERSION = 'maafw-managed.v1'

/**
 * Managed 0.2.x keeps the historical action paths. `capabilities`, `convert`,
 * and `progress` are additive host-UI contracts and deliberately live beside
 * those routes so the modal has one fail-closed gateway surface.
 */
export const MAAFW_MANAGED_ENDPOINTS = {
  capabilities: `${MANAGED_BASE_PATH}/capabilities`,
  convert: `${MANAGED_BASE_PATH}/convert`,
  progress: `${MANAGED_BASE_PATH}/progress`,
  projects: `${MANAGED_BASE_PATH}/projects/list`,
  versions: `${MANAGED_BASE_PATH}/versions/list`,
  importLocal: `${MANAGED_BASE_PATH}/import`,
  checkRemote: `${MANAGED_BASE_PATH}/remote/check`,
  importRemote: `${MANAGED_BASE_PATH}/remote/import`,
  upgradeLocal: `${MANAGED_BASE_PATH}/upgrade-local`,
  upgradeRemote: `${MANAGED_BASE_PATH}/remote/upgrade`,
  applyUpgrade: `${MANAGED_BASE_PATH}/upgrade-apply`,
  cancelUpgrade: `${MANAGED_BASE_PATH}/upgrade-cancel`,
  switchVersion: `${MANAGED_BASE_PATH}/switch`,
  deleteVersion: `${MANAGED_BASE_PATH}/delete`,
  installRuntime: `${MANAGED_BASE_PATH}/runtime/install`,
  runtimes: `${MANAGED_BASE_PATH}/runtime/list`,
  deleteRuntime: `${MANAGED_BASE_PATH}/runtime/delete`,
  pin: `${MANAGED_BASE_PATH}/pin`,
  garbageCollection: `${MANAGED_BASE_PATH}/gc`,
} as const

export const WS_MAAFW_MANAGED_PROGRESS = 'maafw.managed.progress'

export type MaaFWManagedOperation =
  | 'convert'
  | 'import-local'
  | 'import-remote'
  | 'upgrade-local'
  | 'upgrade-remote'
  | 'apply-upgrade'
  | 'cancel-upgrade'
  | 'switch-version'
  | 'install-runtime'
  | 'delete-version'
  | 'delete-runtime'
  | 'pin'
  | 'gc-preview'
  | 'gc-apply'

export type MaaFWManagedProgressStatus = 'idle' | 'running' | 'success' | 'error'

export interface MaaFWManagedFeatures {
  [key: string]: boolean | undefined
  singleEntry?: boolean
  inPlaceConversion: boolean
  conversionRecovery?: boolean
  projectOverview: boolean
  localImport: boolean
  remoteImport: boolean
  upgradePlans: boolean
  runtimeManagement: boolean
  operationProgress?: boolean
  pinning?: boolean
  garbageCollection?: boolean
}

export interface MaaFWManagedCapabilities {
  available: boolean
  unavailableReason: string
  apiVersion: string
  distributionVersion: string
  features: MaaFWManagedFeatures
  hostApis: Record<string, boolean>
}

export interface MaaFWManagedInventorySummary {
  files?: number
  directories?: number
  sizeBytes?: number
  size?: {
    inputBytes?: number
    sourceTreeBytes?: number
    projectedBytes?: number
    savedBytes?: number
    savedPercent?: number
  }
  taskCount?: number
  controllerCount?: number
  resourceCount?: number
  agentCount?: number
  [key: string]: unknown
}

export interface MaaFWManagedProjectSummary {
  projectId: string
  currentVersion: string | null
  versionCount: number
  versions: string[]
  versionSummaries?: Array<{
    version: string
    current: boolean
    summary?: MaaFWManagedInventorySummary | null
  }>
  summary?: MaaFWManagedInventorySummary | null
}

export interface MaaFWManagedProjectVersion {
  projectId: string
  version: string
  current?: boolean
  pinned?: boolean
  references?: string[]
  lastUsedAt?: string | null
  dataPath?: string
  manifestPath?: string
  projectInterfacePath?: string
  runtimeConstraint?: string | null
  summary?: MaaFWManagedInventorySummary | null
  manifest?: Record<string, unknown>
}

export interface MaaFWManagedRuntime {
  runtimeId: string
  path?: string
  environmentPath?: string
  venvPath?: string
  pythonExecutable?: string
  selectorRequirements?: string[]
  resolvedRequirements?: string[]
  packages?: string[]
  maafwRequirement?: string | null
  maafwVersion?: string | null
  pythonPatchVersion?: string | null
  sizeBytes?: number
  lastUsedAt?: string | null
  pinned?: boolean
  references?: string[]
  activeLeaseIds?: string[]
}

export interface MaaFWManagedUpgradeIssue {
  scope?: string
  recordId?: string
  name?: string
  message?: string
  action?: Record<string, unknown>
}

export interface MaaFWManagedUpgradePlan {
  schemaVersion?: number
  kind?: string
  planId: string
  state: string
  createdAt?: string
  scriptId?: string
  project?: {
    projectId?: string
    fromVersion?: string
    toVersion?: string
    fromHash?: string
    toHash?: string
  }
  planCount?: number
  userIds?: string[]
  errors?: MaaFWManagedUpgradeIssue[]
  warnings?: MaaFWManagedUpgradeIssue[]
  manualActions?: MaaFWManagedUpgradeIssue[]
  lossless?: boolean
  readyToApply: boolean
  confirmationToken: string
}

export interface MaaFWManagedBinding {
  scriptId: string
  scriptType: string
  managed: boolean
  projectId: string
  version: string
  runtimeConstraint: string
  runtimeId: string
  pinned: boolean
  status: string
  pendingPlan: MaaFWManagedUpgradePlan | null
}

export interface MaaFWManagedOverview {
  binding: MaaFWManagedBinding
  projects: MaaFWManagedProjectSummary[]
  runtimes: MaaFWManagedRuntime[]
}

export interface MaaFWManagedConversionResult {
  converted: boolean
  idempotent?: boolean
  scriptId: string
  fromType: string
  toType: string
  project?: MaaFWManagedProjectVersion
  userIds?: string[]
  recovered?: boolean
  host?: Record<string, unknown>
}

export interface MaaFWManagedUpgradeStageResult {
  updated?: boolean
  activated?: boolean
  currentVersion?: string | null
  latestVersion?: string | null
  sourcePath?: string
  previousProject?: MaaFWManagedProjectVersion
  project?: MaaFWManagedProjectVersion
  upgradePlan?: MaaFWManagedUpgradePlan
  upgradePlanError?: string
  download?: Record<string, unknown>
}

export interface MaaFWManagedRemoteDiscovery {
  mode?: 'initial' | 'upgrade' | string
  currentVersion?: string
  latestVersion?: string
  updateAvailable?: boolean
  installable?: boolean
  candidate?: Record<string, unknown> | null
  unavailableReason?: string
  message?: string
}

export interface MaaFWManagedGarbageCollectionResult {
  dryRun: boolean
  projectReferenceReconciliation?: Record<string, unknown> | null
  projectStore?: Record<string, unknown>
  referenceReconciliation?: Record<string, unknown> | null
  runtimePool?: Record<string, unknown>
}

export interface MaaFWManagedProgress {
  operationId: string
  operation: MaaFWManagedOperation | ''
  status: MaaFWManagedProgressStatus
  stage: string
  message: string
  percent: number | null
  downloadedBytes: number | null
  totalBytes: number | null
  logs: string[]
}

export interface MaaFWManagedLocalSourceInput {
  scriptId: string
  projectId: string
  version?: string
  runtimeConstraint?: string
  sourcePath?: string
  sourceArchive?: string
}

export interface MaaFWManagedRemoteSourceInput {
  scriptId: string
  projectId: string
  runtimeConstraint?: string
  source: 'MirrorChyan' | 'GitHub'
  channel?: string
  mirrorChyanRid?: string
  mirrorChyanCDK?: string
  githubRepo?: string
  githubTag?: string
  githubAssetPattern?: string
}

interface PluginEnvelope<T> {
  code: number
  status: string
  message?: string
  data?: T | null
}

const EMPTY_FEATURES: MaaFWManagedFeatures = {
  singleEntry: false,
  inPlaceConversion: false,
  conversionRecovery: false,
  projectOverview: false,
  localImport: false,
  remoteImport: false,
  upgradePlans: false,
  runtimeManagement: false,
  operationProgress: false,
  pinning: false,
  garbageCollection: false,
}

const EMPTY_PROGRESS: MaaFWManagedProgress = {
  operationId: '',
  operation: '',
  status: 'idle',
  stage: '',
  message: '',
  percent: null,
  downloadedBytes: null,
  totalBytes: null,
  logs: [],
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

const asString = (value: unknown) => (typeof value === 'string' ? value : '')

const asStringArray = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []

const asNumber = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

const hasOwn = (value: object, key: PropertyKey) => Object.prototype.hasOwnProperty.call(value, key)

const parseJsonRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value !== 'string') return asRecord(value)
  try {
    return asRecord(JSON.parse(value))
  } catch {
    return {}
  }
}

const normalizeCapabilities = (
  raw: Partial<Omit<MaaFWManagedCapabilities, 'available' | 'unavailableReason'>>
): MaaFWManagedCapabilities => {
  const apiVersion = asString(raw.apiVersion)
  if (apiVersion !== MAAFW_MANAGED_API_VERSION) {
    throw new Error(
      apiVersion ? `不支持的 MaaFW 托管接口版本：${apiVersion}` : 'MaaFW 托管能力响应缺少接口版本'
    )
  }
  const rawFeatures = asRecord(raw.features)
  const booleanFeatures = Object.fromEntries(
    Object.entries(rawFeatures).filter((entry): entry is [string, boolean] => {
      return typeof entry[1] === 'boolean'
    })
  )
  return {
    available: true,
    unavailableReason: '',
    apiVersion,
    distributionVersion: asString(raw.distributionVersion),
    features: {
      ...EMPTY_FEATURES,
      ...booleanFeatures,
    },
    hostApis: Object.fromEntries(
      Object.entries(asRecord((raw as { hostApis?: unknown }).hostApis)).map(([key, value]) => [
        key,
        value === true,
      ])
    ),
  }
}

export const readMaaFWManagedBinding = (record: ScriptRecord): MaaFWManagedBinding => {
  const config = asRecord(record.config)
  const managed = asRecord(config.Managed)
  const managedRuntime = asRecord(config.ManagedRuntime)
  const publicPlan = parseJsonRecord(managed.UpgradePlan)
  const durablePlan = parseJsonRecord(managed.PendingUpgrade)
  const durablePlanId = asString(durablePlan.planId)
  const pendingPlanId = asString(managed.PendingPlanId)
  const plan = durablePlanId ? durablePlan : pendingPlanId ? publicPlan : {}
  const project = asRecord(plan.project)
  const planId = durablePlanId || pendingPlanId
  const confirmationToken = asString(plan.confirmationToken) || asString(managed.UpgradeToken)

  return {
    scriptId: record.id,
    scriptType: record.type,
    managed: record.type === 'MaaFWManaged',
    projectId: asString(managed.ProjectId),
    version: asString(managed.Version),
    runtimeConstraint: asString(managed.RuntimeConstraint),
    runtimeId: asString(managedRuntime.RuntimeId),
    pinned: Boolean(managed.Pinned ?? managedRuntime.Pinned),
    status: asString(managed.Status),
    pendingPlan: planId
      ? ({
          ...plan,
          planId,
          state: asString(plan.state) || 'ready',
          project,
          readyToApply: plan.readyToApply === true,
          confirmationToken,
        } as MaaFWManagedUpgradePlan)
      : null,
  }
}

const pluginErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError<PluginEnvelope<unknown>>(error)) {
    const body = error.response?.data
    if (typeof body?.message === 'string' && body.message) return body.message
    const detail = asRecord(error.response?.data).detail
    if (typeof detail === 'string' && detail) return detail
  }
  return error instanceof Error && error.message ? error.message : fallback
}

let operationCounter = 0

export function useMaaFWManagedApi() {
  const registryApi = useScriptRegistryApi()
  const pendingCount = ref(0)
  const error = ref<string | null>(null)
  const capabilities = ref<MaaFWManagedCapabilities | null>(null)
  const progress = ref<MaaFWManagedProgress>({ ...EMPTY_PROGRESS })
  const loading = computed(() => pendingCount.value > 0)

  let pollTimer: number | null = null
  let progressGeneration = 0
  const progressSubscriptions = new Set<string>()

  const request = async <T>(
    path: string,
    payload: Record<string, unknown>,
    progressId?: string
  ): Promise<T> => {
    try {
      const progressEnabled = capabilities.value?.features.operationProgress === true
      const requestPayload = progressEnabled
        ? payload
        : Object.fromEntries(Object.entries(payload).filter(([key]) => key !== 'progressId'))
      const response = await axios.post<PluginEnvelope<T>>(
        `${OpenAPI.BASE}${path}`,
        requestPayload,
        {
          headers:
            progressEnabled && progressId ? { 'X-MaaFW-Progress-Id': progressId } : undefined,
        }
      )
      const body = response.data
      if (body.code !== 200 || body.data === null || body.data === undefined) {
        throw new Error(body.message || 'MaaFW 托管资源操作失败')
      }
      return body.data
    } catch (caught) {
      throw new Error(pluginErrorMessage(caught, 'MaaFW 托管资源操作失败'))
    }
  }

  const run = async <T>(operation: () => Promise<T>): Promise<T> => {
    pendingCount.value += 1
    error.value = null
    try {
      return await operation()
    } catch (caught) {
      const reason = pluginErrorMessage(caught, 'MaaFW 托管资源操作失败')
      error.value = reason
      logger.error(reason)
      throw new Error(reason)
    } finally {
      pendingCount.value -= 1
    }
  }

  const updateProgress = (raw: Record<string, unknown>) => {
    const operationId = asString(raw.operationId) || asString(raw.progressId)
    if (operationId && operationId !== progress.value.operationId) return

    const rawStatus = asString(raw.status).toLowerCase()
    const nextStatus: MaaFWManagedProgressStatus =
      rawStatus === 'completed' || rawStatus === 'success'
        ? 'success'
        : rawStatus === 'failed' || rawStatus === 'error'
          ? 'error'
          : 'running'
    const currentStatus = progress.value.status
    if (
      (currentStatus === 'success' || currentStatus === 'error') &&
      nextStatus !== currentStatus
    ) {
      return
    }
    const hasPercent = hasOwn(raw, 'percent')
    const hasDownloadedBytes = hasOwn(raw, 'downloadedBytes') || hasOwn(raw, 'downloaded_bytes')
    const hasTotalBytes = hasOwn(raw, 'totalBytes') || hasOwn(raw, 'total_bytes')
    progress.value = {
      ...progress.value,
      status: nextStatus,
      stage: asString(raw.stage) || progress.value.stage,
      message: asString(raw.message) || progress.value.message,
      percent: hasPercent ? asNumber(raw.percent) : progress.value.percent,
      downloadedBytes: hasDownloadedBytes
        ? asNumber(raw.downloadedBytes ?? raw.downloaded_bytes)
        : progress.value.downloadedBytes,
      totalBytes: hasTotalBytes
        ? asNumber(raw.totalBytes ?? raw.total_bytes)
        : progress.value.totalBytes,
      logs: hasOwn(raw, 'logs') ? asStringArray(raw.logs) : progress.value.logs,
    }
  }

  const stopProgressTracking = () => {
    progressGeneration += 1
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
    progressSubscriptions.forEach(subscriptionId => unsubscribe(subscriptionId))
    progressSubscriptions.clear()
  }

  const pollProgress = async (scriptId: string, operationId: string, generation: number) => {
    try {
      const data = await request<Record<string, unknown>>(MAAFW_MANAGED_ENDPOINTS.progress, {
        scriptId,
        operationId,
      })
      if (generation !== progressGeneration || operationId !== progress.value.operationId) {
        return
      }
      updateProgress(data)
    } catch {
      if (generation === progressGeneration && pollTimer !== null) {
        window.clearInterval(pollTimer)
        pollTimer = null
      }
    }
  }

  const beginProgressTracking = (
    scriptId: string,
    operation: MaaFWManagedOperation,
    message: string
  ) => {
    stopProgressTracking()
    const generation = progressGeneration
    const operationId = `${scriptId}:${operation}:${Date.now()}:${++operationCounter}`
    progress.value = {
      operationId,
      operation,
      status: 'running',
      stage: message,
      message,
      percent: null,
      downloadedBytes: null,
      totalBytes: null,
      logs: [],
    }
    const handler = (wsMessage: { data: unknown }) => updateProgress(asRecord(wsMessage.data))
    progressSubscriptions.add(subscribe({ id: scriptId, type: WS_MAAFW_MANAGED_PROGRESS }, handler))
    progressSubscriptions.add(
      subscribe({ id: operationId, type: WS_MAAFW_MANAGED_PROGRESS }, handler)
    )
    if (capabilities.value?.features.operationProgress) {
      pollTimer = window.setInterval(() => {
        void pollProgress(scriptId, operationId, generation)
      }, 1000)
    }
    return operationId
  }

  const tracked = async <T>(
    scriptId: string,
    operation: MaaFWManagedOperation,
    message: string,
    action: (progressId: string) => Promise<T>
  ) => {
    const progressId = beginProgressTracking(scriptId, operation, message)
    try {
      const result = await action(progressId)
      if (progress.value.status === 'running') {
        progress.value = {
          ...progress.value,
          status: 'success',
          stage: '操作完成',
          message: '操作已完成',
          percent: 100,
        }
      }
      return result
    } catch (caught) {
      const reason = pluginErrorMessage(caught, 'MaaFW 托管资源操作失败')
      progress.value = {
        ...progress.value,
        status: 'error',
        stage: '操作失败',
        message: reason,
      }
      throw caught
    } finally {
      stopProgressTracking()
    }
  }

  const getCapabilities = async (): Promise<MaaFWManagedCapabilities> => {
    try {
      const data = await request<
        Partial<Omit<MaaFWManagedCapabilities, 'available' | 'unavailableReason'>>
      >(MAAFW_MANAGED_ENDPOINTS.capabilities, {})
      capabilities.value = normalizeCapabilities(data)
    } catch (caught) {
      capabilities.value = {
        available: false,
        unavailableReason: pluginErrorMessage(caught, '当前未提供 MaaFW 托管资源服务'),
        apiVersion: '',
        distributionVersion: '',
        features: { ...EMPTY_FEATURES },
        hostApis: {},
      }
    }
    return capabilities.value
  }

  const getCurrentBinding = async (scriptId: string): Promise<MaaFWManagedBinding> =>
    run(async () => {
      const records = await registryApi.getScripts(scriptId)
      if (records.length !== 1) throw new Error(`无法唯一读取脚本 ${scriptId}`)
      return readMaaFWManagedBinding(records[0])
    })

  const listProjects = (scriptId: string) =>
    run(() => request<MaaFWManagedProjectSummary[]>(MAAFW_MANAGED_ENDPOINTS.projects, { scriptId }))

  const listVersions = (scriptId: string, projectId: string) =>
    run(() =>
      request<MaaFWManagedProjectVersion[]>(MAAFW_MANAGED_ENDPOINTS.versions, {
        scriptId,
        projectId,
      })
    )

  const listRuntimes = (scriptId: string) =>
    run(() => request<MaaFWManagedRuntime[]>(MAAFW_MANAGED_ENDPOINTS.runtimes, { scriptId }))

  const getOverview = async (scriptId: string): Promise<MaaFWManagedOverview> => {
    const binding = await getCurrentBinding(scriptId)
    if (!binding.managed || capabilities.value?.features.projectOverview === false) {
      return { binding, projects: [], runtimes: [] }
    }
    const [projects, runtimes] = await Promise.all([
      listProjects(scriptId),
      capabilities.value?.features.runtimeManagement ? listRuntimes(scriptId) : Promise.resolve([]),
    ])
    return { binding, projects, runtimes }
  }

  const convert = (input: {
    scriptId: string
    projectId?: string
    version?: string
    runtimeConstraint?: string
  }) =>
    run(() =>
      tracked(input.scriptId, 'convert', '正在转换为托管项目', progressId =>
        request<MaaFWManagedConversionResult>(
          MAAFW_MANAGED_ENDPOINTS.convert,
          { ...input, progressId },
          progressId
        )
      )
    )

  const importLocal = (input: MaaFWManagedLocalSourceInput) =>
    run(() =>
      tracked(input.scriptId, 'import-local', '正在导入本地项目资源', progressId =>
        request<MaaFWManagedProjectVersion>(
          MAAFW_MANAGED_ENDPOINTS.importLocal,
          { ...input, progressId },
          progressId
        )
      )
    )

  const upgradeLocal = (input: MaaFWManagedLocalSourceInput) =>
    run(() =>
      tracked(input.scriptId, 'upgrade-local', '正在导入资源并生成升级计划', progressId =>
        request<MaaFWManagedUpgradeStageResult>(
          MAAFW_MANAGED_ENDPOINTS.upgradeLocal,
          { ...input, progressId },
          progressId
        )
      )
    )

  const checkRemote = (input: MaaFWManagedRemoteSourceInput) =>
    run(() =>
      request<MaaFWManagedRemoteDiscovery>(MAAFW_MANAGED_ENDPOINTS.checkRemote, { ...input })
    )

  const importRemote = (input: MaaFWManagedRemoteSourceInput) =>
    run(() =>
      tracked(input.scriptId, 'import-remote', '正在下载并导入远程资源', progressId =>
        request<MaaFWManagedUpgradeStageResult>(
          MAAFW_MANAGED_ENDPOINTS.importRemote,
          { ...input, progressId },
          progressId
        )
      )
    )

  const upgradeRemote = (input: MaaFWManagedRemoteSourceInput) =>
    run(() =>
      tracked(input.scriptId, 'upgrade-remote', '正在下载资源并生成升级计划', progressId =>
        request<MaaFWManagedUpgradeStageResult>(
          MAAFW_MANAGED_ENDPOINTS.upgradeRemote,
          { ...input, progressId },
          progressId
        )
      )
    )

  const switchVersion = (scriptId: string, projectId: string, version: string) =>
    run(() =>
      tracked(scriptId, 'switch-version', '正在生成版本切换计划', progressId =>
        request<MaaFWManagedUpgradeStageResult>(
          MAAFW_MANAGED_ENDPOINTS.switchVersion,
          { scriptId, projectId, version, progressId },
          progressId
        )
      )
    )

  const applyUpgrade = (scriptId: string, planId: string, confirmation: string) =>
    run(() =>
      tracked(scriptId, 'apply-upgrade', '正在校验并应用升级计划', progressId =>
        request<Record<string, unknown>>(
          MAAFW_MANAGED_ENDPOINTS.applyUpgrade,
          { scriptId, planId, confirmation, progressId },
          progressId
        )
      )
    )

  const cancelUpgrade = (scriptId: string) =>
    run(() =>
      tracked(scriptId, 'cancel-upgrade', '正在取消待确认升级', progressId =>
        request<Record<string, unknown>>(
          MAAFW_MANAGED_ENDPOINTS.cancelUpgrade,
          { scriptId, progressId },
          progressId
        )
      )
    )

  const installRuntime = (
    scriptId: string,
    projectId: string,
    version: string,
    runtimeConstraint?: string
  ) =>
    run(() =>
      tracked(scriptId, 'install-runtime', '正在安装或复用共享运行时', progressId =>
        request<Record<string, unknown>>(
          MAAFW_MANAGED_ENDPOINTS.installRuntime,
          { scriptId, projectId, version, runtimeConstraint, progressId },
          progressId
        )
      )
    )

  const deleteVersion = (scriptId: string, projectId: string, version: string) =>
    run(() =>
      tracked(scriptId, 'delete-version', '正在删除项目版本', progressId =>
        request<Record<string, unknown>>(
          MAAFW_MANAGED_ENDPOINTS.deleteVersion,
          {
            scriptId,
            projectId,
            version,
            confirmation: `${projectId}@${version}`,
            progressId,
          },
          progressId
        )
      )
    )

  const deleteRuntime = (scriptId: string, runtimeId: string) =>
    run(() =>
      tracked(scriptId, 'delete-runtime', '正在删除共享运行时', progressId =>
        request<Record<string, unknown>>(
          MAAFW_MANAGED_ENDPOINTS.deleteRuntime,
          { scriptId, runtimeId, confirmation: runtimeId, progressId },
          progressId
        )
      )
    )

  const pin = (
    scriptId: string,
    pinned: boolean,
    target: { projectId?: string; version?: string; runtimeId?: string }
  ) =>
    run(() =>
      tracked(scriptId, 'pin', pinned ? '正在固定资源' : '正在取消固定', progressId =>
        request<Record<string, unknown>>(
          MAAFW_MANAGED_ENDPOINTS.pin,
          { scriptId, pinned, ...target, progressId },
          progressId
        )
      )
    )

  const collectGarbage = (
    scriptId: string,
    input: {
      dryRun: boolean
      projectId?: string
      graceDays: number
      keepLatest: number
    }
  ) => {
    const operation: MaaFWManagedOperation = input.dryRun ? 'gc-preview' : 'gc-apply'
    return run(() =>
      tracked(
        scriptId,
        operation,
        input.dryRun ? '正在预览空间回收' : '正在回收过期资源',
        progressId =>
          request<MaaFWManagedGarbageCollectionResult>(
            MAAFW_MANAGED_ENDPOINTS.garbageCollection,
            {
              scriptId,
              ...input,
              confirmation: input.dryRun ? undefined : 'DELETE UNUSED',
              progressId,
            },
            progressId
          )
      )
    )
  }

  const resetProgress = () => {
    if (progress.value.status === 'running') return
    progress.value = { ...EMPTY_PROGRESS }
  }

  const dispose = () => stopProgressTracking()

  return {
    loading,
    error,
    capabilities,
    progress,
    getCapabilities,
    getCurrentBinding,
    getOverview,
    listProjects,
    listVersions,
    listRuntimes,
    convert,
    importLocal,
    upgradeLocal,
    checkRemote,
    importRemote,
    upgradeRemote,
    switchVersion,
    applyUpgrade,
    cancelUpgrade,
    installRuntime,
    deleteVersion,
    deleteRuntime,
    pin,
    collectGarbage,
    resetProgress,
    dispose,
  }
}
