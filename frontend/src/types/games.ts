import type {
  ComponentHint,
  GameBindingOption,
  GameGetOut,
  GameRuntimeData,
  GameTypeItem,
} from '@/api'

export type GameDocument = NonNullable<GameGetOut['data']>[string]
export type GameDevice = NonNullable<NonNullable<GameDocument['devices']>['data']>[string]
export interface GameRow {
  uid: string
  document: GameDocument
  type: GameTypeItem
  runtime: GameRuntimeData
}
export interface GameDeviceRow {
  uid: string
  document: GameDevice
}
export type GameBindingValue = {
  game_id: string
  device_id: string
  unavailable_reason?: string | null
}

/** 目标下的可用设备；已删除实例的墓碑（宿主永久保留以占住身份）不列出。 */
export function gameDevices(game: GameRow): GameDeviceRow[] {
  const devices = game.document.devices
  return (devices?.order ?? []).flatMap(item => {
    const document = devices?.data?.[item.uid]
    return document && !isTombstone(document) ? [{ uid: item.uid, document }] : []
  })
}

/**
 * 设备下拉的选项：可用设备，外加当前绑定但已不在其中的那台（已删除，禁用），免得下拉框里
 * 露出设备 uid。所绑设备是墓碑时带上原名；绑定指向不存在的设备时 document 为 null。
 */
export function visibleDevices(
  game: GameRow | undefined,
  currentId: string
): Array<{ uid: string; document: GameDevice | null; deleted: boolean }> {
  const available = game ? gameDevices(game) : []
  const rows = available.map(device => ({ ...device, deleted: false }))
  if (!game || currentId === '-' || available.some(device => device.uid === currentId)) return rows
  return [
    ...rows,
    { uid: currentId, document: game.document.devices?.data?.[currentId] ?? null, deleted: true },
  ]
}

export interface BindingTargetOption {
  value: string
  label: string
  disabled: boolean
  /** 禁用原因或只提示不拒绝的问题，放在选项名后 */
  note: string
  /** 当前已选、但与控制方式类型不符或已不在列表里的项 */
  stale: boolean
}

/**
 * 目标下拉的选项：后端给出的目标按控制方式要求的类型（emulator / client）过滤，kind 为空时
 * 不过滤；当前已选但被过滤掉、或已不在列表里的项追加在末尾并禁用，免得下拉框里露出 uid。
 * 后端列表还没到时用游戏管理的条目兜底；两边都找不到时用 missingLabel。
 */
export function bindingTargetOptions(
  options: GameBindingOption[] | undefined,
  rows: GameRow[],
  kind: string | undefined,
  currentId: string,
  missingLabel: string
): BindingTargetOption[] {
  const kindOf = (uid: string) => rows.find(row => row.uid === uid)?.type.kind
  const source: GameBindingOption[] =
    options ?? rows.map(row => ({ value: row.uid, label: row.document.info?.name ?? '' }))
  const result = source
    .filter(option => !kind || !kindOf(option.value) || kindOf(option.value) === kind)
    .map(option => ({
      value: option.value,
      label: option.label,
      disabled: !!option.disabledReason,
      note: option.disabledReason ?? option.warning ?? '',
      stale: false,
    }))
  if (currentId === '-' || result.some(option => option.value === currentId)) return result
  const known = source.find(option => option.value === currentId)
  const row = rows.find(item => item.uid === currentId)
  return [
    ...result,
    {
      value: currentId,
      label: known?.label ?? row?.document.info?.name ?? missingLabel,
      disabled: true,
      note: '',
      stale: true,
    },
  ]
}

function isTombstone(device: GameDevice): boolean {
  return Boolean(device.info && 'tombstone' in device.info && device.info.tombstone)
}

export function gameActionHint(
  row: GameRow,
  uid: string,
  field: string
): ComponentHint | undefined {
  return row.runtime.actionHints?.[uid]?.find(hint => hint.field === field)
}
