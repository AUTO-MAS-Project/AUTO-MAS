import { describe, expect, it } from 'vitest'
import {
  scriptScopeGroup,
  scriptScopeSelection,
  splitUserOptions,
  toScriptUserIds,
} from './schedulerUserOptions'
import {
  countQueueUsers,
  countQueueSelectedUsers,
  withoutAllQueueUsers,
  withQueueGroupSelection,
  type QueueScopeGroup,
} from './schedulerQueueScope'

const user = (uid: string, info: Record<string, unknown>) => ({ uid, info })

const build = (users: Array<{ uid: string; info: Record<string, unknown> }>) =>
  ({
    index: users.map(u => ({ uid: u.uid, type: 'MaaUserConfig' as const })),
    data: Object.fromEntries(users.map(u => [u.uid, { Info: u.info }])),
  }) as unknown as Parameters<typeof splitUserOptions>[0]

describe('splitUserOptions', () => {
  it('未启用的用户归到 disabled，原因 disabled', () => {
    const { runnable, disabled } = splitUserOptions(
      build([
        user('a', { Name: '甲', Status: true, RemainedDay: -1 }),
        user('b', { Name: '乙', Status: false, RemainedDay: -1 }),
      ])
    )
    expect(runnable).toEqual([{ value: 'a', label: '甲' }])
    expect(disabled).toEqual([{ value: 'b', label: '乙', reason: 'disabled' }])
  })

  it('剩余天数为 0 的归到 disabled，原因 expired；-1（无限）与正数保留', () => {
    const { runnable, disabled } = splitUserOptions(
      build([
        user('a', { Name: '甲', Status: true, RemainedDay: 0 }),
        user('b', { Name: '乙', Status: true, RemainedDay: -1 }),
        user('c', { Name: '丙', Status: true, RemainedDay: 3 }),
      ])
    )
    expect(runnable.map(item => item.value)).toEqual(['b', 'c'])
    expect(disabled).toEqual([{ value: 'a', label: '甲', reason: 'expired' }])
  })

  it('未启用且天数耗尽时以未启用为准', () => {
    const { disabled } = splitUserOptions(
      build([user('a', { Name: '甲', Status: false, RemainedDay: 0 })])
    )
    expect(disabled).toEqual([{ value: 'a', label: '甲', reason: 'disabled' }])
  })

  it('保持 index 的顺序', () => {
    const { runnable } = splitUserOptions(
      build([
        user('c', { Name: '丙', Status: true, RemainedDay: -1 }),
        user('a', { Name: '甲', Status: true, RemainedDay: -1 }),
        user('b', { Name: '乙', Status: true, RemainedDay: -1 }),
      ])
    )
    expect(runnable.map(item => item.value)).toEqual(['c', 'a', 'b'])
  })

  it('用户名为空时退回 uid', () => {
    const { runnable } = splitUserOptions(
      build([user('a', { Name: '', Status: true, RemainedDay: -1 })])
    )
    expect(runnable).toEqual([{ value: 'a', label: 'a' }])
  })

  it('index 里有但 data 缺条目时两组都不放，不抛错', () => {
    const payload = build([user('a', { Name: '甲', Status: true, RemainedDay: -1 })])
    payload.index.push({ uid: 'ghost' } as (typeof payload.index)[number])
    const { runnable, disabled } = splitUserOptions(payload)
    expect(runnable).toEqual([{ value: 'a', label: '甲' }])
    expect(disabled).toEqual([])
  })

  it('disabled 只展示：不参与账号计数，写回也不带它', () => {
    const { runnable, disabled } = splitUserOptions(
      build([
        user('a', { Name: '甲', Status: true, RemainedDay: -1 }),
        user('b', { Name: '乙', Status: false, RemainedDay: -1 }),
      ])
    )
    const group: QueueScopeGroup = {
      scriptId: 's1',
      scriptName: 'MAA',
      users: runnable,
      disabledUsers: disabled,
    }
    expect(countQueueUsers([group])).toBe(1)
    expect(countQueueSelectedUsers(scriptScopeSelection(group, undefined), [group])).toBe(1)
    expect(toScriptUserIds(scriptScopeSelection(group, undefined), group)).toEqual(['a'])
  })
})

describe('脚本任务的本次运行范围', () => {
  const users = [
    { label: '甲', value: 'u1' },
    { label: '乙', value: 'u2' },
  ]
  const group: QueueScopeGroup = { scriptId: 's1', scriptName: 'MAA', users }

  it('没改动过就是全选，面板能看到全部账号', () => {
    const scope = scriptScopeSelection(group, undefined)
    expect(scope).toEqual({ s1: ['u1', 'u2'] })
    expect(countQueueSelectedUsers(scope, [group])).toBe(2)
  })

  it('取消勾选写回 userIds 子集，勾满再回到不限制', () => {
    const subset = withQueueGroupSelection(scriptScopeSelection(group, undefined), group, ['u1'])
    expect(subset).toEqual({ s1: ['u1'] })
    expect(toScriptUserIds(subset, group)).toEqual(['u1'])

    const restored = withQueueGroupSelection(subset, group, ['u1', 'u2'])
    expect(restored).toEqual({})
    expect(toScriptUserIds(restored, group)).toBeUndefined()
  })

  it('取消全选写回空数组，启动守卫据此拦住', () => {
    const cleared = withoutAllQueueUsers([group])
    expect(toScriptUserIds(cleared, group)).toEqual([])
    expect(countQueueSelectedUsers(cleared, [group])).toBe(0)
  })

  it('没选中任务时不生成分组', () => {
    expect(scriptScopeGroup(null, 'MAA', users)).toBeNull()
    expect(scriptScopeGroup('s1', 'MAA', users)).toEqual(group)
  })
})
