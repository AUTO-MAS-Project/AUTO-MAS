import { describe, expect, it } from 'vitest'
import { sizedAvatar, startOfWeek, tallyCommits } from './contributors'

const commit = (
  login: string | null,
  options: { type?: string; name?: string; merge?: boolean } = {}
) => ({
  author: login ? { login, avatar_url: `https://a/${login}`, type: options.type ?? 'User' } : null,
  commit: { author: { name: options.name ?? login ?? 'someone' } },
  parents: options.merge ? [{}, {}] : [{}],
})

describe('weekly commit board', () => {
  it('按作者数提交，合并提交和机器人不算，从多到少排', () => {
    const list = tallyCommits([
      [
        commit('alice'),
        commit('bob'),
        commit('alice'),
        commit('alice', { merge: true }),
        commit('github-actions[bot]', { type: 'Bot' }),
      ],
      [commit('bob'), commit('bob'), commit('weekly-format', { type: 'Bot' })],
    ])

    expect(list.map(item => [item.login, item.commits])).toEqual([
      ['bob', 3],
      ['alice', 2],
    ])
    expect(list[0].avatarUrl).toBe('https://a/bob')
  })

  it('没关联 GitHub 账号的按提交里的名字算，没有头像', () => {
    const list = tallyCommits([
      [commit(null, { name: '路人甲' }), commit(null, { name: '路人甲' })],
    ])
    expect(list).toEqual([{ login: '路人甲', avatarUrl: '', commits: 2 }])
  })

  it('返回的不是数组时当空榜', () => {
    expect(tallyCommits([{ message: 'API rate limit exceeded' }])).toEqual([])
  })

  it('本周从周一 0 点算起，周日也归到这一周', () => {
    // 2026-10-06 是周二，2026-10-11 是周日
    expect(startOfWeek(new Date(2026, 9, 6, 15, 30))).toEqual(new Date(2026, 9, 5))
    expect(startOfWeek(new Date(2026, 9, 11, 23, 59))).toEqual(new Date(2026, 9, 5))
    expect(startOfWeek(new Date(2026, 9, 5, 0, 0))).toEqual(new Date(2026, 9, 5))
  })

  it('头像带尺寸参数', () => {
    expect(sizedAvatar('https://avatars.githubusercontent.com/u/1?v=4', 96)).toBe(
      'https://avatars.githubusercontent.com/u/1?v=4&s=96'
    )
    expect(sizedAvatar('https://x/u/1', 48)).toBe('https://x/u/1?s=48')
  })
})
