import { describe, expect, it } from 'vitest'

import {
  QUEUE_SCRIPT_PLACEHOLDER,
  countQueueSelectedUsers,
  countQueueUsers,
  isRunnableQueueScriptId,
  reconcileQueueScope,
  selectedQueueUsers,
  toQueueUserIds,
  withoutAllQueueUsers,
  withQueueGroupSelection,
  type QueueScopeGroup,
} from './schedulerQueueScope'

const groups: QueueScopeGroup[] = [
  {
    scriptId: 's1',
    scriptName: 'MAA',
    users: [
      { label: '甲', value: 'u1' },
      { label: '乙', value: 'u2' },
    ],
  },
  { scriptId: 's2', scriptName: '森空岛签到', users: [{ label: '丙', value: 'u3' }] },
]

describe('schedulerQueueScope', () => {
  it('没改动过就是全选，且不进请求体', () => {
    const scope = {}
    expect(selectedQueueUsers(scope, groups[0])).toEqual(['u1', 'u2'])
    expect(countQueueSelectedUsers(scope, groups)).toBe(3)
    expect(toQueueUserIds(scope, groups)).toBeUndefined()
  })

  it('取消勾选后显式发出，取消到空就是这次整项跳过', () => {
    let scope = withQueueGroupSelection({}, groups[0], ['u1'])
    expect(scope).toEqual({ s1: ['u1'] })
    expect(countQueueSelectedUsers(scope, groups)).toBe(2)
    expect(toQueueUserIds(scope, groups)).toEqual({ s1: ['u1'] })

    scope = withQueueGroupSelection(scope, groups[0], [])
    expect(toQueueUserIds(scope, groups)).toEqual({ s1: [] })
  })

  it('勾回全选后回到不限制，全部取消则每个托管都显式跳过', () => {
    const restored = withQueueGroupSelection({ s1: ['u1'] }, groups[0], ['u2', 'u1'])
    expect(restored).toEqual({})
    expect(withoutAllQueueUsers(groups)).toEqual({ s1: [], s2: [] })
    expect(countQueueSelectedUsers(withoutAllQueueUsers(groups), groups)).toBe(0)
  })

  it('重新加载后丢掉已不可运行的账号与已移除的托管', () => {
    const scope = { s1: ['u1', 'gone'], s2: ['u3'] }
    expect(reconcileQueueScope(scope, groups)).toEqual({ s1: ['u1'] })
    // 队列里被删掉的托管不会残留在请求体里
    expect(toQueueUserIds({ s1: ['u1'], removed: ['u9'] }, groups)).toEqual({ s1: ['u1'] })
  })

  it('队列项没选脚本的占位值不算可运行的托管', () => {
    // 默认值就是 "-"，这类队列项在调度台不该被当成一个托管去拉账号
    expect(QUEUE_SCRIPT_PLACEHOLDER).toBe('-')
    expect(isRunnableQueueScriptId(QUEUE_SCRIPT_PLACEHOLDER)).toBe(false)
    expect(isRunnableQueueScriptId('')).toBe(false)
    expect(isRunnableQueueScriptId(undefined)).toBe(false)
    expect(isRunnableQueueScriptId('s1')).toBe(true)
  })

  it('可运行账号总数为 0 与「有账号但一个没勾」要能区分', () => {
    // 启动按钮与启动守卫共用这两个计数：都为 0 时前者说明没有可勾选对象，不该拦住启动
    const noUsers: QueueScopeGroup[] = [
      { scriptId: 's1', scriptName: 'MAA', users: [] },
      { scriptId: 's2', scriptName: '森空岛签到', users: [] },
    ]
    expect(countQueueUsers(noUsers)).toBe(0)
    expect(countQueueSelectedUsers({}, noUsers)).toBe(0)
    expect(countQueueUsers(groups)).toBe(3)
    expect(countQueueSelectedUsers({}, groups)).toBe(3)
    // 有账号却全部取消勾选：守卫必须拦住
    expect(
      countQueueUsers(groups) > 0 &&
        countQueueSelectedUsers(withoutAllQueueUsers(groups), groups) === 0
    ).toBe(true)
  })

  it('账号全被筛掉时仍保留该托管的显式跳过', () => {
    const empty: QueueScopeGroup[] = [{ scriptId: 's1', scriptName: 'MAA', users: [] }]
    expect(reconcileQueueScope({ s1: [] }, empty)).toEqual({ s1: [] })
    expect(reconcileQueueScope({ s1: ['u1'] }, empty)).toEqual({ s1: [] })
  })
})
