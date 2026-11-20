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

export function gameDevices(game: GameRow): GameDeviceRow[] {
  const devices = game.document.devices
  return (devices?.order ?? []).flatMap(item => {
    const document = devices?.data?.[item.uid]
    return document ? [{ uid: item.uid, document }] : []
  })
}

export function gameActionHint(
  row: GameRow,
  uid: string,
  field: string
): ComponentHint | undefined {
  return row.runtime.actionHints?.[uid]?.find(hint => hint.field === field)
}

export function isDeletedDevice(device: GameDevice): boolean {
  return Boolean(device.info && 'tombstone' in device.info && device.info.tombstone)
}
