import { describe, expect, it, vi } from 'vite-plus/test'
import {
  reconcileScope,
  scopeRequest,
  type TaskScopeDraft,
  type TaskScopeEntry,
} from './taskSelection'
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))

const entry = (uid: string, scriptId = 'script'): TaskScopeEntry => ({
  uid,
  scriptId,
  name: scriptId,
  selection: 'all',
  selected: [],
  params: {},
  users: [
    { uid: 'u1', name: 'first', enabled: true, remainedDay: -1 },
    { uid: 'u2', name: 'second', enabled: false, remainedDay: 0 },
  ],
})
const queue = (): TaskScopeDraft => ({
  uid: 'queue',
  kind: 'queue',
  selection: 'all',
  params: {},
  entries: [entry('q1'), entry('q2', 'other'), entry('q3')],
})
const children = (draft: TaskScopeDraft) => scopeRequest(draft).tasks['0'].children!

describe('任务范围要求树', () => {
  it('被删或被替换的显式队列项保留为失效选择并阻止启动，不误跑新对象', () => {
    const draft = queue()
    draft.selection = 'explicit'
    draft.entries.forEach(item => {
      item.selection = 'explicit'
      item.selected = ['u2', 'u1']
    })
    draft.params = { custom: 'queue' }
    draft.entries[0].params = { custom: 'script' }
    draft.entries[0].users[0].params = { custom: { nested: true } }
    const freshUsers = queue()
    freshUsers.entries.forEach(item =>
      item.users.push({ uid: 'u3', name: 'new', enabled: true, remainedDay: -1 })
    )
    const preserved = reconcileScope(freshUsers, draft)
    expect(scopeRequest(preserved).tasks['0'].params).toEqual({ custom: 'queue' })
    expect(children(preserved)['0'].params).toEqual({ custom: 'script' })
    expect(children(preserved)['0'].children).toEqual({
      '0': { uid: 'u1', params: { custom: { nested: true } } },
      '1': { uid: 'u2' },
    })
    const cancelled = queue()
    cancelled.selection = 'none'
    expect(() => scopeRequest(cancelled)).toThrow()
    const missingUser = queue()
    missingUser.selection = 'explicit'
    missingUser.entries[0].selection = 'explicit'
    missingUser.entries[0].selected = ['missing']
    expect(() => scopeRequest(missingUser)).toThrow()
    missingUser.entries[0].selected = []
    expect(() => scopeRequest(missingUser)).toThrow()
    const fresh = queue()
    fresh.entries[0].scriptId = 'replacement'
    fresh.entries.pop()
    const restored = reconcileScope(fresh, draft)
    expect(restored.entries.map(item => item.uid)).toEqual(['q1', 'q2', 'q3'])
    expect(restored.entries.filter(item => item.missing).map(item => item.uid)).toEqual([
      'q1',
      'q3',
    ])
    expect(() => scopeRequest(restored)).toThrow()
    restored.entries[0].selection = 'none'
    expect(() => scopeRequest(restored)).toThrow()
    restored.entries[0].selection = 'explicit'
    restored.entries[2].selection = 'none'
    expect(() => scopeRequest(restored)).toThrow()
  })
})
