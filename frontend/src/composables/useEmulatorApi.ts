import { onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useEventListener } from '@vueuse/core'
import type {
  EmulatorConfig,
  EmulatorConfigIndexItem,
  EmulatorSearchResult,
  DeviceInfo,
} from '@/api'
import { EmulatorOperateIn, Service } from '@/api'
import { CancelError } from '@/api/core/CancelablePromise'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR_NOTICE,
  WS_ID_EMULATOR_MANAGER,
  type WSEnvelope,
  type WSTaskNoticeData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('模拟器管理')

export type EmulatorType = 'general' | 'mumu' | 'ldplayer'

export interface EmulatorInfo {
  name: string
  type: EmulatorType | ''
  path: string
  max_wait_time: number
  boss_keys: string[]
  force_kill_on_close: boolean
}

export const emulatorTypeOptions = [
  { value: 'general', label: '通用模拟器' },
  { value: 'mumu', label: 'MuMu模拟器' },
  { value: 'ldplayer', label: '雷电模拟器' },
]

export const DeviceStatus = {
  ONLINE: 0,
  OFFLINE: 1,
  STARTING: 2,
  CLOSING: 3,
  ERROR: 4,
  NOT_FOUND: 5,
  UNKNOWN: 10,
} as const

export function getDeviceStatusInfo(status: number) {
  switch (status) {
    case DeviceStatus.ONLINE:
      return { text: '在线', color: 'success' as const }
    case DeviceStatus.OFFLINE:
      return { text: '离线', color: 'default' as const }
    case DeviceStatus.STARTING:
      return { text: '启动中', color: 'processing' as const }
    case DeviceStatus.CLOSING:
      return { text: '关闭中', color: 'warning' as const }
    case DeviceStatus.ERROR:
      return { text: '错误', color: 'error' as const }
    case DeviceStatus.NOT_FOUND:
      return { text: '未找到', color: 'error' as const }
    case DeviceStatus.UNKNOWN:
      return { text: '未知', color: 'default' as const }
    default:
      return { text: '未知', color: 'default' as const }
  }
}

export function canStartDevice(status: number): boolean {
  return (
    status === DeviceStatus.OFFLINE ||
    status === DeviceStatus.ERROR ||
    status === DeviceStatus.NOT_FOUND ||
    status === DeviceStatus.UNKNOWN
  )
}

export function canStopDevice(status: number): boolean {
  return status === DeviceStatus.ONLINE || status === DeviceStatus.STARTING
}

/**
 * 模拟器类型能力矩阵。
 * 所有类型都依赖有效的模拟器路径；路径为空时对应操作禁用。
 * 这是前端基于当前后端契约（app/api/emulator.py）的降级能力声明，
 * 不虚构后端未提供的操作。
 */
export type EmulatorCapability = 'open' | 'close' | 'show' | 'force_kill' | 'boss_key'

const CAPABILITY_MATRIX: Record<EmulatorType | '', Record<EmulatorCapability, boolean>> = {
  general: {
    open: true,
    close: true,
    show: true,
    force_kill: false,
    boss_key: true,
  },
  mumu: {
    open: true,
    close: true,
    show: true,
    force_kill: true,
    boss_key: false,
  },
  ldplayer: {
    open: true,
    close: true,
    show: true,
    force_kill: false,
    boss_key: true,
  },
  '': {
    open: false,
    close: false,
    show: false,
    force_kill: false,
    boss_key: false,
  },
}

export function getEmulatorCapabilities(
  type: EmulatorType | ''
): Record<EmulatorCapability, boolean> {
  return { ...CAPABILITY_MATRIX[type || ''] }
}

export interface DeviceActionState {
  disabled: boolean
  loading: boolean
  reason: string
}

/**
 * 根据设备状态、模拟器类型和当前操作计算按钮禁用状态与原因。
 * 不支持的按钮必须 disabled 并给出原因（unverified：真实 GUI/设备验证部分标记为未验证）。
 */
export function getDeviceActionState(
  operation: 'open' | 'close' | 'show',
  status: number,
  emulatorType: EmulatorType | '',
  hasPath: boolean,
  inFlight: boolean
): DeviceActionState {
  const caps = getEmulatorCapabilities(emulatorType)
  const capKey: EmulatorCapability = operation
  if (!caps[capKey]) {
    return {
      disabled: true,
      loading: false,
      reason: `当前模拟器类型（${emulatorType || '未选择'}）不支持「${
        operation === 'open' ? '启动' : operation === 'close' ? '关闭' : '显示'
      }」操作`,
    }
  }
  if (!hasPath) {
    return {
      disabled: true,
      loading: false,
      reason: '未配置模拟器路径，请先选择路径',
    }
  }
  if (inFlight) {
    return {
      disabled: true,
      loading: true,
      reason: '操作进行中…',
    }
  }
  if (operation === 'open' && !canStartDevice(status)) {
    return {
      disabled: true,
      loading: false,
      reason: `当前状态为「${getDeviceStatusInfo(status).text}」，不可启动`,
    }
  }
  if (operation === 'close' && !canStopDevice(status)) {
    return {
      disabled: true,
      loading: false,
      reason: `当前状态为「${getDeviceStatusInfo(status).text}」，不可关闭`,
    }
  }
  if (operation === 'show' && status !== DeviceStatus.ONLINE) {
    return {
      disabled: true,
      loading: false,
      reason: `当前状态为「${getDeviceStatusInfo(status).text}」，仅在线设备可显示`,
    }
  }
  return { disabled: false, loading: false, reason: '' }
}

function safeJsonParse<T>(jsonString: string | null | undefined, fallback: T): T {
  if (!jsonString) return fallback
  try {
    return JSON.parse(jsonString) as T
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    logger.error(`JSON 解析失败: ${errorMsg}`)
    return fallback
  }
}

export function buildEditingData(configData: EmulatorConfig | undefined): EmulatorInfo {
  const info = configData?.Info
  return {
    name: info?.Name || '',
    type: (info?.Type as EmulatorType) || '',
    path: info?.Path || '',
    max_wait_time: info?.MaxWaitTime || 300,
    boss_keys: safeJsonParse<string[]>(info?.BossKey, []),
    force_kill_on_close: info?.ForceKillOnClose !== false,
  }
}

export interface PollOptions {
  intervalMs?: number
  timeoutMs?: number
  retries?: number
  retryDelayMs?: number
}

const DEFAULT_POLL_OPTIONS: Required<PollOptions> = {
  intervalMs: 5000,
  timeoutMs: 10000,
  retries: 2,
  retryDelayMs: 1000,
}

export interface CancellablePromise<T> extends Promise<T> {
  /**
   * 取消当前正在进行的请求。
   * 取消后 promise 会被 reject，并带有 `CancelError` 或自定义原因。
   */
  cancel: (reason?: string) => void
}

function isCancelable<T>(promise: Promise<T>): promise is CancellablePromise<T> {
  return typeof (promise as CancellablePromise<T>).cancel === 'function'
}

/**
 * 带超时、重试和取消的异步包装。
 *
 * - 通过 Promise.race 在 timeoutMs 后拒绝，避免无限等待。
 * - 重试之间等待 retryDelayMs。
 * - 返回的 promise 带有 `cancel()` 方法；调用后当前请求立即拒绝，
 *   且后续重试不再执行。
 * - 对底层 factory 产生的 late rejection 做 swallow 处理，防止卸载/超时后
 *   产生 unhandled rejection。
 *
 * 注意：factory 应直接返回生成的 Service 方法（CancelablePromise），不要在其后
 * 链式调用 .then()，否则 cancel() 方法会丢失。如需转换结果，请在调用处对返回值处理。
 */
export function withTimeoutAndRetry<T>(
  factory: () => Promise<T>,
  options: { timeoutMs: number; retries: number; retryDelayMs: number; label: string }
): CancellablePromise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let currentRequest: Promise<T> | null = null
  let rejectAttempt: ((reason?: unknown) => void) | null = null
  let cancelled = false
  let cancelReason = '请求已取消'
  let lastError: unknown

  const cleanup = () => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  const cancelCurrentRequest = (reason?: string) => {
    if (currentRequest && isCancelable(currentRequest)) {
      try {
        currentRequest.cancel(reason)
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        logger.debug(`取消请求时忽略错误: ${msg}`)
      }
    }
  }

  const doCancel = (reason: string) => {
    if (cancelled) return
    cancelled = true
    cancelReason = reason
    cleanup()
    cancelCurrentRequest(reason)
    if (rejectAttempt) {
      rejectAttempt(new CancelError(reason))
    }
  }

  let resolveOuter!: (value: T) => void
  let rejectOuter!: (reason?: unknown) => void
  const promise = new Promise<T>((resolve, reject) => {
    resolveOuter = resolve
    rejectOuter = reject
  }) as CancellablePromise<T>

  const runAttempt = async (attempt: number): Promise<T> => {
    if (cancelled) {
      throw new CancelError(cancelReason)
    }

    if (attempt > 0) {
      logger.info(`${options.label} 第 ${attempt}/${options.retries} 次重试…`)
      await new Promise(resolveDelay => setTimeout(resolveDelay, options.retryDelayMs))
      if (cancelled) {
        throw new CancelError(cancelReason)
      }
    }

    cleanup()
    currentRequest = factory()
    const request = currentRequest

    // 预附加一个空 catch，防止请求在超时/取消后产生 late rejection。
    request.catch(() => {
      /* late rejection swallowed */
    })

    return new Promise<T>((resolve, rejectInner) => {
      rejectAttempt = rejectInner

      timeoutId = setTimeout(() => {
        if (cancelled) return
        cancelCurrentRequest(`请求超时 (${options.timeoutMs}ms)`)
        rejectInner(new Error(`请求超时 (${options.timeoutMs}ms)`))
      }, options.timeoutMs)

      request.then(
        value => {
          cleanup()
          resolve(value)
        },
        reason => {
          cleanup()
          rejectInner(reason)
        }
      )
    })
  }

  ;(async () => {
    for (let attempt = 0; attempt <= options.retries; attempt++) {
      try {
        const result = await runAttempt(attempt)
        resolveOuter(result)
        return
      } catch (e) {
        rejectAttempt = null
        currentRequest = null
        if (cancelled) {
          rejectOuter(new CancelError(cancelReason))
          return
        }
        lastError = e
        const errorMsg = e instanceof Error ? e.message : String(e)
        logger.warn(`${options.label} 失败: ${errorMsg}`)
      }
    }
    rejectOuter(lastError)
  })()

  promise.cancel = (reason?: string) => {
    doCancel(reason ?? '请求已取消')
  }

  return promise
}

export function useEmulatorManagement(pollOptions: PollOptions = {}) {
  const { intervalMs, timeoutMs, retries, retryDelayMs } = {
    ...DEFAULT_POLL_OPTIONS,
    ...pollOptions,
  }

  const loading = ref(false)
  const searching = ref(false)
  const emulatorIndex = ref<EmulatorConfigIndexItem[]>([])
  const emulatorData = ref<Record<string, EmulatorConfig>>({})
  const searchResults = ref<EmulatorSearchResult[]>([])
  const showSearchModal = ref(false)
  const devicesData = ref<Record<string, Record<string, DeviceInfo>>>({})
  const loadingDevices = ref<Set<string>>(new Set())
  const startingDevices = ref<Set<string>>(new Set())
  const stoppingDevices = ref<Set<string>>(new Set())
  const showingDevices = ref<Set<string>>(new Set())
  const editingDataMap = ref<Map<string, EmulatorInfo>>(new Map())
  const savingMap = ref<Map<string, boolean>>(new Map())
  const bossKeyInputMap = ref<Record<string, string>>({})
  const pendingOperations = new Map<
    string,
    { uuid: string; index: string; operation: 'open' | 'close' | 'show' }
  >()

  const STORAGE_KEY = 'emulator_active_key'
  const activeKey = ref<string>(localStorage.getItem(STORAGE_KEY) || '')

  // 轮询状态：使用递归 setTimeout 替代 setInterval，避免回调重叠；
  // 通过 generation + AbortController 防止旧响应覆盖和卸载后迟到响应。
  const pollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  let pollGeneration = 0
  let pollInFlight = false
  let disposed = false
  let currentPollAbort: (() => void) | null = null

  // 每个模拟器上轮询的 partial 失败信息（最后一次失败原因）
  const pollingErrors = ref<Record<string, string>>({})

  const saveActiveKey = (key: string) => {
    if (key) {
      localStorage.setItem(STORAGE_KEY, key)
    }
  }

  const abortCurrentPoll = () => {
    if (currentPollAbort) {
      currentPollAbort()
      currentPollAbort = null
    }
  }

  /**
   * 轮询所有模拟器设备状态。
   * 支持：
   * - generation 守卫：旧响应不覆盖新数据
   * - 可取消：新轮询启动或卸载时取消所有在途子请求
   * - timeout + retry：单个模拟器状态请求失败可重试
   * - partial 失败：某个模拟器失败不影响其他模拟器状态更新
   */
  const pollDevicesStatus = async () => {
    if (emulatorIndex.value.length === 0) return
    if (pollInFlight) {
      // 如果上一轮仍在执行，跳过本次，避免重叠；
      // 等上一轮结束后由递归 setTimeout 自动调度下一轮。
      return
    }
    pollInFlight = true
    abortCurrentPoll()

    const generation = ++pollGeneration
    const activeCancels: Array<() => void> = []
    currentPollAbort = () => {
      activeCancels.forEach(cancel => cancel())
    }

    try {
      const results = await Promise.allSettled(
        emulatorIndex.value.map(async emulator => {
          const request = withTimeoutAndRetry(
            () => Service.getStatusApiEmulatorStatusPost({ emulatorId: emulator.uid }),
            {
              timeoutMs,
              retries,
              retryDelayMs,
              label: `轮询设备状态 ${emulator.uid}`,
            }
          )
          activeCancels.push(() => request.cancel())
          const response = await request
          return { emulator, response }
        })
      )

      if (disposed || generation !== pollGeneration) return

      for (const result of results) {
        if (result.status === 'fulfilled' && result.value.response.code === 200) {
          const { emulator, response } = result.value
          const current =
            ((response.data as Record<string, Record<string, DeviceInfo>>) || {})[emulator.uid] ||
            {}
          devicesData.value[emulator.uid] = current
          delete pollingErrors.value[emulator.uid]
        }
      }

      // 记录 partial 失败
      for (let i = 0; i < results.length; i++) {
        const result = results[i]
        const emulator = emulatorIndex.value[i]
        if (result.status === 'rejected') {
          const errorMsg =
            result.reason instanceof Error ? result.reason.message : String(result.reason)
          pollingErrors.value[emulator.uid] = errorMsg
          logger.warn(`轮询设备状态 partial 失败 [${emulator.uid}]: ${errorMsg}`)
        } else if (result.value.response.code !== 200) {
          pollingErrors.value[emulator.uid] = result.value.response.message || '状态查询失败'
          logger.warn(
            `轮询设备状态 partial 失败 [${emulator.uid}]: ${result.value.response.message}`
          )
        }
      }
    } catch (e) {
      if (!disposed && generation === pollGeneration) {
        const errorMsg = e instanceof Error ? e.message : String(e)
        logger.warn(`轮询设备状态时出错: ${errorMsg}`)
      }
    } finally {
      // 无论 generation 是否变化，都必须重置 pollInFlight，否则 stop/start 后轮询会永久阻塞。
      pollInFlight = false
      if (generation === pollGeneration) {
        currentPollAbort = null
      }
    }
  }

  /**
   * 递归调度轮询。当前轮次完成后才安排下一次，避免重叠。
   */
  const scheduleNextPoll = () => {
    if (pollingTimer.value) {
      clearTimeout(pollingTimer.value)
      pollingTimer.value = null
    }
    pollingTimer.value = setTimeout(async () => {
      await pollDevicesStatus()
      if (!disposed) {
        scheduleNextPoll()
      }
    }, intervalMs)
  }

  const startPolling = () => {
    if (pollingTimer.value) return
    logger.info('模拟器页面轮询已启动')
    void pollDevicesStatus()
    scheduleNextPoll()
  }

  const stopPolling = () => {
    abortCurrentPoll()
    if (pollingTimer.value) {
      clearTimeout(pollingTimer.value)
      pollingTimer.value = null
      logger.info('模拟器页面轮询已停止')
    }
    // 递增 generation，使运行中的请求结果不再被采纳
    pollGeneration++
  }

  const syncNameToDisplay = (uuid: string, name: string) => {
    if (emulatorData.value[uuid]?.Info) {
      emulatorData.value[uuid].Info!.Name = name
    }
  }

  const loadEmulators = async () => {
    loading.value = true
    try {
      const response = await withTimeoutAndRetry(
        () => Service.getEmulatorApiEmulatorGetPost({ emulatorId: null }),
        { timeoutMs, retries, retryDelayMs, label: '加载模拟器配置' }
      )
      if (response.code === 200 && 'index' in response && 'data' in response) {
        emulatorIndex.value = (response.index as EmulatorConfigIndexItem[]) || []
        emulatorData.value = (response.data as Record<string, EmulatorConfig>) || {}

        emulatorIndex.value.forEach(item => {
          const configData = emulatorData.value[item.uid]
          const editData = buildEditingData(configData)
          editingDataMap.value.set(item.uid, editData)
          if (editData.boss_keys.length > 0) {
            bossKeyInputMap.value[item.uid] = editData.boss_keys[0]
          }
        })
      } else {
        message.error(response.message || '加载模拟器配置失败')
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`加载模拟器配置失败: ${errorMsg}`)
      message.error('加载模拟器配置失败')
    } finally {
      loading.value = false
    }
  }

  const refreshEmulatorConfig = async (uuid?: string) => {
    try {
      const response = await withTimeoutAndRetry(
        () => Service.getEmulatorApiEmulatorGetPost({ emulatorId: uuid || null }),
        { timeoutMs, retries: 1, retryDelayMs, label: '刷新模拟器配置' }
      )
      if (response.code === 200 && 'index' in response && 'data' in response) {
        if (uuid) {
          const updatedIndex = response.index as EmulatorConfigIndexItem[]
          const updatedData = response.data as Record<string, EmulatorConfig>

          if (updatedIndex.length > 0 && updatedData[uuid]) {
            const indexItem = emulatorIndex.value.find(item => item.uid === uuid)
            if (indexItem) {
              indexItem.type = updatedIndex[0].type
            }
            emulatorData.value[uuid] = updatedData[uuid]
            const configData = updatedData[uuid]
            const editData = buildEditingData(configData)
            editingDataMap.value.set(uuid, editData)
            if (editData.boss_keys.length > 0) {
              bossKeyInputMap.value[uuid] = editData.boss_keys[0]
            }
          }
        } else {
          emulatorIndex.value = (response.index as EmulatorConfigIndexItem[]) || []
          emulatorData.value = (response.data as Record<string, EmulatorConfig>) || {}
          emulatorIndex.value.forEach(item => {
            const configData = emulatorData.value[item.uid]
            const editData = buildEditingData(configData)
            editingDataMap.value.set(item.uid, editData)
            if (editData.boss_keys.length > 0) {
              bossKeyInputMap.value[item.uid] = editData.boss_keys[0]
            }
          })
        }
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`刷新模拟器配置失败: ${errorMsg}`)
    }
  }

  const getEditingData = (uuid: string): EmulatorInfo => {
    if (!editingDataMap.value.has(uuid)) {
      const configData = emulatorData.value[uuid]
      editingDataMap.value.set(uuid, buildEditingData(configData))
    }
    return editingDataMap.value.get(uuid)!
  }

  const handleSaveChange = async (
    uuid: string,
    key: 'name' | 'path' | 'type' | 'max_wait_time' | 'boss_keys' | 'force_kill_on_close',
    value: string | number | string[] | boolean
  ) => {
    savingMap.value.set(uuid, true)
    try {
      let configData: Partial<EmulatorConfig> = {}

      if (key === 'name') {
        configData = { Info: { Name: value as string } }
      } else if (key === 'path') {
        configData = { Info: { Path: value as string } }
      } else if (key === 'type') {
        configData = { Info: { Type: value as EmulatorType } }
      } else if (key === 'max_wait_time') {
        configData = { Info: { MaxWaitTime: value as number } }
      } else if (key === 'boss_keys') {
        configData = { Info: { BossKey: JSON.stringify(value as string[]) } }
      } else if (key === 'force_kill_on_close') {
        configData = { Info: { ForceKillOnClose: value as boolean } }
      }

      const response = await withTimeoutAndRetry(
        () =>
          Service.updateEmulatorApiEmulatorUpdatePost({
            emulatorId: uuid,
            data: configData,
          }),
        { timeoutMs, retries: 1, retryDelayMs, label: '保存模拟器配置' }
      )

      if (response.code === 200) {
        logger.info(`配置已保存: ${key}`)
        await refreshEmulatorConfig(uuid)
      } else {
        message.error(response.message || '保存失败')
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`保存模拟器配置失败: ${errorMsg}`)
      message.error('保存模拟器配置失败')
    } finally {
      savingMap.value.set(uuid, false)
    }
  }

  const handleAdd = async () => {
    try {
      const response = await withTimeoutAndRetry(() => Service.addEmulatorApiEmulatorAddPost(), {
        timeoutMs,
        retries: 1,
        retryDelayMs,
        label: '添加模拟器',
      })
      if (response.code === 200) {
        await loadEmulators()
        activeKey.value = response.emulatorId
        saveActiveKey(activeKey.value)
        await loadDevices(response.emulatorId)
        return response.emulatorId
      } else {
        message.error(response.message || '添加失败')
        return null
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`添加模拟器失败: ${errorMsg}`)
      message.error('添加模拟器失败')
      return null
    }
  }

  const handleDelete = async (uuid: string) => {
    try {
      const response = await withTimeoutAndRetry(
        () => Service.deleteEmulatorApiEmulatorDeletePost({ emulatorId: uuid }),
        { timeoutMs, retries: 1, retryDelayMs, label: '删除模拟器' }
      )
      if (response.code === 200) {
        if (activeKey.value === uuid) {
          const currentIndex = emulatorIndex.value.findIndex(e => e.uid === uuid)
          if (currentIndex < emulatorIndex.value.length - 1) {
            activeKey.value = emulatorIndex.value[currentIndex + 1].uid
          } else if (currentIndex > 0) {
            activeKey.value = emulatorIndex.value[currentIndex - 1].uid
          } else {
            activeKey.value = ''
            localStorage.removeItem(STORAGE_KEY)
          }
          saveActiveKey(activeKey.value)
        }
        await loadEmulators()
        return true
      } else {
        message.error(response.message || '删除失败')
        return false
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`删除模拟器失败: ${errorMsg}`)
      message.error('删除模拟器失败')
      return false
    }
  }

  const handleSearch = async () => {
    searching.value = true
    try {
      const response = await withTimeoutAndRetry(
        () => Service.searchEmulatorsApiEmulatorEmulatorSearchPost(),
        { timeoutMs, retries: 1, retryDelayMs, label: '搜索模拟器' }
      )
      if (response.code === 200) {
        searchResults.value = response.emulators || []
        if (searchResults.value.length > 0) {
          showSearchModal.value = true
          message.success(`找到 ${searchResults.value.length} 个模拟器`)
        } else {
          message.info('未找到已安装的模拟器')
        }
      } else {
        message.error(response.message || '搜索失败')
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`搜索模拟器失败: ${errorMsg}`)
      message.error('搜索模拟器失败')
    } finally {
      searching.value = false
    }
  }

  const handleImportFromSearch = async (result: EmulatorSearchResult) => {
    try {
      const response = await withTimeoutAndRetry(() => Service.addEmulatorApiEmulatorAddPost(), {
        timeoutMs,
        retries: 1,
        retryDelayMs,
        label: '导入添加模拟器',
      })
      if (response.code === 200) {
        const updateResponse = await withTimeoutAndRetry(
          () =>
            Service.updateEmulatorApiEmulatorUpdatePost({
              emulatorId: response.emulatorId,
              data: {
                Info: {
                  Name: result.name,
                  Type: result.type as EmulatorType,
                  Path: result.path,
                  MaxWaitTime: 300,
                  BossKey: JSON.stringify([]),
                },
              },
            }),
          { timeoutMs, retries: 1, retryDelayMs, label: '导入更新模拟器' }
        )
        if (updateResponse.code === 200) {
          message.success('导入成功')
          await loadEmulators()
          showSearchModal.value = false
          return response.emulatorId
        } else {
          message.error(updateResponse.message || '导入失败')
          return null
        }
      } else {
        message.error(response.message || '导入失败')
        return null
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`导入模拟器失败: ${errorMsg}`)
      message.error('导入模拟器失败')
      return null
    }
  }

  const loadDevices = async (uuid: string) => {
    loadingDevices.value.add(uuid)
    loadingDevices.value = new Set(loadingDevices.value)

    try {
      const response = await withTimeoutAndRetry(
        () => Service.getStatusApiEmulatorStatusPost({ emulatorId: uuid }),
        { timeoutMs, retries, retryDelayMs, label: `获取设备信息 ${uuid}` }
      )
      if (response.code === 200) {
        const allDevicesData = (response.data as Record<string, Record<string, DeviceInfo>>) || {}
        const currentDevices = allDevicesData[uuid] || {}
        devicesData.value[uuid] = currentDevices
        delete pollingErrors.value[uuid]
      } else {
        message.error(response.message || '获取设备信息失败')
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`获取设备信息失败: ${errorMsg}`)
      message.error('获取设备信息失败')
    } finally {
      loadingDevices.value.delete(uuid)
      loadingDevices.value = new Set(loadingDevices.value)
    }
  }

  const handleEmulatorNotice = (envelope: WSEnvelope) => {
    const data = envelope.data as Partial<WSTaskNoticeData>
    const operationId = typeof data.operationId === 'string' ? data.operationId : ''
    if (!operationId) return

    const pending = pendingOperations.get(operationId)
    if (!pending) return
    pendingOperations.delete(operationId)

    if (data.level === 'error') {
      message.error(data.message || '模拟器操作失败')
    } else if (data.level === 'warning') {
      message.warning(data.message || '模拟器操作未完成')
    } else {
      message.success(data.message || '模拟器操作完成')
    }
    void loadDevices(pending.uuid)
  }

  const emulatorNoticeSubscriptionId = subscribe(
    { id: WS_ID_EMULATOR_MANAGER, type: WS_EMULATOR_NOTICE },
    handleEmulatorNotice
  )

  const rememberPendingOperation = (
    operationId: unknown,
    uuid: string,
    index: string,
    operation: 'open' | 'close' | 'show'
  ): boolean => {
    if (typeof operationId !== 'string' || !operationId.trim()) return false
    pendingOperations.set(operationId, { uuid, index, operation })
    return true
  }

  const startEmulator = async (uuid: string, index: string) => {
    const deviceKey = `${uuid}-${index}`
    if (startingDevices.value.has(deviceKey)) return
    startingDevices.value.add(deviceKey)
    startingDevices.value = new Set(startingDevices.value)

    try {
      const response = await withTimeoutAndRetry(
        () =>
          Service.operationEmulatorApiEmulatorOperatePost({
            emulatorId: uuid,
            operate: EmulatorOperateIn.operate.OPEN,
            index: index,
          }),
        { timeoutMs, retries: 1, retryDelayMs, label: `启动模拟器 ${uuid}#${index}` }
      )

      if (response.code === 200) {
        if (!rememberPendingOperation(response.operationId, uuid, index, 'open')) {
          message.info(response.message || `模拟器 ${index} 启动指令已受理`)
          setTimeout(() => loadDevices(uuid), 2000)
        }
      } else {
        message.error(response.message || '启动失败')
      }
      return response
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`启动模拟器失败: ${errorMsg}`)
      message.error('启动模拟器失败')
      throw e
    } finally {
      startingDevices.value.delete(deviceKey)
      startingDevices.value = new Set(startingDevices.value)
    }
  }

  const stopEmulator = async (uuid: string, index: string) => {
    const deviceKey = `${uuid}-${index}`
    if (stoppingDevices.value.has(deviceKey)) return
    stoppingDevices.value.add(deviceKey)
    stoppingDevices.value = new Set(stoppingDevices.value)

    try {
      const response = await withTimeoutAndRetry(
        () =>
          Service.operationEmulatorApiEmulatorOperatePost({
            emulatorId: uuid,
            operate: EmulatorOperateIn.operate.CLOSE,
            index: index,
          }),
        { timeoutMs, retries: 1, retryDelayMs, label: `关闭模拟器 ${uuid}#${index}` }
      )

      if (response.code === 200) {
        if (!rememberPendingOperation(response.operationId, uuid, index, 'close')) {
          message.info(response.message || `模拟器 ${index} 关闭指令已受理`)
          setTimeout(() => loadDevices(uuid), 2000)
        }
      } else {
        message.error(response.message || '关闭失败')
      }
      return response
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`关闭模拟器失败: ${errorMsg}`)
      message.error('关闭模拟器失败')
      throw e
    } finally {
      stoppingDevices.value.delete(deviceKey)
      stoppingDevices.value = new Set(stoppingDevices.value)
    }
  }

  const showEmulator = async (uuid: string, index: string) => {
    const deviceKey = `${uuid}-${index}`
    if (showingDevices.value.has(deviceKey)) return
    showingDevices.value.add(deviceKey)
    showingDevices.value = new Set(showingDevices.value)

    try {
      const response = await withTimeoutAndRetry(
        () =>
          Service.operationEmulatorApiEmulatorOperatePost({
            emulatorId: uuid,
            operate: EmulatorOperateIn.operate.SHOW,
            index: index,
          }),
        { timeoutMs, retries: 1, retryDelayMs, label: `显示模拟器 ${uuid}#${index}` }
      )

      if (response.code === 200) {
        if (!rememberPendingOperation(response.operationId, uuid, index, 'show')) {
          message.info(response.message || `模拟器 ${index} 显示指令已受理`)
        }
      } else {
        message.error(response.message || '显示失败')
      }
      return response
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.error(`显示模拟器失败: ${errorMsg}`)
      message.error('显示模拟器失败')
      throw e
    } finally {
      showingDevices.value.delete(deviceKey)
      showingDevices.value = new Set(showingDevices.value)
    }
  }

  const selectEmulatorPath = async (uuid: string) => {
    try {
      if (!window.electronAPI) {
        message.error('文件选择功能不可用,请在 Electron 环境中运行')
        return
      }

      const editData = getEditingData(uuid)
      if (!editData) return

      const paths = await window.electronAPI.selectFile([
        { name: '可执行文件', extensions: ['exe'] },
        { name: '所有文件', extensions: ['*'] },
      ])

      if (paths && paths.length > 0) {
        editData.path = paths[0]
        await handleSaveChange(uuid, 'path', paths[0])

        const newPath = getEditingData(uuid)?.path || ''
        if (paths[0] !== newPath && newPath) {
          message.info(`路径已自动调整: ${paths[0]} -> ${newPath}`)
        } else {
          message.success('模拟器路径选择成功')
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`选择模拟器路径失败: ${errorMsg}`)
      message.error('选择文件失败')
    }
  }

  const onTabChange = async (key: string) => {
    activeKey.value = key
    saveActiveKey(key)
    if (emulatorIndex.value.some(e => e.uid === key)) {
      await loadDevices(key)
    }
  }

  const onEmulatorsLoaded = async () => {
    if (emulatorIndex.value.length > 0) {
      const savedKey = activeKey.value
      const isValidKey = emulatorIndex.value.some(e => e.uid === savedKey)

      if (!savedKey || !isValidKey) {
        activeKey.value = emulatorIndex.value[0].uid
        saveActiveKey(activeKey.value)
      }
      await loadDevices(activeKey.value)
    }
  }

  const recordingBossKeyMap = ref<Map<string, boolean>>(new Map())
  const recordedKeysMap = ref<Map<string, Set<string>>>(new Map())

  const startRecordBossKey = (uuid: string) => {
    const existingRecording = Array.from(recordingBossKeyMap.value.entries()).find(
      ([, recording]) => recording
    )?.[0]
    if (existingRecording && existingRecording !== uuid) {
      message.warning('请先完成当前老板键录制')
      return
    }
    const editData = getEditingData(uuid)
    if (editData && editData.type === 'mumu') {
      message.warning('MuMu 模拟器不支持老板键')
      return
    }
    recordingBossKeyMap.value.set(uuid, true)
    recordedKeysMap.value.set(uuid, new Set())
    bossKeyInputMap.value[uuid] = ''
    message.info('请按下快捷键组合（按 Esc 取消）')
  }

  const stopRecordBossKey = (uuid: string) => {
    recordingBossKeyMap.value.delete(uuid)
    recordedKeysMap.value.delete(uuid)
    delete bossKeyInputMap.value[uuid]
  }

  const cancelRecordBossKey = (uuid: string) => {
    recordingBossKeyMap.value.delete(uuid)
    recordedKeysMap.value.delete(uuid)
    delete bossKeyInputMap.value[uuid]
    message.info('已取消录制')
  }

  const handleKeyDown = (event: KeyboardEvent) => {
    const recordingUuid = Array.from(recordingBossKeyMap.value.entries()).find(
      ([, recording]) => recording
    )?.[0]

    if (!recordingUuid) return

    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      cancelRecordBossKey(recordingUuid)
      return
    }

    if (event.isComposing || event.keyCode === 229) {
      event.preventDefault()
      return
    }

    event.preventDefault()
    event.stopPropagation()

    const keys: string[] = []
    if (event.ctrlKey) keys.push('Ctrl')
    if (event.shiftKey) keys.push('Shift')
    if (event.altKey) keys.push('Alt')
    if (event.metaKey) keys.push('Meta')

    const mainKey = event.key
    const isModifier = ['Control', 'Shift', 'Alt', 'Meta'].includes(mainKey)
    if (!isModifier) {
      const displayKey = mainKey.length === 1 ? mainKey.toUpperCase() : mainKey
      keys.push(displayKey)
    }

    if (keys.length > 0) {
      recordedKeysMap.value.set(recordingUuid, new Set(keys))
    }
  }

  const handleKeyUp = async (event: KeyboardEvent) => {
    const recordingUuid = Array.from(recordingBossKeyMap.value.entries()).find(
      ([, recording]) => recording
    )?.[0]

    if (!recordingUuid) return

    event.preventDefault()
    event.stopPropagation()

    const recordedKeys = recordedKeysMap.value.get(recordingUuid)
    if (!recordedKeys || recordedKeys.size === 0) return

    const modifiers = new Set(['Ctrl', 'Shift', 'Alt', 'Meta'])
    const hasMainKey = Array.from(recordedKeys).some(k => !modifiers.has(k))
    if (!hasMainKey) return

    const keyCombo = Array.from(recordedKeys).join('+')
    const editData = getEditingData(recordingUuid)
    if (editData) {
      editData.boss_keys = [keyCombo]
      bossKeyInputMap.value[recordingUuid] = keyCombo
      message.success(`老板键已设置为: ${keyCombo}`)
      await handleSaveChange(recordingUuid, 'boss_keys', [keyCombo])
    }
    recordingBossKeyMap.value.delete(recordingUuid)
    recordedKeysMap.value.delete(recordingUuid)
  }

  const handleSetBossKey = async (uuid: string) => {
    if (recordingBossKeyMap.value.get(uuid)) return
    const editData = getEditingData(uuid)
    if (editData && editData.type === 'mumu') {
      message.warning('MuMu 模拟器不支持老板键')
      return
    }

    const bossKeyInput = bossKeyInputMap.value[uuid] || ''
    if (bossKeyInput.trim()) {
      if (editData) {
        editData.boss_keys = [bossKeyInput.trim()]
        message.success(`老板键已设置为: ${bossKeyInput.trim()}`)
        await handleSaveChange(uuid, 'boss_keys', [bossKeyInput.trim()])
      }
    }
  }

  const handleBossKeyInputChange = (uuid: string) => {
    const bossKeyInput = bossKeyInputMap.value[uuid] || ''
    const editData = getEditingData(uuid)
    if (editData) {
      if (bossKeyInput.trim()) {
        editData.boss_keys = [bossKeyInput.trim()]
      } else {
        editData.boss_keys = []
      }
    }
  }

  useEventListener(document, 'keydown', handleKeyDown)
  useEventListener(document, 'keyup', handleKeyUp)
  useEventListener(window, 'blur', () => {
    const recordingUuid = Array.from(recordingBossKeyMap.value.entries()).find(
      ([, recording]) => recording
    )?.[0]
    if (recordingUuid) {
      cancelRecordBossKey(recordingUuid)
      message.info('窗口失焦，已取消老板键录制')
    }
  })

  onUnmounted(() => {
    disposed = true
    stopPolling()
    pendingOperations.clear()
    unsubscribe(emulatorNoticeSubscriptionId)
  })

  return {
    loading,
    searching,
    emulatorIndex,
    emulatorData,
    searchResults,
    showSearchModal,
    devicesData,
    loadingDevices,
    startingDevices,
    stoppingDevices,
    showingDevices,
    editingDataMap,
    savingMap,
    bossKeyInputMap,
    activeKey,
    pollingTimer,
    pollingErrors,
    recordingBossKeyMap,
    loadEmulators,
    refreshEmulatorConfig,
    getEditingData,
    handleSaveChange,
    handleAdd,
    handleDelete,
    handleSearch,
    handleImportFromSearch,
    loadDevices,
    startEmulator,
    stopEmulator,
    showEmulator,
    selectEmulatorPath,
    onTabChange,
    onEmulatorsLoaded,
    syncNameToDisplay,
    startPolling,
    stopPolling,
    startRecordBossKey,
    stopRecordBossKey,
    cancelRecordBossKey,
    handleSetBossKey,
    handleBossKeyInputChange,
    saveActiveKey,
    getDeviceActionState,
    getEmulatorCapabilities,
  }
}
