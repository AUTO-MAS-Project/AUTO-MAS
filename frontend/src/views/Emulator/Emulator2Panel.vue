<script setup lang="ts">
/**
 * Emulator 2.0 面板。
 *
 * 与旧配置的区别：一条配置纳管多条模拟器路径，各家的实例合并成一张设备表。
 * 设备号由本配置统一编排，脚本绑定用的就是它；模拟器自己的实例号另外显示，
 * 因为两者不一定对得上（实例被删过就会错开）。
 */
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  AppstoreOutlined,
  DeleteOutlined,
  LoadingOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  PoweroffOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

import { Emulator20Service, EmulatorOperateIn, Service } from '@/api'
import { usePerformanceStore } from '@/stores/performance'
import { invalidateEmulatorDeviceOptions } from '@/composables/useEmulatorDeviceOptions'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR_OPERATION_FINISHED,
  WS_ID_EMULATOR_MANAGER,
  type WSEmulatorOperationData,
} from '@/services/websocket/types'
import {
  DeviceStatus,
  POLL_ACTIVE_MS,
  POLL_IDLE_MS,
  actionAvailability,
  effectiveStatus,
  isTransitional,
  makePending,
  mergeSettings,
  mergeStatus,
  pendingSettled,
  type Pending,
  type PendingOp,
} from './emulator2Status'
import type {
  Emulator2AffectedScript,
  Emulator2BatchResult,
  Emulator2DeviceItem,
  Emulator2PathItem,
  Emulator2SearchItem,
  Emulator2SettingField,
} from '@/api'

/** ``active``：所在页签是否被选中。不在前台的页签不轮询，也不用抢子进程。 */
const props = withDefaults(defineProps<{ emulatorId: string; active?: boolean }>(), {
  active: true,
})

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const performanceStore = usePerformanceStore()

/** 首次加载：还没有任何行可以显示，表格位置转圈 */
const loading = ref(false)
/** 后台刷新（设置那一批）：表格照常可用，只在标题旁转一个小圈 */
const refreshing = ref(false)
const paths = ref<Emulator2PathItem[]>([])
const devices = ref<Emulator2DeviceItem[]>([])
/** 已经拉过设置：在此之前设置列显示成加载中而不是破折号 */
const settingsLoaded = ref(false)
/**
 * 表里现在这份状态是哪个时刻发出的请求取到的。
 *
 * 状态轮询和设置全量会交错在飞：全量那趟后端先取状态再逐台读设置，响应回来时
 * 状态已经比表里的旧。谁发得晚谁的状态算数，发得早却到得晚的只能收下设置。
 */
let statusRequestedAt = 0

/** 路径管理弹窗。入口在上层配置栏的「路径」那一行，与旧样式保持一致。 */
const pathsOpen = ref(false)
const openPaths = () => {
  pathsOpen.value = true
}

const searchOpen = ref(false)
const searching = ref(false)
const searchResults = ref<Emulator2SearchItem[]>([])
const selectedPaths = ref<string[]>([])
const adding = ref(false)

const removeOpen = ref(false)
const removing = ref(false)
const removeTarget = ref<Emulator2PathItem | null>(null)
const removeSlots = ref<string[]>([])
const removeAffected = ref<Emulator2AffectedScript[]>([])

const addableResults = computed(() => searchResults.value.filter(item => item.supported))

/** 模拟器类型 → 用户看得懂的名字。界面上不该出现 ldplayer / mumu 这种内部名。 */
const typeLabel = (type: string | undefined) => {
  if (!type) return ''
  const key = `emulator.type.${type}`
  const text = t(key)
  return text === key ? type : text
}

/** 判定原因枚举 → 用户文案。后端只给枚举，措辞在这里定。 */
const reasonLabel = (reason: string) => {
  const key = `emulator2.reason.${reason}`
  const text = t(key)
  return text === key ? reason : text
}

const reasonText = (item: Emulator2SearchItem) => reasonLabel(item.reason)

const reasonColor = (reason: string) => {
  if (reason === 'ok') return 'success'
  if (reason === 'planned') return 'processing'
  return 'default'
}

/**
 * 拉取设备列表。
 *
 * 设备表要的东西分两种速度：在线状态几秒就可能变，四项设置几乎不变。所以：
 *
 * - ``withSettings=false`` 只取状态（一次问全，不逐台读配置），给轮询用，几百毫秒；
 * - ``withSettings=true`` 连设置一起读，进页面、改完设置、模拟器状态变了才跑。
 *
 * 只带状态的结果**并进**现有行而不是整表替换，这样已经拉到的设置不会闪成破折号。
 * ``silent`` 供后台轮询用：失败也不弹提示——网络抖一下就在用户脸上弹一个红条毫无意义，
 * 下一轮自然会补上。
 */
const loadDevices = async ({
  silent = false,
  withSettings = true,
}: { silent?: boolean; withSettings?: boolean } = {}): Promise<boolean> => {
  if (!props.emulatorId) return false
  const firstLoad = !devices.value.length && !paths.value.length
  const showLoading = !silent && firstLoad
  // 设置那一批在后台补：表格照常可用，只在标题旁转个小圈；状态轮询什么都不转
  const showRefreshing = withSettings && !firstLoad
  if (showLoading) loading.value = true
  if (showRefreshing) refreshing.value = true
  const requestedAt = Date.now()
  try {
    const response = await Emulator20Service.listDevicesApiEmulator2DevicesPost({
      emulatorId: props.emulatorId,
      withSettings,
    })
    if (response.code !== 200) {
      if (!silent) message.error(response.message)
      return false
    }
    paths.value = response.paths || []
    const fresh = response.devices || []
    const stale = requestedAt < statusRequestedAt
    if (withSettings) {
      devices.value = stale ? mergeSettings(devices.value, fresh) : fresh
      settingsLoaded.value = true
    } else if (!stale) {
      const { rows, changed } = mergeStatus(devices.value, fresh)
      devices.value = rows
      // 状态一变就把设置也补一遍：模拟器关掉时会把自己那份配置写回去，
      // 启动前稳定模式 / 配置守卫也可能改过它
      if (changed.length && settingsLoaded.value) scheduleSettingsRefresh()
    }
    if (!stale) statusRequestedAt = requestedAt
    settlePending()
    return true
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`加载设备列表失败: ${detail}`)
    if (!silent) message.error(t('emulator2.toast.loadFailed'))
    return false
  } finally {
    if (showLoading) loading.value = false
    if (showRefreshing) refreshing.value = false
  }
}

/** 先把状态拉回来让表格立刻出现，设置随后补上——用户不必盯着转圈等那批子进程 */
const loadAll = async () => {
  const ok = await loadDevices({ withSettings: false })
  if (ok) await loadDevices({ silent: true, withSettings: true })
}

let settingsRefreshTimer: ReturnType<typeof setTimeout> | null = null
const scheduleSettingsRefresh = () => {
  if (settingsRefreshTimer) return
  settingsRefreshTimer = setTimeout(() => {
    settingsRefreshTimer = null
    void loadDevices({ silent: true, withSettings: true })
  }, 1500)
}

const openSearch = async () => {
  searchOpen.value = true
  selectedPaths.value = []
  searching.value = true
  try {
    const response = await Emulator20Service.searchEmulatorsApiEmulator2SearchPost({
      emulatorId: props.emulatorId,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    searchResults.value = response.emulators || []
    selectedPaths.value = addableResults.value.map(item => item.installPath)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`搜索模拟器失败: ${detail}`)
    message.error(t('emulator2.toast.searchFailed'))
  } finally {
    searching.value = false
  }
}

const confirmAdd = async () => {
  if (!selectedPaths.value.length) return
  adding.value = true
  let added = 0
  try {
    for (const installPath of selectedPaths.value) {
      const item = searchResults.value.find(row => row.installPath === installPath)
      const response = await Emulator20Service.addPathApiEmulator2PathsAddPost({
        emulatorId: props.emulatorId,
        installPath,
        alias: item?.alias || null,
      })
      if (response.code === 200 && response.ok) {
        added += 1
      } else {
        message.warning(
          `${item?.alias || installPath}: ${
            response.reason ? reasonLabel(response.reason) : response.message
          }`
        )
      }
    }
  } finally {
    adding.value = false
  }
  if (added > 0) {
    message.success(t('emulator2.toast.addOk', { count: added }))
    searchOpen.value = false
    invalidateEmulatorDeviceOptions()
    await loadDevices({ silent: true })
  }
}

const openRemove = async (path: Emulator2PathItem) => {
  removeTarget.value = path
  removeSlots.value = path.slots || []
  removeAffected.value = []
  removeOpen.value = true
  try {
    const response = await Emulator20Service.previewRemovePathApiEmulator2PathsRemovePreviewPost({
      emulatorId: props.emulatorId,
      pathId: path.pathId,
    })
    if (response.code === 200) {
      removeSlots.value = response.slots || []
      removeAffected.value = response.affectedScripts || []
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`预览移除影响失败: ${detail}`)
  }
}

const confirmRemove = async () => {
  if (!removeTarget.value) return
  removing.value = true
  try {
    const response = await Emulator20Service.removePathApiEmulator2PathsRemovePost({
      emulatorId: props.emulatorId,
      pathId: removeTarget.value.pathId,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.removeOk'))
    removeOpen.value = false
    invalidateEmulatorDeviceOptions()
    await loadDevices({ silent: true })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`移除模拟器路径失败: ${detail}`)
    message.error(t('emulator2.toast.removeFailed'))
  } finally {
    removing.value = false
  }
}

const runningAffected = computed(() => removeAffected.value.filter(item => item.running))

// ---- 新建 / 删除实例 ----

const createOpen = ref(false)
const creating = ref(false)
const createPathId = ref('')
const createName = ref('')

const pathSelectOptions = computed(() =>
  paths.value.map(item => ({
    value: item.pathId,
    label: item.alias + ' (' + typeLabel(item.type) + ')',
  }))
)

const openCreate = () => {
  createPathId.value = paths.value[0]?.pathId ?? ''
  createName.value = ''
  createOpen.value = true
}

const confirmCreate = async () => {
  if (!createPathId.value) return
  const path = paths.value.find(item => item.pathId === createPathId.value)
  const pendingKey = `pending-${Date.now()}`

  // 弹窗立刻关掉，表尾出现一行「新建中」——新建要跑好几秒，把用户堵在弹窗里没意义
  createOpen.value = false
  pendingRows.value = [
    ...pendingRows.value,
    {
      pendingKey,
      slot: '',
      pathId: createPathId.value,
      alias: path?.alias ?? '',
      realType: path?.type ?? '',
      nativeIndex: '',
      availability: 'pending',
      title: createName.value || '',
      status: 5,
      adbAddress: '',
      settings: {},
      stableMode: false,
      stableUnsafe: [],
    } as DeviceRow,
  ]

  try {
    const response = await Emulator20Service.createInstanceApiEmulator2InstancesCreatePost({
      emulatorId: props.emulatorId,
      pathId: createPathId.value,
      name: createName.value || null,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.createOk', { slot: response.slot }))
    invalidateEmulatorDeviceOptions()
    await loadDevices({ silent: true })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error('新建实例失败: ' + detail)
    message.error(t('emulator2.toast.createFailed'))
  } finally {
    // 真实那一行这时已经在 devices 里了，占位行退场
    pendingRows.value = pendingRows.value.filter(row => row.pendingKey !== pendingKey)
  }
}

const deleteOpen = ref(false)
const deleting = ref(false)
const deleteTarget = ref<Emulator2DeviceItem | null>(null)
const deleteAffected = ref<Emulator2AffectedScript[]>([])

const openDelete = async (device: Emulator2DeviceItem) => {
  deleteTarget.value = device
  deleteAffected.value = []
  deleteOpen.value = true
  try {
    const response =
      await Emulator20Service.previewDeleteInstanceApiEmulator2InstancesDeletePreviewPost({
        emulatorId: props.emulatorId,
        slot: device.slot,
      })
    if (response.code === 200) deleteAffected.value = response.affectedScripts || []
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error('预览删除影响失败: ' + detail)
  }
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  const slot = deleteTarget.value.slot

  // 同样不把用户堵在弹窗里：关掉弹窗，那一行原地转圈显示「删除中」
  deleteOpen.value = false
  setPending(slot, 'deleting', deleteTarget.value.status ?? DeviceStatus.NOT_FOUND)

  try {
    const response = await Emulator20Service.deleteInstanceApiEmulator2InstancesDeletePost({
      emulatorId: props.emulatorId,
      slot,
    })
    if (response.code !== 200 || !response.ok) {
      message.error(response.message)
      return
    }
    message.success(t('emulator2.toast.deleteOk'))
    invalidateEmulatorDeviceOptions()
    // 确认没了才从列表里去掉；后端已经给该设备号写了墓碑，重新拉也不会再出现
    devices.value = devices.value.filter(item => item.slot !== slot)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error('删除实例失败: ' + detail)
    message.error(t('emulator2.toast.deleteFailed'))
  } finally {
    clearPending(slot)
  }
}

const FIELDS = ['width', 'height', 'dpi', 'cpu', 'memoryMb', 'fps'] as const
type FieldName = (typeof FIELDS)[number]
type FieldForm = Record<FieldName, number | null>

const emptyForm = (): FieldForm => ({
  width: null,
  height: null,
  dpi: null,
  cpu: null,
  memoryMb: null,
  fps: null,
})

const fieldOf = (device: Emulator2DeviceItem, name: FieldName): Emulator2SettingField | undefined =>
  device.settings?.[name]

const fieldValue = (device: Emulator2DeviceItem, name: FieldName) =>
  fieldOf(device, name)?.value ?? null

/** 字段名 → 用户文案。后端只给字段名，措辞在这里定。 */
const fieldLabel = (name: string) => {
  const key = `emulator2.field.${name}`
  const text = t(key)
  return text === key ? name : text
}

/** 表里显示的值。空着的显示破折号，而不是 0 或 null。 */
const fieldText = (device: Emulator2DeviceItem, name: FieldName) => {
  const value = fieldValue(device, name)
  return value === null ? '—' : String(value)
}

const resolutionText = (device: Emulator2DeviceItem) => {
  const w = fieldValue(device, 'width')
  const h = fieldValue(device, 'height')
  return w === null || h === null ? '—' : `${w} × ${h}`
}

// ---- 单台设置 ----

const settingsOpen = ref(false)
const savingSettings = ref(false)
const settingsTarget = ref<Emulator2DeviceItem | null>(null)
const settingsForm = ref<FieldForm>(emptyForm())
/** 表单打开时看到的值。保存时带回后端做冲突比对，避免盖掉别人的改动。 */
const settingsBaseline = ref<FieldForm>(emptyForm())

const openSettings = (device: Emulator2DeviceItem) => {
  settingsTarget.value = device
  const form = emptyForm()
  for (const name of FIELDS) form[name] = fieldValue(device, name)
  settingsForm.value = { ...form }
  settingsBaseline.value = { ...form }
  settingsOpen.value = true
}

/** 只提交用户真正改过的字段——其余键在文件里原样保留。 */
const changedFields = computed(() => {
  const changes: Record<string, number> = {}
  for (const name of FIELDS) {
    const value = settingsForm.value[name]
    if (value === null || value === undefined) continue
    if (value === settingsBaseline.value[name]) continue
    changes[name] = value
  }
  return changes
})

const confirmSettings = async () => {
  if (!settingsTarget.value) return
  const changes = changedFields.value
  if (!Object.keys(changes).length) {
    settingsOpen.value = false
    return
  }
  savingSettings.value = true
  try {
    const response = await Emulator20Service.applySettingsApiEmulator2SettingsApplyPost({
      emulatorId: props.emulatorId,
      slot: settingsTarget.value.slot,
      changes,
      expected: settingsBaseline.value,
    })
    if (response.code !== 200 || !response.ok) {
      // 冲突是最常见的失败，后端只给字段名；文案在这里按词表拼，
      // 免得把后端的中文原句直接甩进英文 / 日文界面
      const conflicts = response.conflicts || []
      message.error(
        conflicts.length
          ? t('emulator2.toast.settingsConflict', {
              fields: conflicts.map(fieldLabel).join(' / '),
            })
          : response.message
      )
      return
    }
    message.success(t('emulator2.toast.settingsOk'))
    settingsOpen.value = false
    await loadDevices({ silent: true })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`保存设置失败: ${detail}`)
    message.error(t('emulator2.toast.settingsFailed'))
  } finally {
    savingSettings.value = false
  }
}

// ---- 批量设置 ----

const batchOpen = ref(false)
const batchSaving = ref(false)
const batchForm = ref<FieldForm>(emptyForm())

/** 批量写入里失败的那几台，连原因一起显示在弹窗内。 */
const batchFailures = ref<Emulator2BatchResult[]>([])

const openBatch = () => {
  batchForm.value = emptyForm()
  batchFailures.value = []
  batchOpen.value = true
}

/** 留空的字段不下发——批量设置只改用户填了的那几项。 */
const batchChanges = computed(() => {
  const changes: Record<string, number> = {}
  for (const name of FIELDS) {
    const value = batchForm.value[name]
    if (value !== null && value !== undefined) changes[name] = value
  }
  return changes
})

const confirmBatch = async () => {
  const changes = batchChanges.value
  if (!Object.keys(changes).length) return
  batchSaving.value = true
  try {
    const response = await Emulator20Service.applySettingsToAllApiEmulator2SettingsApplyAllPost({
      emulatorId: props.emulatorId,
      changes,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    const failed = response.failCount ?? 0
    if (failed > 0) {
      // 只报「N 台失败」用户没法行动，把每台的原因一并列出来
      batchFailures.value = (response.results || []).filter(item => !item.ok)
      message.warning(
        t('emulator2.toast.batchPartial', {
          ok: response.okCount ?? 0,
          fail: failed,
        })
      )
    } else {
      batchFailures.value = []
      message.success(t('emulator2.toast.batchOk', { count: response.okCount ?? 0 }))
    }
    batchOpen.value = false
    await loadDevices({ silent: true })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`批量设置失败: ${detail}`)
    message.error(t('emulator2.toast.batchFailed'))
  } finally {
    batchSaving.value = false
  }
}

// ---- 启动 / 关闭 / 显示 / 隐藏 ----

/**
 * 行级过渡态：设备号 → 正在进行、还没等到结果的操作。
 *
 * 启动 / 关闭在后端是后台任务，接口一调用就返回，模拟器自己的状态要过一两秒才会变。
 * 那段空窗里照实显示「离线」，用户会以为没点上再点一次。所以点下去的那一刻就把这行
 * 记成过渡态：状态按目标显示、按钮按目标状态给，直到轮询看到模拟器真的动了、
 * 或者后端发来「操作结束」。判定规则都在 ``emulator2Status.ts`` 里。
 */
const pending = ref<Map<string, Pending>>(new Map())
/** 让依赖「现在几点」的过渡态判断能随轮询重新计算 */
const now = ref(Date.now())

const setPending = (slot: string, op: PendingOp, from: number) => {
  const next = new Map(pending.value)
  next.set(slot, makePending(op, from, Date.now()))
  pending.value = next
}

const clearPending = (slot: string) => {
  if (!pending.value.has(slot)) return
  const next = new Map(pending.value)
  next.delete(slot)
  pending.value = next
}

/** 轮询之后：目标状态已经看到、或者过期的过渡态就收掉 */
const settlePending = () => {
  now.value = Date.now()
  if (!pending.value.size) return
  const bySlot = new Map(devices.value.map(row => [row.slot, row]))
  for (const [slot, item] of pending.value) {
    const row = bySlot.get(slot)
    const polled = row?.status ?? DeviceStatus.NOT_FOUND
    if (!row || pendingSettled(item, polled, now.value)) clearPending(slot)
  }
}

/** 新建时还没有设备号，先在表尾占一行占位行，建好后由真实数据替换。 */
type DeviceRow = Emulator2DeviceItem & { pendingKey?: string }
const pendingRows = ref<DeviceRow[]>([])

const tableRows = computed<DeviceRow[]>(() => [...devices.value, ...pendingRows.value])

/** 占位行和删除 / 打开游戏中心这类没有目标状态的操作，在状态列直接写明在干什么 */
const rowLabel = (row: DeviceRow) => {
  if (row.pendingKey) return t('emulator2.busy.creating')
  const item = pending.value.get(row.slot)
  if (!item || item.to !== null) return ''
  if (item.op === 'deleting') return t('emulator2.busy.deleting')
  if (item.op === 'store') return t('emulator2.busy.openingStore')
  return t('emulator2.busy.operating')
}

const statusOf = (row: DeviceRow) => effectiveStatus(row, pending.value.get(row.slot), now.value)

const NO_ACTIONS = {
  start: false,
  stop: false,
  show: false,
  hide: false,
  store: false,
  settings: false,
  delete: false,
}

const actionsOf = (row: DeviceRow) =>
  row.pendingKey ? NO_ACTIONS : actionAvailability(row, pending.value.get(row.slot), now.value)

const OPERATION_OF: Record<string, PendingOp> = {
  [EmulatorOperateIn.operate.OPEN]: 'open',
  [EmulatorOperateIn.operate.CLOSE]: 'close',
  [EmulatorOperateIn.operate.SHOW]: 'show',
  [EmulatorOperateIn.operate.HIDE]: 'hide',
}

const operate = async (device: Emulator2DeviceItem, action: EmulatorOperateIn.operate) => {
  const op = OPERATION_OF[action] ?? 'show'
  setPending(device.slot, op, device.status ?? DeviceStatus.NOT_FOUND)
  try {
    const response = await Service.operationEmulatorApiEmulatorOperatePost({
      emulatorId: props.emulatorId,
      operate: action,
      index: device.slot,
    })
    if (response.code !== 200) {
      message.error(response.message)
      clearPending(device.slot)
      return
    }
    // 后端已经开始干活，马上盯一眼；之后轮询会按过渡态自动加快
    schedulePoll(POLL_ACTIVE_MS)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`操作设备 #${device.slot} 失败: ${detail}`)
    message.error(t('emulator2.toast.operateFailed'))
    clearPending(device.slot)
  }
}

// 雷电开了纯净模式之后 launcher 会把游戏中心从桌面藏掉，这是用户唯一的图形入口。
// 拉不起来后端回 ok=false 加一句说明（不是接口错误），照原话提示即可。
const openStore = async (device: Emulator2DeviceItem) => {
  setPending(device.slot, 'store', device.status ?? DeviceStatus.NOT_FOUND)
  try {
    const response = await Emulator20Service.openStoreApiEmulator2InstancesStoreOpenPost({
      emulatorId: props.emulatorId,
      slot: device.slot,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return
    }
    if (!response.ok) {
      message.warning(response.message)
      return
    }
    message.success(t('emulator2.toast.storeOpened'))
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`打开设备 #${device.slot} 的游戏中心失败: ${detail}`)
    message.error(t('emulator2.toast.storeOpenFailed'))
  } finally {
    clearPending(device.slot)
  }
}

/**
 * 后端「操作结束」：先把最新状态拉回来，再收掉过渡态。
 *
 * 顺序不能反：雷电关一台刚开的实例只要一两百毫秒，事件到的时候表里那行还写着
 * 「在线」，先收过渡态会让它闪回在线、关闭按钮又亮半秒。失败时刷新回来的就是
 * 真实状态，收掉过渡态刚好；失败原因由常驻的系统通知另外弹出。
 */
const onOperationFinished = async (data: WSEmulatorOperationData) => {
  if (data.emulatorId !== props.emulatorId) return
  await loadDevices({ silent: true, withSettings: true })
  // 只收自己那一次：启动中点了关闭，先结束的是启动，关闭那份过渡态还得留着
  if (pending.value.get(data.index)?.op === data.operate) clearPending(data.index)
}

const isReachable = (device: Emulator2DeviceItem) => device.availability === 'ok'

// ---- 稳定模式 ----
//
// 开关本身在上层的配置栏里（它是配置级设置，不该在设备表每行重复一遍）。
// 这里只提供「按当前配置把所有设备压到安全状态」的动作，由父组件在开关打开时调用。

/**
 * 记录配置守卫的基准。开关打开时调一次。
 *
 * 基准只取用户显式设过的字段——模拟器默认值和从没设过的项没有「应该是什么」可言。
 */
const captureBaselines = async (): Promise<number | null> => {
  try {
    const response = await Emulator20Service.captureBaselinesApiEmulator2GuardCapturePost({
      emulatorId: props.emulatorId,
    })
    if (response.code !== 200) {
      message.error(response.message)
      return null
    }
    return response.count ?? 0
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`记录配置基准失败: ${detail}`)
    message.error(t('emulator2.toast.guardFailed'))
    return null
  }
}

const applyStableMode = async (): Promise<number | null> => {
  try {
    const response = await Emulator20Service.applyStableModeApiEmulator2StableModeApplyPost({
      emulatorId: props.emulatorId,
      slots: [],
    })
    if (response.code !== 200) {
      message.error(response.message)
      return null
    }
    await loadDevices({ silent: true })
    return response.okCount ?? 0
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    logger.error(`应用稳定模式失败: ${detail}`)
    message.error(t('emulator2.toast.stableFailed'))
    return null
  }
}

/**
 * 按钮为什么用不了。
 *
 * 之前不管什么原因都提示「实例未关闭」——设备明明不可达或处于错误状态，
 * 却被告知「它还在运行」，等于给了一句错的诊断。这里按实际原因分开说。
 */
const blockedReason = (device: DeviceRow) => {
  if (device.availability === 'unavailable') return t('emulator2.blocked.unavailable')
  if (device.availability !== 'ok') return t('emulator2.blocked.missing')
  const status = statusOf(device)
  if (status === DeviceStatus.ERROR) return t('emulator2.blocked.error')
  if (isTransitional(status) || pending.value.has(device.slot)) {
    return t('emulator2.blocked.busy')
  }
  if (status !== DeviceStatus.OFFLINE && status !== DeviceStatus.NOT_FOUND) {
    return t('emulator2.deleteNeedsOffline')
  }
  return ''
}

/** 设备状态 → Tag。availability 优先：这次没枚举到就不该显示成离线。 */
const deviceStatus = (device: DeviceRow) => {
  if (device.availability === 'unavailable') {
    return { color: 'default', text: t('emulator2.status.unavailable') }
  }
  if (device.availability === 'missing') {
    return { color: 'warning', text: t('emulator2.status.missing') }
  }
  const map: Record<number, { color: string; text: string }> = {
    [DeviceStatus.ONLINE]: { color: 'success', text: t('emulator.deviceStatus.online') },
    [DeviceStatus.OFFLINE]: { color: 'default', text: t('emulator.deviceStatus.offline') },
    [DeviceStatus.STARTING]: { color: 'processing', text: t('emulator.deviceStatus.starting') },
    [DeviceStatus.CLOSING]: { color: 'processing', text: t('emulator.deviceStatus.closing') },
    [DeviceStatus.ERROR]: { color: 'error', text: t('emulator.deviceStatus.error') },
    [DeviceStatus.NOT_FOUND]: { color: 'default', text: t('emulator.deviceStatus.notFound') },
  }
  return (
    map[statusOf(device)] ?? {
      color: 'default',
      text: t('emulator.deviceStatus.unknown'),
    }
  )
}

/**
 * 表格滚动。
 *
 * 页面本身不滚（上层把高度钉死了），行数一多表格就会被裁掉、连底部的提示都看不见。
 * 所以量出表格区域实际有多高，把表体钉成那么高、表头固定、在表格内部滚；
 * 行少时表体撑不满也无妨，不会留下一片空白。
 */
const TABLE_HEADER_HEIGHT = 39
const TABLE_MIN_BODY_HEIGHT = 160
const tableArea = ref<HTMLElement | null>(null)
const tableBodyHeight = ref<number | undefined>(undefined)
let resizeObserver: ResizeObserver | null = null

const measureTable = () => {
  const area = tableArea.value
  if (!area) return
  const available = Math.floor(area.clientHeight) - TABLE_HEADER_HEIGHT
  tableBodyHeight.value = available > TABLE_MIN_BODY_HEIGHT ? available : TABLE_MIN_BODY_HEIGHT
}

const tableScroll = computed(() => ({
  x: 'max-content' as const,
  y: tableBodyHeight.value,
}))

const deviceColumns = computed(() => [
  { title: t('emulator2.colSource'), key: 'source', width: 140 },
  { title: t('emulator2.colSlot'), dataIndex: 'slot', key: 'slot', width: 80 },
  { title: t('emulator.colStatus'), key: 'status', width: 96 },
  {
    title: t('emulator.colName'),
    dataIndex: 'title',
    key: 'title',
    ellipsis: true,
  },
  {
    title: t('emulator.colAdb'),
    dataIndex: 'adbAddress',
    key: 'adb',
    ellipsis: true,
  },
  { title: t('emulator2.colResolution'), key: 'resolution', width: 110 },
  { title: t('emulator2.colDpi'), key: 'dpi', width: 72 },
  { title: t('emulator2.colCpu'), key: 'cpu', width: 64 },
  { title: t('emulator2.colMemory'), key: 'memory', width: 96 },
  { title: t('emulator2.colFps'), key: 'fps', width: 72 },
  { title: t('emulator.colAction'), key: 'action', width: 216 },
])

watch(
  () => props.emulatorId,
  () => {
    devices.value = []
    paths.value = []
    settingsLoaded.value = false
    void loadAll()
  }
)

/**
 * 状态轮询。
 *
 * 只拉状态不读设置，一轮几百毫秒。没什么在变时 5 秒一轮——真正需要跟进的是界面之外
 * 的变化（用户自己在模拟器里开了一台）；有行处在启动中 / 关闭中时 1 秒一轮，
 * 让过渡态尽快落定。页签不在前台、窗口在后台时不轮询。
 */
let pollTimer: ReturnType<typeof setTimeout> | null = null
let polling = false
/** 卸载后正在飞的那一轮回来时不能再排下一轮，否则计时器会在组件没了之后一直跑 */
let disposed = false

const shouldPoll = () => !disposed && props.active && !performanceStore.isBackgrounded

const hasTransitionalRow = () =>
  devices.value.some(row => isTransitional(statusOf(row)) || pending.value.has(row.slot))

const schedulePoll = (delay: number) => {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
  if (!shouldPoll()) return
  pollTimer = setTimeout(() => {
    pollTimer = null
    void pollOnce()
  }, delay)
}

const pollOnce = async () => {
  if (!shouldPoll()) return
  if (polling) {
    schedulePoll(POLL_ACTIVE_MS)
    return
  }
  polling = true
  try {
    // 新建 / 删除进行中列表正被我们自己改，这一轮跳过
    if (!pendingRows.value.length) {
      await loadDevices({ silent: true, withSettings: false })
    }
  } finally {
    polling = false
  }
  schedulePoll(hasTransitionalRow() ? POLL_ACTIVE_MS : POLL_IDLE_MS)
}

const stopPolling = () => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

// 页签切走 / 窗口进后台时停掉轮询，回来立即拉一次再继续
watch(
  () => [props.active, performanceStore.isBackgrounded] as const,
  () => {
    if (shouldPoll()) {
      void pollOnce()
    } else {
      stopPolling()
    }
  }
)

let operationSubscription: string | null = null

onMounted(() => {
  void loadAll().then(() => schedulePoll(POLL_IDLE_MS))
  operationSubscription = subscribe(
    { id: WS_ID_EMULATOR_MANAGER, type: WS_EMULATOR_OPERATION_FINISHED },
    envelope => void onOperationFinished(envelope.data)
  )
  if (tableArea.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(measureTable)
    resizeObserver.observe(tableArea.value)
  }
  measureTable()
})

onUnmounted(() => {
  disposed = true
  stopPolling()
  if (settingsRefreshTimer) clearTimeout(settingsRefreshTimer)
  if (operationSubscription) unsubscribe(operationSubscription)
  resizeObserver?.disconnect()
})

defineExpose({ reload: loadAll, applyStableMode, captureBaselines, openPaths })
</script>

<template>
  <div class="emulator2-panel">
    <!-- 模拟器路径管理：整块搬进二级弹窗，主页面只留设备表 -->
    <a-modal
      v-model:open="pathsOpen"
      :title="t('emulator2.pathsTitle')"
      width="760px"
      :footer="null"
    >
      <div class="section-header" style="margin-top: 0">
        <span class="section-hint">{{ t('emulator2.pathsHint') }}</span>
        <a-button size="small" type="primary" ghost :icon="h(SearchOutlined)" @click="openSearch">
          {{ t('emulator2.searchAndAdd') }}
        </a-button>
      </div>

      <a-empty v-if="!paths.length" :description="t('emulator2.noPath')">
        <a-button type="primary" :icon="h(PlusOutlined)" @click="openSearch">
          {{ t('emulator2.searchAndAdd') }}
        </a-button>
      </a-empty>

      <div v-else class="path-grid">
        <a-card v-for="path in paths" :key="path.pathId" size="small" class="path-card">
          <template #title>
            <a-space :size="6">
              <a-tag color="purple">{{ typeLabel(path.type) }}</a-tag>
              <span class="path-alias">{{ path.alias }}</span>
              <span class="path-version">{{ path.version }}</span>
            </a-space>
          </template>
          <template #extra>
            <a-button type="text" size="small" danger @click="openRemove(path)">
              {{ t('emulator2.removePath') }}
            </a-button>
          </template>
          <div class="path-line">{{ path.installPath }}</div>
          <div class="path-sub">
            {{
              t('emulator2.slotRange', {
                slots: (path.slots ?? []).map(s => `#${s}`).join(' ') || '—',
              })
            }}
          </div>
        </a-card>
      </div>
    </a-modal>

    <div class="section-header">
      <h3>
        {{ t('emulator.deviceList') }}
        <span class="section-hint">{{ t('emulator2.deviceHint') }}</span>
        <LoadingOutlined v-if="refreshing" class="section-refreshing" />
      </h3>
      <a-space :size="8">
        <a-button
          size="small"
          type="primary"
          ghost
          :icon="h(PlusOutlined)"
          :disabled="!paths.length"
          @click="openCreate"
        >
          {{ t('emulator2.createInstance') }}
        </a-button>
        <a-button
          size="small"
          :icon="h(SettingOutlined)"
          :disabled="!devices.length"
          @click="openBatch"
        >
          {{ t('emulator2.batchSettings') }}
        </a-button>
      </a-space>
    </div>

    <div ref="tableArea" class="table-area">
      <a-spin :spinning="loading" wrapper-class-name="table-spin">
        <a-empty
          v-if="!tableRows.length"
          :description="loading ? '' : t('emulator.noDevice')"
          class="table-empty"
        />
        <a-table
          v-else
          class="device-table"
          :data-source="tableRows"
          :columns="deviceColumns"
          :row-key="(record: DeviceRow) => record.pendingKey ?? record.slot"
          :pagination="false"
          size="small"
          :scroll="tableScroll"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'source'">
              <div class="source-cell">
                <a-tag color="purple">{{ typeLabel(record.realType) }}</a-tag>
                <span class="source-sub">
                  {{ record.alias }} ·
                  {{ t('emulator2.nativeIndex', { index: record.nativeIndex }) }}
                </span>
              </div>
            </template>
            <template v-else-if="column.key === 'slot'">
              <strong v-if="record.slot">#{{ record.slot }}</strong>
              <span v-else>—</span>
            </template>
            <template v-else-if="column.key === 'status'">
              <a-tag v-if="rowLabel(record)" color="processing">
                <LoadingOutlined style="margin-right: 4px" />
                {{ rowLabel(record) }}
              </a-tag>
              <a-tag v-else :color="deviceStatus(record).color">
                <LoadingOutlined
                  v-if="isTransitional(statusOf(record))"
                  style="margin-right: 4px"
                />
                {{ deviceStatus(record).text }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'resolution'">
              <span v-if="settingsLoaded || record.pendingKey">{{ resolutionText(record) }}</span>
              <span v-else class="cell-loading">…</span>
            </template>
            <template v-else-if="column.key === 'dpi'">
              <span v-if="settingsLoaded || record.pendingKey">{{ fieldText(record, 'dpi') }}</span>
              <span v-else class="cell-loading">…</span>
            </template>
            <template v-else-if="column.key === 'cpu'">
              <span v-if="settingsLoaded || record.pendingKey">{{ fieldText(record, 'cpu') }}</span>
              <span v-else class="cell-loading">…</span>
            </template>
            <template v-else-if="column.key === 'memory'">
              <span v-if="settingsLoaded || record.pendingKey">{{
                fieldText(record, 'memoryMb')
              }}</span>
              <span v-else class="cell-loading">…</span>
            </template>
            <template v-else-if="column.key === 'fps'">
              <span v-if="settingsLoaded || record.pendingKey">{{ fieldText(record, 'fps') }}</span>
              <span v-else class="cell-loading">…</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space :size="4">
                <a-tooltip :title="t('emulator2.start')">
                  <a-button
                    size="small"
                    type="text"
                    :icon="h(PlayCircleOutlined)"
                    :loading="pending.get(record.slot)?.op === 'open'"
                    :disabled="!actionsOf(record).start"
                    @click="operate(record, EmulatorOperateIn.operate.OPEN)"
                  />
                </a-tooltip>
                <a-tooltip :title="t('emulator2.stop')">
                  <a-button
                    size="small"
                    type="text"
                    :icon="h(PoweroffOutlined)"
                    :loading="pending.get(record.slot)?.op === 'close'"
                    :disabled="!actionsOf(record).stop"
                    @click="operate(record, EmulatorOperateIn.operate.CLOSE)"
                  />
                </a-tooltip>
                <a-tooltip :title="t('emulator2.show')">
                  <a-button
                    size="small"
                    type="text"
                    :icon="h(EyeOutlined)"
                    :loading="pending.get(record.slot)?.op === 'show'"
                    :disabled="!actionsOf(record).show"
                    @click="operate(record, EmulatorOperateIn.operate.SHOW)"
                  />
                </a-tooltip>
                <a-tooltip :title="t('emulator2.hide')">
                  <a-button
                    size="small"
                    type="text"
                    :icon="h(EyeInvisibleOutlined)"
                    :loading="pending.get(record.slot)?.op === 'hide'"
                    :disabled="!actionsOf(record).hide"
                    @click="operate(record, EmulatorOperateIn.operate.HIDE)"
                  />
                </a-tooltip>
                <a-tooltip :title="t('emulator2.openStore')">
                  <a-button
                    size="small"
                    type="text"
                    :icon="h(AppstoreOutlined)"
                    :loading="pending.get(record.slot)?.op === 'store'"
                    :disabled="!actionsOf(record).store"
                    @click="openStore(record)"
                  />
                </a-tooltip>
                <a-tooltip
                  :title="
                    actionsOf(record).settings ? t('emulator2.settings') : blockedReason(record)
                  "
                >
                  <a-button
                    size="small"
                    type="text"
                    :icon="h(SettingOutlined)"
                    :disabled="!actionsOf(record).settings"
                    @click="openSettings(record)"
                  />
                </a-tooltip>
                <a-tooltip
                  :title="
                    actionsOf(record).delete ? t('emulator2.deleteInstance') : blockedReason(record)
                  "
                >
                  <a-button
                    size="small"
                    type="text"
                    danger
                    :icon="h(DeleteOutlined)"
                    :loading="pending.get(record.slot)?.op === 'deleting'"
                    :disabled="!actionsOf(record).delete"
                    @click="openDelete(record)"
                  />
                </a-tooltip>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-spin>
    </div>

    <a-alert type="info" show-icon :message="t('emulator2.footerHint')" class="footer-hint" />

    <!-- 单台设置 -->
    <a-modal
      v-model:open="settingsOpen"
      :title="t('emulator2.settingsTitle')"
      width="560px"
      :confirm-loading="savingSettings"
      :ok-text="t('emulator2.save')"
      @ok="confirmSettings"
    >
      <p v-if="settingsTarget">
        <strong>#{{ settingsTarget.slot }}</strong>
        — {{ settingsTarget.alias }} ·
        {{ t('emulator2.nativeIndex', { index: settingsTarget.nativeIndex }) }}
      </p>
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldWidth')">
              <a-input-number
                v-model:value="settingsForm.width"
                :min="160"
                :max="4096"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldHeight')">
              <a-input-number
                v-model:value="settingsForm.height"
                :min="160"
                :max="4096"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldDpi')">
              <a-input-number
                v-model:value="settingsForm.dpi"
                :min="80"
                :max="640"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldFps')">
              <a-input-number
                v-model:value="settingsForm.fps"
                :min="1"
                :max="240"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldCpu')">
              <a-input-number
                v-model:value="settingsForm.cpu"
                :min="1"
                :max="64"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldMemory')">
              <a-input-number
                v-model:value="settingsForm.memoryMb"
                :min="512"
                :max="65536"
                :step="512"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <a-alert type="info" show-icon :message="t('emulator2.settingsHint')" />
    </a-modal>

    <!-- 批量设置 -->
    <a-modal
      v-model:open="batchOpen"
      :title="t('emulator2.batchTitle')"
      width="560px"
      :confirm-loading="batchSaving"
      :ok-text="t('emulator2.batchApply')"
      :ok-button-props="{ disabled: !Object.keys(batchChanges).length }"
      @ok="confirmBatch"
    >
      <a-alert
        type="warning"
        show-icon
        :message="t('emulator2.batchWarning', { count: devices.length })"
        style="margin-bottom: 12px"
      />
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldWidth')">
              <a-input-number
                v-model:value="batchForm.width"
                :min="160"
                :max="4096"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldHeight')">
              <a-input-number
                v-model:value="batchForm.height"
                :min="160"
                :max="4096"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldDpi')">
              <a-input-number
                v-model:value="batchForm.dpi"
                :min="80"
                :max="640"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldFps')">
              <a-input-number
                v-model:value="batchForm.fps"
                :min="1"
                :max="240"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldCpu')">
              <a-input-number
                v-model:value="batchForm.cpu"
                :min="1"
                :max="64"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('emulator2.fieldMemory')">
              <a-input-number
                v-model:value="batchForm.memoryMb"
                :min="512"
                :max="65536"
                :step="512"
                style="width: 100%"
                :placeholder="t('emulator2.keepCurrent')"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
      <a-alert type="info" show-icon :message="t('emulator2.batchHint')" />
      <a-list
        v-if="batchFailures.length"
        size="small"
        bordered
        :data-source="batchFailures"
        :header="t('emulator2.batchFailures')"
        style="margin-top: 12px"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>#{{ item.slot }}</span>
            <template #actions>
              <span class="batch-fail-reason">{{ item.message }}</span>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- 新建实例 -->
    <a-modal
      v-model:open="createOpen"
      :title="t('emulator2.createTitle')"
      :confirm-loading="creating"
      :ok-text="t('emulator2.create')"
      :ok-button-props="{ disabled: !createPathId }"
      @ok="confirmCreate"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('emulator2.createOnPath')">
          <a-select v-model:value="createPathId" :options="pathSelectOptions" />
        </a-form-item>
        <a-form-item :label="t('emulator2.createName')">
          <a-input v-model:value="createName" :placeholder="t('emulator2.createNamePlaceholder')" />
        </a-form-item>
      </a-form>
      <a-alert type="info" show-icon :message="t('emulator2.createHint')" />
    </a-modal>

    <!-- 删除实例 -->
    <a-modal
      v-model:open="deleteOpen"
      :title="t('emulator2.deleteTitle')"
      width="600px"
      :confirm-loading="deleting"
      :ok-text="t('emulator2.deleteInstance')"
      :ok-button-props="{ danger: true }"
      @ok="confirmDelete"
    >
      <p v-if="deleteTarget">
        <strong>#{{ deleteTarget.slot }}</strong>
        — {{ deleteTarget.alias }} ·
        {{ t('emulator2.nativeIndex', { index: deleteTarget.nativeIndex }) }}
      </p>
      <a-alert
        type="warning"
        show-icon
        :message="
          t('emulator2.deleteWarning', {
            slot: deleteTarget ? '#' + deleteTarget.slot : '',
            count: deleteAffected.length,
          })
        "
        style="margin-bottom: 12px"
      />
      <a-list
        v-if="deleteAffected.length"
        size="small"
        bordered
        :data-source="deleteAffected"
        :header="t('emulator2.affectedScripts')"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>{{ item.name }}</span>
            <template #actions>
              <a-tag v-if="item.running" color="processing">{{ t('emulator2.running') }}</a-tag>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- 添加模拟器 -->
    <a-modal
      v-model:open="searchOpen"
      :title="t('emulator2.addTitle')"
      width="760px"
      :confirm-loading="adding"
      :ok-text="t('emulator2.add')"
      :ok-button-props="{ disabled: !selectedPaths.length }"
      @ok="confirmAdd"
    >
      <a-alert
        type="info"
        show-icon
        :message="t('emulator2.addHint')"
        style="margin-bottom: 12px"
      />
      <a-spin :spinning="searching">
        <a-empty v-if="!searchResults.length" :description="t('emulator.searchEmpty')" />
        <a-checkbox-group v-else v-model:value="selectedPaths" style="width: 100%">
          <div v-for="item in searchResults" :key="item.installPath" class="search-row">
            <a-checkbox :value="item.installPath" :disabled="!item.supported" />
            <div class="search-main">
              <div>
                <a-tag :color="item.supported ? 'purple' : 'default'">{{
                  typeLabel(item.type)
                }}</a-tag>
                <span class="search-alias">{{ item.alias }}</span>
                <span class="search-version">{{ item.version }}</span>
              </div>
              <div class="search-path">{{ item.installPath }}</div>
            </div>
            <a-tag :color="reasonColor(item.reason)">{{ reasonText(item) }}</a-tag>
          </div>
        </a-checkbox-group>
      </a-spin>
    </a-modal>

    <!-- 移除路径 -->
    <a-modal
      v-model:open="removeOpen"
      :title="t('emulator2.removeTitle')"
      width="640px"
      :confirm-loading="removing"
      :ok-text="t('emulator2.removePath')"
      :ok-button-props="{ danger: true }"
      @ok="confirmRemove"
    >
      <p v-if="removeTarget">
        <a-tag color="purple">{{ typeLabel(removeTarget.type) }}</a-tag>
        {{ removeTarget.alias }} — {{ removeTarget.installPath }}
      </p>
      <a-alert
        type="warning"
        show-icon
        :message="
          t('emulator2.removeWarning', {
            slots: removeSlots.map(s => `#${s}`).join(' ') || '—',
            count: removeAffected.length,
          })
        "
        style="margin-bottom: 12px"
      />
      <a-list
        v-if="removeAffected.length"
        size="small"
        bordered
        :data-source="removeAffected"
        :header="t('emulator2.affectedScripts')"
      >
        <template #renderItem="{ item }">
          <a-list-item>
            <span>{{ item.name }}</span>
            <template #actions>
              <span>#{{ item.slot }}</span>
              <a-tag v-if="item.running" color="processing">{{ t('emulator2.running') }}</a-tag>
            </template>
          </a-list-item>
        </template>
      </a-list>
      <a-alert
        v-if="runningAffected.length"
        type="warning"
        show-icon
        :message="t('emulator2.removeRunningHint', { count: runningAffected.length })"
        style="margin-top: 12px"
      />
    </a-modal>
  </div>
</template>

<style scoped>
/*
 * 面板占满上层给的高度：表头、表格、底部提示纵向排开，只有表格那一段可以伸缩。
 * 上层（Emulator.vue）把页签内容的高度钉死且不滚动，这里不这么排的话行数一多就被裁掉。
 */
.emulator2-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
}

.section-refreshing {
  margin-left: 8px;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
}

.table-area {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.table-area :deep(.table-spin),
.table-area :deep(.table-spin > .ant-spin-container) {
  height: 100%;
}

.table-empty {
  padding: 48px 0;
}

/* 表体的高度由脚本按 table-area 的实际高度算出来；antd 钉高后会常驻一条滚动条，改成按需出现 */
.device-table :deep(.ant-table-body) {
  overflow-y: auto !important;
}

.cell-loading {
  color: var(--ant-color-text-quaternary);
}

.footer-hint {
  flex-shrink: 0;
  margin-top: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.section-hint {
  margin-left: 8px;
  font-size: 13px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.path-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.path-alias {
  font-weight: 600;
}

.path-version,
.path-sub {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.path-line {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.source-sub {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.search-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  margin-bottom: 8px;
}

.search-main {
  flex: 1;
  min-width: 0;
}

.search-alias {
  font-size: 14px;
}

.search-version,
.search-path {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.search-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
