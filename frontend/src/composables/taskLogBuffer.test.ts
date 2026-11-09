import { describe, expect, it } from 'vite-plus/test'
import { applyTaskLogUpdate, LOG_BUFFER_MAX_CHARS, type TaskLogBufferState } from './taskLogBuffer'

const state = (): TaskLogBufferState => ({ log: '', logFirstLine: 1 })

describe('任务日志增量合并', () => {
  it('替换建立基线，连续序号追加，不受追加包 firstLine 影响', () => {
    const buffer = state()
    expect(applyTaskLogUpdate(buffer, { log: 'one\n', seq: 1, append: false, firstLine: 10 })).toBe(
      'replace'
    )
    expect(applyTaskLogUpdate(buffer, { log: 'two\n', seq: 2, append: true, firstLine: 1 })).toBe(
      'append'
    )
    expect(buffer.log).toBe('one\ntwo\n')
    expect(buffer.logFirstLine).toBe(10)
    expect(buffer.logSeq).toBe(2)
  })

  it('缺少基线或序号跳跃时丢弃增量，直到完整快照重建基线', () => {
    const buffer = state()
    expect(applyTaskLogUpdate(buffer, { log: 'missing', seq: 2, append: true, firstLine: 1 })).toBe(
      'resync'
    )
    applyTaskLogUpdate(buffer, { log: 'base', seq: 3, append: false, firstLine: 1 })
    expect(applyTaskLogUpdate(buffer, { log: 'gap', seq: 5, append: true, firstLine: 1 })).toBe(
      'resync'
    )
    expect(buffer.log).toBe('base')
    expect(buffer.logSeq).toBeUndefined()
    applyTaskLogUpdate(buffer, { log: 'snapshot', seq: 7, append: false, firstLine: 4 })
    expect(applyTaskLogUpdate(buffer, { log: '+tail', seq: 8, append: true, firstLine: 1 })).toBe(
      'append'
    )
    expect(buffer.log).toBe('snapshot+tail')
  })

  it('完整快照在前端裁剪显示窗口时推进实际首行号', () => {
    const buffer = state()
    applyTaskLogUpdate(buffer, {
      log: `head\n${'x'.repeat(LOG_BUFFER_MAX_CHARS)}`,
      seq: 8,
      append: false,
      firstLine: 10,
    })
    expect(buffer.log).toBe('x'.repeat(LOG_BUFFER_MAX_CHARS))
    expect(buffer.logFirstLine).toBe(11)
    expect(buffer.logSeq).toBe(8)
  })

  it('重置和清空通过替换包生效', () => {
    const buffer = state()
    applyTaskLogUpdate(buffer, { log: 'old', seq: 1, append: false, firstLine: 5 })
    applyTaskLogUpdate(buffer, { log: '', seq: 2, append: false, firstLine: 1 })
    expect(buffer.log).toBe('')
    expect(buffer.logFirstLine).toBe(1)
    expect(buffer.logSeq).toBe(2)
  })
})
