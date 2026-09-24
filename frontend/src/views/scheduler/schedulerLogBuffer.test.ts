import { describe, expect, it } from 'vitest'

import {
  LOG_BUFFER_MAX_CHARS,
  applyTaskLogUpdate,
  type TaskLogBufferState,
} from './schedulerLogBuffer'

const fresh = (): TaskLogBufferState => ({ logBuffer: '', logSeq: undefined })

describe('applyTaskLogUpdate', () => {
  it('append=false 整体替换并记下 seq', () => {
    const state = fresh()
    expect(applyTaskLogUpdate(state, { log: 'a\nb\n', seq: 1, append: false })).toBe('replace')
    expect(state).toEqual({ logBuffer: 'a\nb\n', logSeq: 1 })

    // 日志被重置时后端再次推 append=false，同样整体替换
    expect(applyTaskLogUpdate(state, { log: 'x\n', seq: 2, append: false })).toBe('replace')
    expect(state).toEqual({ logBuffer: 'x\n', logSeq: 2 })
  })

  it('连续 append 按序追加', () => {
    const state = fresh()
    applyTaskLogUpdate(state, { log: '1\n', seq: 1, append: false })
    expect(applyTaskLogUpdate(state, { log: '2\n', seq: 2, append: true })).toBe('append')
    expect(applyTaskLogUpdate(state, { log: '3\n', seq: 3, append: true })).toBe('append')
    expect(state).toEqual({ logBuffer: '1\n2\n3\n', logSeq: 3 })
  })

  it('没有基线就收到 append 时要求重同步，本条丢弃', () => {
    const state = fresh()
    expect(applyTaskLogUpdate(state, { log: '2\n', seq: 2, append: true })).toBe('resync')
    expect(state).toEqual({ logBuffer: '', logSeq: undefined })
  })

  it('序号断裂时要求重同步，buffer 保持、seq 清空，之后的增量继续丢弃', () => {
    const state = fresh()
    applyTaskLogUpdate(state, { log: '1\n', seq: 1, append: false })
    expect(applyTaskLogUpdate(state, { log: '3\n', seq: 3, append: true })).toBe('resync')
    expect(state).toEqual({ logBuffer: '1\n', logSeq: undefined })
    // 重同步期间到达的下一条增量：没有基线，仍然丢弃
    expect(applyTaskLogUpdate(state, { log: '4\n', seq: 4, append: true })).toBe('resync')
    expect(state.logBuffer).toBe('1\n')
  })

  it('重同步后快照重置基线，随后增量可以衔接', () => {
    const state = fresh()
    applyTaskLogUpdate(state, { log: '1\n', seq: 1, append: false })
    applyTaskLogUpdate(state, { log: '3\n', seq: 3, append: true })
    // 快照带回上次推送的完整日志与 seq
    state.logBuffer = '1\n2\n3\n'
    state.logSeq = 3
    expect(applyTaskLogUpdate(state, { log: '4\n', seq: 4, append: true })).toBe('append')
    expect(state).toEqual({ logBuffer: '1\n2\n3\n4\n', logSeq: 4 })
  })

  it('buffer 超过 200,000 字符时丢头留尾', () => {
    const state = fresh()
    applyTaskLogUpdate(state, { log: 'a'.repeat(LOG_BUFFER_MAX_CHARS - 10), seq: 1, append: false })
    applyTaskLogUpdate(state, { log: 'b'.repeat(30), seq: 2, append: true })
    expect(state.logBuffer).toHaveLength(LOG_BUFFER_MAX_CHARS)
    expect(state.logBuffer.endsWith('b'.repeat(30))).toBe(true)
    expect(state.logBuffer.startsWith('a')).toBe(true)

    // 单条 append=false 超长同样裁到上限
    applyTaskLogUpdate(state, { log: 'c'.repeat(LOG_BUFFER_MAX_CHARS + 5), seq: 3, append: false })
    expect(state.logBuffer).toHaveLength(LOG_BUFFER_MAX_CHARS)
    expect(state.logSeq).toBe(3)
  })
})
