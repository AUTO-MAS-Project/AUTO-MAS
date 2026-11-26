import { describe, expect, it } from 'vite-plus/test'
import type { ActiveTriggerField } from '@/api'
import type { GameRow } from '@/types/games'
import {
  buildTargetOperationsMap,
  filterGameTargetRows,
  getTargetPriorityBadge,
  resolveEditableDeviceTarget,
  resolveEditableGameTarget,
  shouldShowTargetSearch,
} from './gamePresentation'

function makeRow(uid: string, name: string, overrides?: Partial<GameRow>): GameRow {
  return {
    uid,
    type: {
      type: 'mumu',
      name: 'MuMu 模拟器',
      configType: 'MuMuGameConfig',
      kind: 'emulator',
    },
    document: {
      info: { name, path: `D:\\Emulators\\${uid}\\MuMuManager.exe` },
      devices: {
        order: [{ uid: `${uid}-dev-0`, type: 'MuMuDevice' }],
        data: {
          [`${uid}-dev-0`]: {
            info: { name: `${name}-0`, index: '0', status: 1 },
          },
        },
      },
    } as GameRow['document'],
    runtime: {
      actionHints: {
        [uid]: [{ field: 'delete', component: 'button', editable: true }],
        [`${uid}-dev-0`]: [{ field: 'delete_instance', component: 'button', editable: true }],
      },
      deviceUsage: {},
      recoveryPending: [],
    },
    ...overrides,
  }
}

describe('gamePresentation', () => {
  it('按固定目标 UID 回查可执行目标，原目标被移除后不误删其他目标', () => {
    const targetA = makeRow('game-a', '目标 A')
    const targetB = makeRow('game-b', '目标 B')

    expect(resolveEditableGameTarget([targetA, targetB], 'game-a', 'delete')?.uid).toBe('game-a')
    // 确认框打开期间目标 A 被移除、列表只剩目标 B，必须停止而不是命中 B
    expect(resolveEditableGameTarget([targetB], 'game-a', 'delete')).toBeUndefined()
    // 同一目标已被锁定不可删时同样停止
    const lockedA = makeRow('game-a', '目标 A', {
      runtime: {
        actionHints: { 'game-a': [{ field: 'delete', component: 'button', editable: false }] },
      },
    })
    expect(resolveEditableGameTarget([lockedA], 'game-a', 'delete')).toBeUndefined()
  })

  it('按固定目标与设备 UID 回查可执行设备，避免误删其他目标的实例', () => {
    const targetA = makeRow('game-a', '目标 A')
    const targetB = makeRow('game-b', '目标 B')

    expect(
      resolveEditableDeviceTarget([targetA, targetB], 'game-a', 'game-a-dev-0', 'delete_instance')
        ?.uid
    ).toBe('game-a')
    expect(
      resolveEditableDeviceTarget([targetB], 'game-a', 'game-a-dev-0', 'delete_instance')
    ).toBeUndefined()
  })

  it('目标数降到 5 个以内隐藏搜索框时忽略旧关键词，避免把剩余目标藏空', () => {
    const sixTargets = Array.from({ length: 6 }, (_, i) => makeRow(`g-${i}`, `目标 ${i}`))
    expect(shouldShowTargetSearch(sixTargets.length)).toBe(true)
    expect(filterGameTargetRows(sixTargets, '目标 5').map(r => r.uid)).toEqual(['g-5'])

    // 删掉唯一命中的第 6 个目标后，剩余 5 个应全部可见，不能继续被旧关键词“目标 5”藏空
    const fiveTargets = sixTargets.slice(0, 5)
    expect(shouldShowTargetSearch(fiveTargets.length)).toBe(false)
    expect(filterGameTargetRows(fiveTargets, '目标 5').map(r => r.uid)).toEqual([
      'g-0',
      'g-1',
      'g-2',
      'g-3',
      'g-4',
    ])
  })

  it('按目标归属聚合进行中操作，并严格按优先级选出单一状态标', () => {
    const targetA = makeRow('game-a', '目标 A', {
      runtime: {
        recoveryPending: ['game-a-dev-0'],
        deviceUsage: { 'game-a-dev-0': 'MAA' },
      },
    })
    const triggerOnDevice: ActiveTriggerField = {
      taskId: 'task-1',
      configUid: 'game-a-dev-0',
      group: 'action',
      field: 'open',
      cancelling: false,
    }
    const opsMap = buildTargetOperationsMap([targetA], [triggerOnDevice])
    expect(opsMap.get('game-a')).toHaveLength(1)
    expect(getTargetPriorityBadge(targetA, opsMap.get('game-a'))?.kind).toBe('operating')
    expect(getTargetPriorityBadge(targetA, [])?.kind).toBe('recovery')
  })
})
