/**
 * Emulator 2.0 设备表的状态语义。
 *
 * 面板里和状态相关的判断都收在这里：一台设备此刻"算什么状态"、哪个按钮该亮、
 * 后台轮询回来的一份新状态怎么并进已有的行。纯函数，不碰网络和组件。
 *
 * 启动 / 关闭在后端是后台任务，接口一调用就返回，模拟器自己的状态要过一两秒才会变。
 * 那段空窗里如果照实显示"离线"，用户会以为没点上、再点一次。所以点下去的那一刻就
 * 把行记成 :data:`Pending`：状态按目标显示、按钮按目标状态给，直到轮询看到模拟器
 * 真的动了、或者后端发来「操作结束」。
 */
import type { Emulator2DeviceItem } from '@/api'

/** 设备状态码，与后端 ``DeviceStatus`` 一致 */
export const DeviceStatus = {
  ONLINE: 0,
  OFFLINE: 1,
  STARTING: 2,
  CLOSING: 3,
  ERROR: 4,
  NOT_FOUND: 5,
  UNKNOWN: 10,
} as const

export type PendingOp = 'open' | 'close' | 'show' | 'hide' | 'store' | 'deleting'

/** 一行上正在进行、还没等到结果的操作 */
export interface Pending {
  op: PendingOp
  /** 点下去时模拟器的状态；轮询仍看到这个值说明模拟器还没动，继续按目标显示 */
  from: number
  /** 过渡态显示成什么；只有启动 / 关闭有 */
  to: number | null
  /** 兜底过期时间（毫秒时间戳）：后端事件丢了也不能让一行永远转圈 */
  expiresAt: number
}

/** 启动 / 关闭的兜底时长。启动要等 Android 起来，给足；后端事件正常会早得多地收掉它 */
export const OPERATION_PENDING_TTL_MS = 120_000
/** 显示 / 隐藏 / 打开游戏中心这类，几秒内必有结果 */
export const QUICK_PENDING_TTL_MS = 30_000

/** 轮询节奏：有行在过渡态时盯紧一点，其余时间慢慢来（每轮都是几个子进程） */
export const POLL_IDLE_MS = 5000
export const POLL_ACTIVE_MS = 1000

export const makePending = (op: PendingOp, from: number, now: number): Pending => {
  const to = op === 'open' ? DeviceStatus.STARTING : op === 'close' ? DeviceStatus.CLOSING : null
  const ttl = op === 'open' || op === 'close' ? OPERATION_PENDING_TTL_MS : QUICK_PENDING_TTL_MS
  return { op, from, to, expiresAt: now + ttl }
}

/**
 * 这台设备此刻应当显示的状态。
 *
 * 轮询到的状态优先——模拟器一旦真的进入启动中 / 在线，那才是事实；只有它还停在
 * 点击前的那个值时，才用过渡态盖住。过期的过渡态不算数。
 */
export const effectiveStatus = (
  device: Pick<Emulator2DeviceItem, 'status'>,
  pending: Pending | undefined,
  now: number
): number => {
  const polled = device.status ?? DeviceStatus.NOT_FOUND
  if (!pending || pending.to === null || now >= pending.expiresAt) return polled
  return polled === pending.from ? pending.to : polled
}

/** 过渡态本身说明操作已经到头了：启动的看到在线、关闭的看到离线 */
export const pendingSettled = (pending: Pending, polledStatus: number, now: number): boolean => {
  if (now >= pending.expiresAt) return true
  if (pending.op === 'open') return polledStatus === DeviceStatus.ONLINE
  if (pending.op === 'close') return polledStatus === DeviceStatus.OFFLINE
  return false
}

export const isTransitional = (status: number): boolean =>
  status === DeviceStatus.STARTING || status === DeviceStatus.CLOSING

export interface ActionAvailability {
  start: boolean
  stop: boolean
  show: boolean
  hide: boolean
  store: boolean
  settings: boolean
  delete: boolean
}

/**
 * 每个按钮能不能点。
 *
 * - 启动：离线 / 出错 / 未知才能点；启动中和关闭中都不能——那正是用户抱怨的地方，
 *   启动中还亮着「启动」等于邀请他再点一次。
 * - 关闭：在线和**启动中**都能点。启动卡住时用户需要的正是这个按钮。
 * - 显示 / 隐藏 / 游戏中心：只有在线才有意义。
 * - 设置：启动 / 关闭 / 删除进行中不能改——雷电的写入和启动共用同一把实例锁，这时点保存会
 *   一直等到启动结束才返回，看起来像卡死；显示 / 隐藏 / 游戏中心进行中照常可改。
 * - 删除：必须离线，且这行没有别的事在进行。
 */
export const actionAvailability = (
  device: Pick<Emulator2DeviceItem, 'availability' | 'status'>,
  pending: Pending | undefined,
  now: number
): ActionAvailability => {
  const reachable = device.availability === 'ok'
  const status = effectiveStatus(device, pending, now)
  const busy = pending !== undefined && now < pending.expiresAt
  // 启动 / 关闭 / 删除会把这台实例整个占住（雷电还持有实例锁）；
  // 显示 / 隐藏 / 游戏中心只是对着窗口按几下，不该连关闭和设置一起锁掉
  const heavy =
    busy && (pending.op === 'open' || pending.op === 'close' || pending.op === 'deleting')
  const online = status === DeviceStatus.ONLINE
  const canStart =
    status === DeviceStatus.OFFLINE ||
    status === DeviceStatus.ERROR ||
    status === DeviceStatus.NOT_FOUND ||
    status === DeviceStatus.UNKNOWN
  const canStop = online || status === DeviceStatus.STARTING
  return {
    start: reachable && !busy && canStart,
    stop: reachable && canStop && !(heavy && pending.op !== 'open'),
    show: reachable && online && !busy,
    hide: reachable && online && !busy,
    store: reachable && online && !busy,
    settings: reachable && !heavy,
    delete:
      reachable && !busy && (status === DeviceStatus.OFFLINE || status === DeviceStatus.NOT_FOUND),
  }
}

/**
 * 把一份只带状态的新列表并进已有的行。
 *
 * 状态轮询不读设置（每轮把每台的配置都读一遍太贵），所以新列表里 ``settings`` 是空的，
 * 这里保留旧行的设置和稳定模式；新出现的行照单全收，消失的行去掉。
 * 返回值另外交回哪些设备号的状态变了——调用方据此决定要不要顺手把设置也刷一遍
 * （模拟器关掉时会把自己那份配置写回去）。
 */
/**
 * 把一份带设置的全量列表并进已有的行，但**状态以表里现有的为准**。
 *
 * 全量那一趟后端先取状态再逐台读设置，MuMu 上要一两秒；这段时间里状态轮询可能已经
 * 看到更新的状态（启动中 → 在线）。响应到达时如果表里的状态来自更晚发出的请求，
 * 就只收下它带来的设置，状态、地址、可用性都保留表里那份，免得把一行闪回旧状态。
 */
export const mergeSettings = (
  current: Emulator2DeviceItem[],
  fresh: Emulator2DeviceItem[]
): Emulator2DeviceItem[] => {
  const previous = new Map(current.map(row => [row.slot, row]))
  return fresh.map(row => {
    const old = previous.get(row.slot)
    if (!old) return row
    return {
      ...row,
      status: old.status,
      adbAddress: old.adbAddress,
      availability: old.availability,
      title: old.title,
    }
  })
}

export const mergeStatus = (
  current: Emulator2DeviceItem[],
  fresh: Emulator2DeviceItem[]
): { rows: Emulator2DeviceItem[]; changed: string[] } => {
  const previous = new Map(current.map(row => [row.slot, row]))
  const changed: string[] = []
  const rows = fresh.map(row => {
    const old = previous.get(row.slot)
    if (!old) return row
    if (old.status !== row.status || old.availability !== row.availability) changed.push(row.slot)
    return {
      ...row,
      settings: old.settings,
      stableMode: old.stableMode,
      stableUnsafe: old.stableUnsafe,
    }
  })
  return { rows, changed }
}
