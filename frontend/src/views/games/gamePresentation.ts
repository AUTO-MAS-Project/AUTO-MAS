import type { ActiveTriggerField, DeviceStatus } from '@/api'
import { gameActionHint, gameDevices, type GameDevice, type GameRow } from '@/types/games'

export type StatusTone = 'success' | 'processing' | 'warning' | 'error' | 'neutral'

export interface TargetPriorityBadge {
  kind: 'operating' | 'error' | 'recovery' | 'inUse' | 'update'
  labelKey: string
  tone: StatusTone
  spinning?: boolean
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined
}

export function countOnlineDevices(row: GameRow): number {
  return gameDevices(row).filter(device => device.document.info?.status === 0).length
}

export function countActiveDevices(row: GameRow): number {
  return gameDevices(row).length
}

/** 按游戏目标归属聚合正在执行的触发器操作（含目标本身与其下属设备）。 */
export function buildTargetOperationsMap(
  rows: readonly GameRow[],
  activeTriggers: readonly ActiveTriggerField[] | undefined
): Map<string, ActiveTriggerField[]> {
  const result = new Map<string, ActiveTriggerField[]>()
  if (!activeTriggers?.length) return result
  const ownerByConfigUid = new Map<string, string>()
  for (const row of rows) {
    ownerByConfigUid.set(row.uid, row.uid)
    for (const device of gameDevices(row)) {
      ownerByConfigUid.set(device.uid, row.uid)
    }
  }
  for (const trigger of activeTriggers) {
    const ownerUid = ownerByConfigUid.get(trigger.configUid)
    if (!ownerUid) continue
    const list = result.get(ownerUid) ?? []
    list.push(trigger)
    result.set(ownerUid, list)
  }
  return result
}

export function hasModAvdMaintenance(row: GameRow): boolean {
  return Boolean(
    gameActionHint(row, row.uid, 'check_components') ||
    gameActionHint(row, row.uid, 'check_update') ||
    gameActionHint(row, row.uid, 'update')
  )
}

export function hasModAvdUpdate(row: GameRow): boolean {
  const update = asRecord(row.runtime.maintenance?.update)
  if (!update) return false
  const current = typeof update.currentVersion === 'string' ? update.currentVersion : ''
  const latest = typeof update.latestVersion === 'string' ? update.latestVersion : ''
  const blocked =
    (typeof update.checkError === 'string' && update.checkError.length > 0) ||
    (typeof update.notUpdatableReason === 'string' && update.notUpdatableReason.length > 0)
  return Boolean(current && latest && current !== latest && !blocked)
}

/** 插件提供配置守卫时后端才下发 capture 提示。 */
export function supportsConfigGuard(row: GameRow): boolean {
  return !!gameActionHint(row, row.uid, 'capture')
}

export function isTargetInUse(row: GameRow): boolean {
  return (
    Object.values(row.runtime.deviceUsage ?? {}).some(Boolean) ||
    gameActionHint(row, row.uid, 'save')?.editable === false
  )
}

/** 左栏每项最多显示一个最高优先状态：操作中 > 异常 > 待恢复 > 使用中 > 可更新。 */
export function getTargetPriorityBadge(
  row: GameRow,
  ops: readonly ActiveTriggerField[] | undefined
): TargetPriorityBadge | null {
  if (ops?.length) {
    return {
      kind: 'operating',
      labelKey: 'core.games.operating',
      tone: 'processing',
      spinning: true,
    }
  }
  const hasError = gameDevices(row).some(device => {
    const status = device.document.info?.status
    return status === 4 || status === 7
  })
  if (hasError) {
    return { kind: 'error', labelKey: 'core.games.states.4', tone: 'error' }
  }
  if (row.runtime.recoveryPending?.length) {
    return { kind: 'recovery', labelKey: 'core.games.recoveryShort', tone: 'warning' }
  }
  if (isTargetInUse(row)) {
    return { kind: 'inUse', labelKey: 'core.games.inUse', tone: 'processing' }
  }
  if (hasModAvdUpdate(row)) {
    return { kind: 'update', labelKey: 'core.games.updateAvailable', tone: 'success' }
  }
  return null
}

export function deviceStatusTone(device: GameDevice): StatusTone {
  const status: DeviceStatus = device.info?.status ?? 10
  if (status === 0) return 'success'
  if (status === 4 || status === 7) return 'error'
  if (status === 2 || status === 3 || status === 6) return 'processing'
  if (status === 5) return 'warning'
  return 'neutral'
}

export const RAIL_SEARCH_THRESHOLD = 5

export function shouldShowTargetSearch(rowCount: number): boolean {
  return rowCount > RAIL_SEARCH_THRESHOLD
}

/** 搜索框隐藏时忽略旧关键词，避免目标数降回阈值内后列表被旧筛选藏空。 */
export function filterGameTargetRows(
  rows: readonly GameRow[],
  keyword: string,
  searchVisible = shouldShowTargetSearch(rows.length)
): readonly GameRow[] {
  if (!searchVisible) return rows
  const query = keyword.trim().toLowerCase()
  if (!query) return rows
  return rows.filter(row => {
    const name = (row.document.info?.name ?? '').toLowerCase()
    const path = (row.document.info?.path ?? '').toLowerCase()
    const adapter = row.type.name.toLowerCase()
    return name.includes(query) || path.includes(query) || adapter.includes(query)
  })
}

/** 按打开确认框时固定的目标 UID 回查最新列表，目标消失或不可执行时返回 undefined。 */
export function resolveEditableGameTarget(
  rows: readonly GameRow[],
  targetUid: string,
  actionField: string
): GameRow | undefined {
  const row = rows.find(item => item.uid === targetUid)
  if (!row || gameActionHint(row, row.uid, actionField)?.editable !== true) return undefined
  return row
}

/** 按打开确认框时固定的目标与设备 UID 回查最新列表，设备消失或不可执行时返回 undefined。 */
export function resolveEditableDeviceTarget(
  rows: readonly GameRow[],
  gameUid: string,
  deviceUid: string,
  actionField: string
): GameRow | undefined {
  const row = rows.find(item => item.uid === gameUid)
  if (!row) return undefined
  if (!gameDevices(row).some(device => device.uid === deviceUid)) return undefined
  if (gameActionHint(row, deviceUid, actionField)?.editable !== true) return undefined
  return row
}

export function formatTargetConfigSummary(row: GameRow, t: (key: string) => string): string {
  const info = row.document.info
  const parts: string[] = []
  const waitTime =
    info && 'wait_time' in info
      ? info.wait_time
      : info && 'max_wait_time' in info
        ? info.max_wait_time
        : undefined
  if (typeof waitTime === 'number') parts.push(`${waitTime}s`)
  if (info && 'concurrent_execution' in info) {
    parts.push(
      t(info.concurrent_execution ? 'core.games.summary.parallel' : 'core.games.summary.serial')
    )
  }
  if (row.type.kind === 'client') {
    if (info && 'launch_with_launcher' in info) {
      parts.push(
        t(
          info.launch_with_launcher !== false
            ? 'core.games.summary.viaLauncher'
            : 'core.games.summary.directLaunch'
        )
      )
    }
    if (info && 'force_kill' in info && info.force_kill) {
      parts.push(t('core.games.summary.forceClose'))
    }
  } else if (row.type.type === 'general_emulator') {
    if (info && 'adb_path' in info && info.adb_path) {
      parts.push(t('core.games.summary.customAdb'))
    }
  } else {
    if (row.type.type !== 'avd' && info && 'stable_mode' in info && info.stable_mode) {
      parts.push(t('core.games.summary.stableMode'))
    }
    if (supportsConfigGuard(row) && info && 'config_guard' in info && info.config_guard) {
      parts.push(t('core.games.summary.configGuard'))
    }
    if (
      row.type.type === 'mumu' &&
      info &&
      'force_kill_before_launch' in info &&
      info.force_kill_before_launch
    ) {
      parts.push(t('core.games.summary.forceBefore'))
    }
    if (info && 'force_kill_on_close' in info && info.force_kill_on_close) {
      parts.push(t('core.games.summary.forceClose'))
    }
  }
  return parts.join(' · ')
}
