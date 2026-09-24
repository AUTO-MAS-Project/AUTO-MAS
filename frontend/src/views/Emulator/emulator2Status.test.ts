import { describe, expect, it } from 'vitest'

import type { Emulator2DeviceItem } from '@/api'
import {
  DeviceStatus,
  OPERATION_PENDING_TTL_MS,
  actionAvailability,
  effectiveStatus,
  makePending,
  mergeSettings,
  mergeStatus,
  pendingSettled,
} from './emulator2Status'

const device = (overrides: Partial<Emulator2DeviceItem> = {}): Emulator2DeviceItem => ({
  slot: '3',
  pathId: 'p',
  alias: 'LDPlayer14',
  realType: 'ldplayer',
  nativeIndex: '3',
  availability: 'ok',
  title: 'auto1',
  status: DeviceStatus.OFFLINE,
  adbAddress: 'emulator-5560',
  settings: { cpu: { value: 6, state: 'saved' } },
  stableMode: false,
  stableUnsafe: [],
  ...overrides,
})

describe('effectiveStatus', () => {
  it('shows the target state while the emulator has not moved yet', () => {
    const pending = makePending('open', DeviceStatus.OFFLINE, 1000)
    expect(effectiveStatus(device(), pending, 1500)).toBe(DeviceStatus.STARTING)
  })

  it('lets the polled state win once the emulator has moved', () => {
    const pending = makePending('open', DeviceStatus.OFFLINE, 1000)
    expect(effectiveStatus(device({ status: DeviceStatus.ONLINE }), pending, 1500)).toBe(
      DeviceStatus.ONLINE
    )
  })

  it('drops an expired pending state', () => {
    const pending = makePending('open', DeviceStatus.OFFLINE, 1000)
    expect(effectiveStatus(device(), pending, 1000 + OPERATION_PENDING_TTL_MS)).toBe(
      DeviceStatus.OFFLINE
    )
  })

  it('has no target state for show / hide', () => {
    const pending = makePending('show', DeviceStatus.ONLINE, 1000)
    expect(effectiveStatus(device({ status: DeviceStatus.ONLINE }), pending, 1500)).toBe(
      DeviceStatus.ONLINE
    )
  })
})

describe('pendingSettled', () => {
  it('settles an open once online and a close once offline', () => {
    expect(pendingSettled(makePending('open', 1, 0), DeviceStatus.ONLINE, 10)).toBe(true)
    expect(pendingSettled(makePending('open', 1, 0), DeviceStatus.STARTING, 10)).toBe(false)
    expect(pendingSettled(makePending('close', 0, 0), DeviceStatus.OFFLINE, 10)).toBe(true)
    expect(pendingSettled(makePending('close', 0, 0), DeviceStatus.CLOSING, 10)).toBe(false)
  })

  it('never settles show / hide from polling, only by expiry', () => {
    const pending = makePending('hide', DeviceStatus.ONLINE, 0)
    expect(pendingSettled(pending, DeviceStatus.ONLINE, 10)).toBe(false)
    expect(pendingSettled(pending, DeviceStatus.ONLINE, pending.expiresAt)).toBe(true)
  })
})

describe('actionAvailability', () => {
  it('offers start only when offline and stop while starting', () => {
    const offline = actionAvailability(device(), undefined, 0)
    expect(offline.start).toBe(true)
    expect(offline.stop).toBe(false)
    expect(offline.show).toBe(false)
    expect(offline.delete).toBe(true)

    const starting = actionAvailability(device({ status: DeviceStatus.STARTING }), undefined, 0)
    expect(starting.start).toBe(false)
    expect(starting.stop).toBe(true)
    expect(starting.show).toBe(false)
    expect(starting.delete).toBe(false)

    const closing = actionAvailability(device({ status: DeviceStatus.CLOSING }), undefined, 0)
    expect(closing.start).toBe(false)
    expect(closing.stop).toBe(false)
  })

  it('keeps stop available while our own start is in flight', () => {
    const pending = makePending('open', DeviceStatus.OFFLINE, 0)
    const actions = actionAvailability(device(), pending, 10)
    expect(actions.start).toBe(false)
    expect(actions.stop).toBe(true)
    expect(actions.settings).toBe(false)
    expect(actions.delete).toBe(false)
  })

  it('locks the row while our own close is in flight', () => {
    const pending = makePending('close', DeviceStatus.ONLINE, 0)
    const actions = actionAvailability(device({ status: DeviceStatus.ONLINE }), pending, 10)
    expect(actions.start).toBe(false)
    expect(actions.stop).toBe(false)
    expect(actions.hide).toBe(false)
  })

  it('keeps stop and settings available while a show / hide is in flight', () => {
    const pending = makePending('hide', DeviceStatus.ONLINE, 0)
    const actions = actionAvailability(device({ status: DeviceStatus.ONLINE }), pending, 10)
    expect(actions.stop).toBe(true)
    expect(actions.settings).toBe(true)
    expect(actions.show).toBe(false)
    expect(actions.hide).toBe(false)
  })

  it('enables show / hide / store only when online and idle', () => {
    const online = actionAvailability(device({ status: DeviceStatus.ONLINE }), undefined, 0)
    expect(online).toMatchObject({ show: true, hide: true, store: true, stop: true, start: false })
    const busy = actionAvailability(
      device({ status: DeviceStatus.ONLINE }),
      makePending('show', DeviceStatus.ONLINE, 0),
      10
    )
    expect(busy).toMatchObject({ show: false, hide: false, store: false })
  })

  it('disables everything when the install is unreachable', () => {
    const actions = actionAvailability(device({ availability: 'unavailable' }), undefined, 0)
    expect(Object.values(actions).every(value => value === false)).toBe(true)
  })
})

describe('mergeSettings', () => {
  it('takes settings from the fresh rows but keeps the newer status already in the table', () => {
    const current = [device({ status: DeviceStatus.ONLINE, settings: {} })]
    const fresh = [
      device({ status: DeviceStatus.STARTING, settings: { fps: { value: 60, state: 'saved' } } }),
      device({ slot: '9', nativeIndex: '9', status: DeviceStatus.OFFLINE }),
    ]
    const rows = mergeSettings(current, fresh)
    expect(rows[0]?.status).toBe(DeviceStatus.ONLINE)
    expect(rows[0]?.settings).toEqual({ fps: { value: 60, state: 'saved' } })
    expect(rows[1]?.status).toBe(DeviceStatus.OFFLINE)
  })
})

describe('mergeStatus', () => {
  it('keeps settings from the previous rows and reports status changes', () => {
    const current = [device(), device({ slot: '4', nativeIndex: '4', status: DeviceStatus.ONLINE })]
    const fresh = [
      device({ status: DeviceStatus.STARTING, settings: {} }),
      device({ slot: '4', nativeIndex: '4', status: DeviceStatus.ONLINE, settings: {} }),
      device({ slot: '5', nativeIndex: '5', settings: {} }),
    ]
    const { rows, changed } = mergeStatus(current, fresh)
    expect(rows.map(row => row.slot)).toEqual(['3', '4', '5'])
    expect(rows[0]?.status).toBe(DeviceStatus.STARTING)
    expect(rows[0]?.settings).toEqual({ cpu: { value: 6, state: 'saved' } })
    expect(rows[1]?.settings).toEqual({ cpu: { value: 6, state: 'saved' } })
    expect(rows[2]?.settings).toEqual({})
    expect(changed).toEqual(['3'])
  })

  it('drops rows that disappeared', () => {
    const { rows } = mergeStatus([device()], [])
    expect(rows).toEqual([])
  })
})
