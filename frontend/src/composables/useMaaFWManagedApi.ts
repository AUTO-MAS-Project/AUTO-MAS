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
  activeOperation: `${MANAGED_BASE_PATH}/operations/active`,
  inventory: `${MANAGED_BASE_PATH}/inventory`,
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
  | 'remote-check'
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

export type MaaFWManagedProgressStatus = 'idle' | 'running' | 'success' | 'error' | 'unknown'

const MAAFW_MANAGED_OPERATIONS: readonly MaaFWManagedOperation[] = [
  'convert',
  'import-local',
  'import-remote',
  'remote-check',
  'upgrade-local',
  'upgrade-remote',
  'apply-upgrade',
  'cancel-upgrade',
  'switch-version',
  'install-runtime',
  'delete-version',
  'delete-runtime',
  'pin',
  'gc-preview',
  'gc-apply',
]

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
  activeOperationLookup?: boolean
  serverMutationExclusion?: boolean
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
  activeLeaseIds?: string[]
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
  poolId?: string
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

export interface MaaFWManagedStorageInfo {
  available: boolean
  reason?: string
  root?: string
  storeId?: string
  runRoot?: string
  runRootId?: string
  poolId?: string
  isDefault?: boolean
  isDefaultRunRoot?: boolean
  rootIdentity?: Record<string, unknown>
  runRootIdentity?: Record<string, unknown>
}

export interface MaaFWManagedCheckout {
  checkoutId: string
  dataPath: string
  storeId: string
  runRootId: string
  projectId: string
  version: string
  sourceHash: string
  payloadHash?: string
  scriptId: string
  storeAvailable: boolean
  scriptAvailable?: boolean
  bindingCurrent?: boolean
  orphanReason?: string | null
  createdAt?: string | null
  lastUsedAt?: string | null
  leaseProtectionAvailable?: boolean
  activeLeaseIds?: string[]
}

export interface MaaFWManagedInventoryError {
  scope?: string
  path?: string
  scriptId?: string
  runtimeId?: string
  error: string
}

export interface MaaFWManagedReferenceReconciliation<T> {
  scriptCount?: number
  runtimeCount?: number
  updated?: T[]
}

export interface MaaFWManagedGlobalInventory {
  complete: boolean
  generatedAt: string
  storage: {
    projectStore: MaaFWManagedStorageInfo
    runtimePool: MaaFWManagedStorageInfo
  }
  projects: MaaFWManagedProjectSummary[]
  versions: MaaFWManagedProjectVersion[]
  checkouts: MaaFWManagedCheckout[]
  runtimes: MaaFWManagedRuntime[]
  references: {
    scripts: MaaFWManagedReferenceReconciliation<MaaFWManagedProjectVersion>
    runtimes: MaaFWManagedReferenceReconciliation<MaaFWManagedRuntime>
  }
  errors: MaaFWManagedInventoryError[]
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
  scriptId?: string
  serverEpoch?: string
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

export interface MaaFWManagedActiveOperationLookup {
  scriptId: string
  serverEpoch: string
  activeOperation: MaaFWManagedProgress | null
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
  activeOperationLookup: false,
  serverMutationExclusion: false,
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

const ACTIVE_OPERATION_STORAGE_PREFIX = 'auto-mas:maafw-managed:active-operation:'
const PROGRESS_ID_PATTERN = /^[A-Za-z0-9._:-]{1,200}$/

interface MaaFWManagedActiveOperationRef {
  v: 1
  scriptId: string
  operationId: string
  operation: MaaFWManagedOperation
  startedAt: string
  apiVersion: string
  distributionVersion: string
}

const asManagedOperation = (value: unknown): MaaFWManagedOperation | '' =>
  typeof value === 'string' && MAAFW_MANAGED_OPERATIONS.includes(value as MaaFWManagedOperation)
    ? (value as MaaFWManagedOperation)
    : ''

const activeOperationStorageKey = (scriptId: string) =>
  `${ACTIVE_OPERATION_STORAGE_PREFIX}${scriptId}`

const clearActiveOperationRef = (scriptId: string, expectedOperationId?: string) => {
  try {
    const key = activeOperationStorageKey(scriptId)
    if (expectedOperationId) {
      const raw = window.sessionStorage.getItem(key)
      if (raw) {
        try {
          const stored = asRecord(JSON.parse(raw))
          if (stored.operationId !== expectedOperationId) return
        } catch {
          window.sessionStorage.removeItem(key)
          return
        }
      }
    }
    window.sessionStorage.removeItem(key)
  } catch (caught) {
    logger.warn(
      `清理 MaaFW 托管操作恢复引用失败: ${caught instanceof Error ? caught.message : String(caught)}`
    )
  }
}

const writeActiveOperationRef = (
  scriptId: string,
  operationId: string,
  operation: MaaFWManagedOperation,
  currentCapabilities: MaaFWManagedCapabilities | null
) => {
  if (currentCapabilities?.features.operationProgress !== true) return
  const stored: MaaFWManagedActiveOperationRef = {
    v: 1,
    scriptId,
    operationId,
    operation,
    startedAt: new Date().toISOString(),
    apiVersion: currentCapabilities.apiVersion,
    distributionVersion: currentCapabilities.distributionVersion,
  }
  try {
    window.sessionStorage.setItem(activeOperationStorageKey(scriptId), JSON.stringify(stored))
  } catch (caught) {
    logger.warn(
      `保存 MaaFW 托管操作恢复引用失败: ${caught instanceof Error ? caught.message : String(caught)}`
    )
  }
}

const readActiveOperationRef = (
  scriptId: string,
  currentCapabilities: MaaFWManagedCapabilities
): MaaFWManagedActiveOperationRef | null => {
  try {
    const raw = window.sessionStorage.getItem(activeOperationStorageKey(scriptId))
    if (!raw) return null
    const stored = asRecord(JSON.parse(raw))
    const operation = asManagedOperation(stored.operation)
    const startedAt = typeof stored.startedAt === 'string' ? Date.parse(stored.startedAt) : NaN
    const valid =
      stored.v === 1 &&
      stored.scriptId === scriptId &&
      typeof stored.operationId === 'string' &&
      PROGRESS_ID_PATTERN.test(stored.operationId) &&
      Boolean(operation) &&
      Number.isFinite(startedAt) &&
      startedAt <= Date.now() + 5_000 &&
      stored.apiVersion === currentCapabilities.apiVersion &&
      stored.distributionVersion === currentCapabilities.distributionVersion
    if (!valid) {
      clearActiveOperationRef(scriptId)
      return null
    }
    return {
      v: 1,
      scriptId,
      operationId: stored.operationId as string,
      operation: operation as MaaFWManagedOperation,
      startedAt: stored.startedAt as string,
      apiVersion: stored.apiVersion as string,
      distributionVersion: stored.distributionVersion as string,
    }
  } catch (caught) {
    logger.warn(
      `读取 MaaFW 托管操作恢复引用失败: ${caught instanceof Error ? caught.message : String(caught)}`
    )
    clearActiveOperationRef(scriptId)
    return null
  }
}

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

class MaaFWManagedRequestError extends Error {
  constructor(
    message: string,
    readonly transient: boolean,
    readonly code?: number
  ) {
    super(message)
    this.name = 'MaaFWManagedRequestError'
  }
}

const isTransientRequestError = (error: unknown) =>
  error instanceof MaaFWManagedRequestError && error.transient

let operationCounter = 0

export function useMaaFWManagedApi() {
  const registryApi = useScriptRegistryApi()
  const pendingCount = ref(0)
  const error = ref<string | null>(null)
  const capabilities = ref<MaaFWManagedCapabilities | null>(null)
  const progress = ref<MaaFWManagedProgress>({ ...EMPTY_PROGRESS })
  const loading = computed(() => pendingCount.value > 0)

  let pollTimer: number | null = null
  let pollInFlight = false
  let progressGeneration = 0
  let activeProgressScriptId = ''
  let activeProgressStartedAt = 0
  let missingProgressSince = 0
  const progressSubscriptions = new Set<string>()
  const actionRequestsInFlight = new Set<string>()

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
        throw new MaaFWManagedRequestError(
          body.message || 'MaaFW 托管资源操作失败',
          body.code >= 500,
          body.code
        )
      }
      return body.data
    } catch (caught) {
      if (caught instanceof MaaFWManagedRequestError) throw caught
      throw new MaaFWManagedRequestError(
        pluginErrorMessage(caught, 'MaaFW 托管资源操作失败'),
        axios.isAxiosError(caught) &&
          (!caught.response || Number(caught.response.data?.code || caught.response.status) >= 500),
        axios.isAxiosError<PluginEnvelope<unknown>>(caught)
          ? Number(caught.response?.data?.code || caught.response?.status) || undefined
          : undefined
      )
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
    if (!operationId || operationId !== progress.value.operationId) return
    missingProgressSince = 0

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
      operation: asManagedOperation(raw.operation) || progress.value.operation,
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
    if (nextStatus === 'success' || nextStatus === 'error') {
      if (activeProgressScriptId) {
        clearActiveOperationRef(activeProgressScriptId, progress.value.operationId)
      }
      stopProgressTracking()
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
    pollInFlight = false
    activeProgressScriptId = ''
    activeProgressStartedAt = 0
    missingProgressSince = 0
  }

  const pollProgress = async (scriptId: string, operationId: string, generation: number) => {
    if (pollInFlight) return
    pollInFlight = true
    try {
      const data = await request<Record<string, unknown>>(MAAFW_MANAGED_ENDPOINTS.progress, {
        scriptId,
        operationId,
      })
      if (generation !== progressGeneration || operationId !== progress.value.operationId) {
        return
      }
      updateProgress(data)
    } catch (caught) {
      if (generation !== progressGeneration || operationId !== progress.value.operationId) return
      if (isTransientRequestError(caught)) {
        missingProgressSince = 0
        progress.value = {
          ...progress.value,
          status: 'running',
          stage: '正在重新连接',
          message: '与后端的连接暂时中断，正在恢复 MaaFW 操作进度',
        }
        return
      }
      if (caught instanceof MaaFWManagedRequestError && caught.code === 404) {
        if (capabilities.value?.features.activeOperationLookup === true) {
          try {
            const requestStillPending = actionRequestsInFlight.has(operationId)
            const active = await lookupAndAttachActiveOperation(scriptId, {
              emptyBehavior: requestStillPending ? 'keep' : 'reconcile',
            })
            if (active === 'none' && requestStillPending) {
              progress.value = {
                ...progress.value,
                status: 'running',
                stage: '正在等待后台登记操作',
                message: '操作请求仍在发送，正在等待 MaaFW 后端建立权威进度记录',
              }
            }
          } catch (lookupError) {
            const reason = pluginErrorMessage(lookupError, '服务端活跃操作查询失败')
            progress.value = {
              ...progress.value,
              status: 'running',
              stage: '无法确认服务端活跃操作',
              message: `暂时无法确认后台操作（${reason}）；为避免重复修改资源，将保持锁定并重试`,
            }
          }
          return
        }
        const now = Date.now()
        if (!missingProgressSince) missingProgressSince = now
        const waitingForRegistration =
          now - activeProgressStartedAt < 15_000 || now - missingProgressSince < 15_000
        progress.value = {
          ...progress.value,
          status: 'running',
          stage: waitingForRegistration ? '正在等待后台登记操作' : '正在确认进度记录',
          message: waitingForRegistration
            ? '操作请求刚刚发出，正在等待 MaaFW 后端建立进度记录'
            : '暂未找到操作进度；为避免重复修改资源，将继续保持锁定并重试',
        }
        return
      }
      const reason = pluginErrorMessage(caught, 'MaaFW 托管操作进度查询失败')
      missingProgressSince = 0
      progress.value = {
        ...progress.value,
        status: 'running',
        stage: '正在确认后台状态',
        message: `进度接口暂时无法确认操作终态（${reason}）；为避免重复修改资源，将保持锁定并继续重试`,
      }
    } finally {
      if (generation === progressGeneration) pollInFlight = false
    }
  }

  const attachProgressTracking = (
    scriptId: string,
    operationId: string,
    startedAt = Date.now()
  ) => {
    stopProgressTracking()
    activeProgressScriptId = scriptId
    activeProgressStartedAt = startedAt
    missingProgressSince = 0
    const generation = progressGeneration
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
    return generation
  }

  const beginProgressTracking = (
    scriptId: string,
    operation: MaaFWManagedOperation,
    message: string
  ) => {
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
    writeActiveOperationRef(scriptId, operationId, operation, capabilities.value)
    attachProgressTracking(scriptId, operationId)
    return operationId
  }

  const lookupAndAttachActiveOperation = async (
    scriptId: string,
    options: { emptyBehavior?: 'clear' | 'keep' | 'reconcile' } = {}
  ): Promise<'attached' | 'none'> => {
    const lookup = await request<MaaFWManagedActiveOperationLookup>(
      MAAFW_MANAGED_ENDPOINTS.activeOperation,
      { scriptId }
    )
    if (lookup.scriptId !== scriptId) {
      throw new Error('MaaFW 后端返回了不匹配的活跃操作脚本')
    }
    const serverEpoch = asString(lookup.serverEpoch).trim()
    if (!serverEpoch) {
      throw new Error('MaaFW 后端未返回有效的服务端运行标识')
    }
    const activeOperation = lookup.activeOperation
    if (activeOperation === null) {
      if (options.emptyBehavior !== 'keep') {
        clearActiveOperationRef(scriptId)
        stopProgressTracking()
        progress.value =
          options.emptyBehavior === 'reconcile'
            ? {
                ...progress.value,
                status: 'success',
                stage: '服务端已确认无活跃操作',
                message: '旧操作不存在或后端已经重启；正在重新核对资源状态，完成后将安全解锁',
                percent: null,
              }
            : { ...EMPTY_PROGRESS }
      }
      return 'none'
    }
    const operationId = asString(activeOperation.operationId)
    const operation = asManagedOperation(activeOperation.operation)
    if (asString(activeOperation.scriptId) !== scriptId) {
      throw new Error('MaaFW 后端返回的活跃操作不属于当前脚本')
    }
    if (asString(activeOperation.serverEpoch).trim() !== serverEpoch) {
      throw new Error('MaaFW 后端返回了过期的活跃操作')
    }
    if (!operationId || !PROGRESS_ID_PATTERN.test(operationId) || !operation) {
      throw new Error('MaaFW 后端返回了无效的活跃操作标识')
    }
    if (activeOperation.status !== 'running') {
      throw new Error('MaaFW 后端返回的活跃操作状态无效')
    }
    progress.value = {
      operationId,
      operation,
      status: 'running',
      stage: asString(activeOperation.stage) || '正在恢复操作状态',
      message: asString(activeOperation.message) || '正在读取 MaaFW 后端活跃操作进度',
      percent: asNumber(activeOperation.percent),
      downloadedBytes: asNumber(activeOperation.downloadedBytes),
      totalBytes: asNumber(activeOperation.totalBytes),
      logs: asStringArray(activeOperation.logs),
    }
    writeActiveOperationRef(scriptId, operationId, operation, capabilities.value)
    attachProgressTracking(scriptId, operationId)
    return 'attached'
  }

  const resumeProgress = async (scriptId: string): Promise<boolean> => {
    const currentCapabilities = capabilities.value
    if (!currentCapabilities || currentCapabilities.features.operationProgress !== true)
      return false

    if (currentCapabilities.features.activeOperationLookup === true) {
      stopProgressTracking()
      progress.value = {
        operationId: '',
        operation: '',
        status: 'running',
        stage: '正在查询服务端活跃操作',
        message: '正在由 MaaFW 后端确认该脚本是否有尚未结束的资源操作',
        percent: null,
        downloadedBytes: null,
        totalBytes: null,
        logs: [],
      }
      try {
        return (await lookupAndAttachActiveOperation(scriptId)) === 'attached'
      } catch (caught) {
        progress.value = {
          ...progress.value,
          stage: '无法确认服务端活跃操作',
          message: '为避免重复修改 MaaFW 资源，项目管理操作将保持锁定；请重试',
        }
        throw caught
      }
    }

    const stored = readActiveOperationRef(scriptId, currentCapabilities)
    if (!stored) return false
    progress.value = {
      operationId: stored.operationId,
      operation: stored.operation,
      status: 'running',
      stage: '正在恢复操作状态',
      message: '正在读取离开页面前的 MaaFW 托管操作进度',
      percent: null,
      downloadedBytes: null,
      totalBytes: null,
      logs: [],
    }
    const parsedStartedAt = Date.parse(stored.startedAt)
    const generation = attachProgressTracking(
      scriptId,
      stored.operationId,
      Number.isFinite(parsedStartedAt) ? Math.min(parsedStartedAt, Date.now()) : Date.now()
    )
    await pollProgress(scriptId, stored.operationId, generation)
    return progress.value.operationId === stored.operationId
  }

  const tracked = async <T>(
    scriptId: string,
    operation: MaaFWManagedOperation,
    message: string,
    action: (progressId: string) => Promise<T>
  ) => {
    const progressId = beginProgressTracking(scriptId, operation, message)
    let keepTracking = false
    actionRequestsInFlight.add(progressId)
    try {
      const result = await action(progressId)
      actionRequestsInFlight.delete(progressId)
      if (progress.value.operationId === progressId && progress.value.status === 'running') {
        progress.value = {
          ...progress.value,
          status: 'success',
          stage: '操作完成',
          message: '操作已完成',
          percent: 100,
        }
      }
      clearActiveOperationRef(scriptId, progressId)
      return result
    } catch (caught) {
      actionRequestsInFlight.delete(progressId)
      if (capabilities.value?.features.operationProgress === true) {
        let authoritativeProgress: Record<string, unknown> | null = null
        try {
          authoritativeProgress = await request<Record<string, unknown>>(
            MAAFW_MANAGED_ENDPOINTS.progress,
            { scriptId, operationId: progressId }
          )
        } catch (progressError) {
          if (!(progressError instanceof MaaFWManagedRequestError && progressError.code === 404)) {
            if (progress.value.operationId === progressId && progress.value.status === 'success') {
              progress.value = {
                ...progress.value,
                stage: '操作已完成，请刷新',
                message: '服务端已通过实时进度确认操作完成；请以刷新后的资源状态为准',
                percent: 100,
              }
              return undefined
            }
            if (progress.value.operationId === progressId && progress.value.status === 'error') {
              throw new MaaFWManagedRequestError(
                progress.value.message || 'MaaFW 后端确认资源操作失败',
                false
              )
            }
            keepTracking = true
            progress.value = {
              ...progress.value,
              status: 'running',
              stage: '无法确认原操作状态',
              message: '动作请求异常后无法读取原操作进度；为避免重复修改资源，将保持锁定并重试',
            }
            throw caught
          }
        }

        if (authoritativeProgress !== null) {
          const authoritativeOperationId =
            asString(authoritativeProgress.operationId) ||
            asString(authoritativeProgress.progressId)
          if (authoritativeOperationId !== progressId) {
            keepTracking = true
            progress.value = {
              ...progress.value,
              status: 'running',
              stage: '原操作响应无效',
              message: '后端返回了不匹配的操作进度；为避免重复修改资源，将保持锁定',
            }
            throw caught
          }
          updateProgress(authoritativeProgress)
          if (progress.value.status === 'success') {
            progress.value = {
              ...progress.value,
              stage: '操作已完成，请刷新',
              message: '服务端确认操作已经完成；原请求响应中断，请以刷新后的资源状态为准',
              percent: 100,
            }
            return undefined
          }
          if (progress.value.status === 'error') {
            throw new MaaFWManagedRequestError(
              progress.value.message || 'MaaFW 后端确认资源操作失败',
              false
            )
          }
        }

        if (capabilities.value.features.activeOperationLookup !== true) {
          keepTracking = true
          progress.value = {
            ...progress.value,
            status: 'running',
            stage: '正在确认后台状态',
            message: '原操作尚未返回终态；将继续按原操作编号跟踪，确认前不会解锁新操作',
          }
          throw caught
        }
        let active: 'attached' | 'none'
        try {
          active = await lookupAndAttachActiveOperation(scriptId, { emptyBehavior: 'keep' })
        } catch {
          keepTracking = true
          progress.value = {
            ...progress.value,
            status: 'running',
            stage: '无法确认服务端活跃操作',
            message: '动作请求失败后无法安全读取服务端状态；为避免重复修改资源，将保持锁定',
          }
          throw caught
        }
        if (active === 'attached') {
          keepTracking = true
          throw caught
        }
        clearActiveOperationRef(scriptId, progressId)
        stopProgressTracking()
        const reason = pluginErrorMessage(caught, 'MaaFW 托管资源操作失败')
        if (!(caught instanceof MaaFWManagedRequestError) || caught.code === undefined) {
          progress.value = {
            ...EMPTY_PROGRESS,
            operationId: progressId,
            operation,
            status: 'unknown',
            stage: '操作结果待核对',
            message: '请求连接中断且后端已无原操作记录；正在重新核对资源状态，完成后将安全解锁',
          }
          return undefined
        }
        progress.value = {
          ...EMPTY_PROGRESS,
          operationId: progressId,
          operation,
          status: 'error',
          stage: '操作失败',
          message: reason,
        }
        throw caught
      }
      if (caught instanceof MaaFWManagedRequestError && caught.code === 409) {
        clearActiveOperationRef(scriptId, progressId)
        try {
          const attached = await resumeProgress(scriptId)
          if (attached) {
            keepTracking = true
          } else {
            progress.value = {
              ...EMPTY_PROGRESS,
              status: 'running',
              stage: '正在确认服务端活跃操作',
              message: '服务端拒绝了重复操作，但未返回可接管的操作；为避免重复修改资源，将保持锁定',
            }
          }
        } catch {
          progress.value = {
            ...EMPTY_PROGRESS,
            status: 'running',
            stage: '无法接管服务端活跃操作',
            message: '服务端已拒绝重复操作，但无法安全读取当前操作；为避免重复修改资源，将保持锁定',
          }
        }
        throw caught
      }
      const reason = pluginErrorMessage(caught, 'MaaFW 托管资源操作失败')
      if (
        progress.value.operationId === progressId &&
        progress.value.status !== 'success' &&
        progress.value.status !== 'error'
      ) {
        progress.value = {
          ...progress.value,
          status: 'error',
          stage: '操作失败',
          message: reason,
        }
      }
      clearActiveOperationRef(scriptId, progressId)
      throw caught
    } finally {
      actionRequestsInFlight.delete(progressId)
      if (!keepTracking && progress.value.operationId === progressId) stopProgressTracking()
    }
  }

  const releaseProgressTracking = (scriptId: string, operationId: string) => {
    if (
      activeProgressScriptId !== scriptId ||
      progress.value.operationId !== operationId ||
      progress.value.status !== 'running' ||
      progress.value.stage !== '正在确认进度记录' ||
      !missingProgressSince ||
      Date.now() - missingProgressSince < 15_000
    ) {
      return false
    }
    clearActiveOperationRef(scriptId, operationId)
    stopProgressTracking()
    progress.value = { ...EMPTY_PROGRESS }
    return true
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

  const getInventory = () =>
    run(() => request<MaaFWManagedGlobalInventory>(MAAFW_MANAGED_ENDPOINTS.inventory, {}))

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
      tracked(input.scriptId, 'remote-check', '正在检查远程资源版本', progressId =>
        request<MaaFWManagedRemoteDiscovery>(
          MAAFW_MANAGED_ENDPOINTS.checkRemote,
          { ...input, progressId },
          progressId
        )
      )
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
    resumeProgress,
    releaseProgressTracking,
    getCurrentBinding,
    getOverview,
    listProjects,
    listVersions,
    listRuntimes,
    getInventory,
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
