import { describe, expect, it } from 'vitest'
import type { Script, User } from '@/types/script'
import { filterScriptsByKeyword } from './scriptSearch'

const createUser = (id: string, name: string, accountId: string) =>
  ({ id, name, Info: { Name: name, Id: accountId } }) as User

const createScript = (id: string, name: string, users: User[]) =>
  ({ id, name, type: 'MAA', users }) as Script

describe('filterScriptsByKeyword', () => {
  const alice = createUser('user-1', 'Alice', '10001')
  const bob = createUser('user-2', 'Bob', '10002')
  const scripts = [
    createScript('script-1', '日常任务', [alice, bob]),
    createScript('script-2', '活动任务', []),
  ]

  it('keeps all users when the script itself matches', () => {
    const result = filterScriptsByKeyword(scripts, '日常')

    expect(result).toHaveLength(1)
    expect(result[0]).toBe(scripts[0])
    expect(result[0].users).toEqual([alice, bob])
  })

  it('keeps only matching users when a user name or ID matches', () => {
    expect(filterScriptsByKeyword(scripts, 'alice')[0].users).toEqual([alice])
    expect(filterScriptsByKeyword(scripts, '10002')[0].users).toEqual([bob])
  })

  it('returns the original list for a blank query and no rows for an unknown query', () => {
    expect(filterScriptsByKeyword(scripts, '   ')).toBe(scripts)
    expect(filterScriptsByKeyword(scripts, '不存在')).toEqual([])
  })
})
