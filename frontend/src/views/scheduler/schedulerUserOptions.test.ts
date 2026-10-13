import { describe, expect, it } from 'vitest'
import { toRunnableUserOptions } from './schedulerUserOptions'

const build = (users: Array<{ uid: string; info: Record<string, unknown> }>) =>
  ({
    order: users.map(user => ({ uid: user.uid, type: 'UserEntry' as const })),
    data: Object.fromEntries(users.map(user => [user.uid, { info: user.info }])),
  }) as Parameters<typeof toRunnableUserOptions>[0]

describe('toRunnableUserOptions', () => {
  it('按后端顺序提供已启用用户并跳过已禁用用户', () => {
    expect(
      toRunnableUserOptions(
        build([
          { uid: 'u2', info: { name: '乙', enabled: true } },
          { uid: 'u1', info: { name: '甲', enabled: false } },
          { uid: 'u3', info: { name: '', enabled: true } },
        ])
      )
    ).toEqual([
      { value: 'u2', label: '乙' },
      { value: 'u3', label: 'u3' },
    ])
  })

  it('缺失用户数据时安全跳过', () => {
    const response = build([{ uid: 'u1', info: { name: '甲', enabled: true } }])
    response.order?.push({ uid: 'missing', type: 'UserEntry' })
    expect(toRunnableUserOptions(response)).toEqual([{ value: 'u1', label: '甲' }])
  })
})
