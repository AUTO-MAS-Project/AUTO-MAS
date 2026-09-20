import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./useSchedulerLogic.ts', import.meta.url), 'utf8')

/** 取 useSchedulerLogic 内某个顶层 const 声明的函数体（到下一个同缩进的 const 为止） */
const bodyOf = (declaration: string) => {
  const from = source.indexOf(declaration)
  expect(from, `缺少声明: ${declaration}`).toBeGreaterThan(-1)
  const rest = source.slice(from + declaration.length)
  const next = rest.indexOf('\n  const ')
  return next === -1 ? rest : rest.slice(0, next)
}

describe('调度台任务订阅归属', () => {
  it('状态同步不重复订阅（运行期状态每秒推送，重复调用只会刷日志）', () => {
    expect(bodyOf('const applyRuntimeStateToTab = (')).not.toContain('subscribeToTask(')
  })

  it('建台、启动与恢复路径仍会建立订阅', () => {
    expect(bodyOf('const createSchedulerTabForTask = (')).toContain('subscribeToTask(')
    expect(bodyOf('const trackStartedTask = (')).toContain('subscribeToTask(')
    expect(bodyOf('const startTask = async')).toContain('subscribeToTask(')
    expect(bodyOf('const initialize = async () => {')).toContain('subscribeToTask(')
  })
})
