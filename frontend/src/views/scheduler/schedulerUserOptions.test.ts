import { describe, expect, it } from 'vitest'
import {
  scriptScopeGroup,
  scriptScopeSelection,
  toRunnableUserOptions,
  toScriptUserIds,
} from './schedulerUserOptions'
import {
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
  }) as unknown as Parameters<typeof toRunnableUserOptions>[0]

describe('toRunnableUserOptions', () => {
  it('筛掉未启用的用户', () => {
    const options = toRunnableUserOptions(
      build([
        user('a', { Name: '甲', Status: true, RemainedDay: -1 }),
        user('b', { Name: '乙', Status: false, RemainedDay: -1 }),
      ])
    )
    expect(options).toEqual([{ value: 'a', label: '甲' }])
  })

  it('筛掉剩余天数为 0 的用户，但保留 -1（无限）与正数', () => {
    const options = toRunnableUserOptions(
      build([
        user('a', { Name: '甲', Status: true, RemainedDay: 0 }),
        user('b', { Name: '乙', Status: true, RemainedDay: -1 }),
        user('c', { Name: '丙', Status: true, RemainedDay: 3 }),
      ])
    )
    expect(options.map(item => item.value)).toEqual(['b', 'c'])
  })

  it('保持 index 的顺序', () => {
    const options = toRunnableUserOptions(
      build([
        user('c', { Name: '丙', Status: true, RemainedDay: -1 }),
        user('a', { Name: '甲', Status: true, RemainedDay: -1 }),
        user('b', { Name: '乙', Status: true, RemainedDay: -1 }),
      ])
    )
    expect(options.map(item => item.value)).toEqual(['c', 'a', 'b'])
  })

  it('用户名为空时退回 uid', () => {
    const options = toRunnableUserOptions(
      build([user('a', { Name: '', Status: true, RemainedDay: -1 })])
    )
    expect(options).toEqual([{ value: 'a', label: 'a' }])
  })

  it('index 里有但 data 缺条目时跳过，不抛错', () => {
    const payload = build([user('a', { Name: '甲', Status: true, RemainedDay: -1 })])
    payload.index.push({ uid: 'ghost' } as (typeof payload.index)[number])
    expect(toRunnableUserOptions(payload)).toEqual([{ value: 'a', label: '甲' }])
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
