import type { ActiveTriggerField, DeviceStatus } from '@/api'
import {
  gameActionHint,
  gameDevices,
  isDeletedDevice,
  type GameDevice,
  type GameRow,
} from '@/types/games'

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
  return gameDevices(row).filter(
    device => !isDeletedDevice(device.document) && device.document.info?.status === 0
  ).length
}

export function countActiveDevices(row: GameRow): number {
  return gameDevices(row).filter(device => !isDeletedDevice(device.document)).length
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
    if (isDeletedDevice(device.document)) return false
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
    if (info && 'config_guard' in info && info.config_guard) {
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
