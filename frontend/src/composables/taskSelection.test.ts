import { describe, expect, it, vi } from 'vite-plus/test'
import { TaskMode } from '@/api'
import {
  indexed,
  persistScope,
  reconcileScope,
  scopeRequest,
  targetRequest,
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
  it('动态全选保留空子树，直接托管使用单个 - 入口', () => {
    expect(scopeRequest(queue())).toEqual({
      mode: TaskMode.AUTO_PROXY,
      tasks: { '0': { uid: 'queue' } },
    })
    expect(targetRequest({ kind: 'script', value: 'script' }).tasks['0']).toEqual({
      uid: '-',
      children: { '0': { uid: 'script' } },
    })
  })
  it('动态全选保留入口参数，不强制展开配置名单', () => {
    const draft = queue()
    draft.params = { custom: 'queue' }
    expect(scopeRequest(draft).tasks['0']).toEqual({ uid: 'queue', params: { custom: 'queue' } })
  })
  it('重复托管按队列项独立选择，最后一次出现不会误选第一次', () => {
    const draft = queue()
    draft.selection = 'explicit'
    draft.entries[0].selection = 'none'
    draft.entries[1].selection = 'none'
    draft.entries[2].selection = 'explicit'
    draft.entries[2].selected = ['u2']
    draft.entries[2].params = { instance_idx: 2 }
    expect(children(draft)).toEqual({
      '0': { uid: 'q3', params: { instance_idx: 2 }, children: { '0': { uid: 'u2' } } },
    })
  })
  it('显式全选在配置新增用户后仍保留原集合，不扩大为全部用户', () => {
    const draft = queue()
    draft.selection = 'explicit'
    draft.entries.forEach(item => {
      item.selection = 'explicit'
      item.selected = ['u2', 'u1']
    })
    const fresh = queue()
    fresh.entries.forEach(item =>
      item.users.push({ uid: 'u3', name: 'new', enabled: true, remainedDay: -1 })
    )
    const restored = reconcileScope(fresh, draft)
    expect(children(restored)['0'].children).toEqual({ '0': { uid: 'u1' }, '1': { uid: 'u2' } })
  })
  it('全部取消不能变成空子树全选，禁用与天数不足不改变显式要求', () => {
    const draft = queue()
    draft.selection = 'none'
    expect(() => scopeRequest(draft)).toThrow()
    draft.selection = 'explicit'
    draft.entries.forEach(item => {
      item.selection = 'explicit'
      item.selected = ['u2']
    })
    expect(children(draft)['0'].children!['0'].uid).toBe('u2')
  })
  it('被删或被替换的显式队列项保留为失效选择并阻止启动，不误跑新对象', () => {
    const draft = queue()
    draft.selection = 'explicit'
    const fresh = queue()
    fresh.entries[0].scriptId = 'replacement'
    fresh.entries.pop()
    const restored = reconcileScope(fresh, draft)
    expect(restored.entries.map(item => item.uid)).toEqual(['q1', 'q2', 'q3'])
    expect(() => scopeRequest(restored)).toThrow()
  })
  it('用户失效不静默改成全选，节点参数原样放在对应层', () => {
    const draft = queue()
    draft.selection = 'explicit'
    draft.entries[0].selection = 'explicit'
    draft.entries[0].selected = ['missing']
    expect(() => scopeRequest(draft)).toThrow()
    draft.entries[0].selected = ['u1']
    draft.entries[0].users[0].params = { custom: { nested: true } }
    expect(children(draft)['0'].children!['0'].params).toEqual({ custom: { nested: true } })
  })
  it('共享配置与查看会话唯一目标明确为 default，队列不能用于配置会话', () => {
    expect(targetRequest({ kind: 'script', value: 'script' }, TaskMode.SCRIPT_VIEW)).toEqual({
      mode: TaskMode.SCRIPT_VIEW,
      tasks: indexed([{ uid: 'script', children: indexed([{ uid: 'default' }]) }]),
    })
    expect(() => targetRequest({ kind: 'queue', value: 'queue' }, TaskMode.SCRIPT_CONFIG)).toThrow()
  })
  it('只持久化选择意图，刷新配置后仍恢复第三个队列项的独立选择', () => {
    const draft = queue()
    draft.selection = 'explicit'
    draft.entries[2].selection = 'explicit'
    draft.entries[2].selected = ['u2']
    const saved = persistScope(draft)!
    expect(saved.entries[0].users).toEqual([])
    expect(saved.entries[0].name).toBe('')
    expect(children(reconcileScope(queue(), saved))['2'].children!['0'].uid).toBe('u2')
  })
})
