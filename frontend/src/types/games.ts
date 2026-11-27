import type { ComponentHint, GameGetOut, GameRuntimeData, GameTypeItem } from '@/api'

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

/** 目标下的可用设备；适配插件删除实例后、宿主移除条目前留下的墓碑不列出。 */
export function gameDevices(game: GameRow): GameDeviceRow[] {
  const devices = game.document.devices
  return (devices?.order ?? []).flatMap(item => {
    const document = devices?.data?.[item.uid]
    return document && !isTombstone(document) ? [{ uid: item.uid, document }] : []
  })
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
