import { describe, expect, it } from 'vitest'
import { toRunnableUserOptions } from './schedulerUserOptions'

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
