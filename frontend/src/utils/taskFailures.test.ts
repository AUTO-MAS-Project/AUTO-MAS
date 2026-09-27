import { describe, expect, it } from 'vitest'
import type { WSTaskScriptInfoData } from '@/services/websocket/types'
import { countTaskFailures, resolveTaskCompletionFeedback } from './taskFailures'

const script = (status: string, users: string[] = [], id = 'script'): WSTaskScriptInfoData => ({
  script_id: id,
  name: id,
  status,
  userList: users.map((userStatus, index) => ({
    user_id: `${id}-u${index}`,
    name: `u${index}`,
    status: userStatus,
  })),
})

describe('countTaskFailures', () => {
  it('用户异常：脚本与用户都计数', () => {
    expect(countTaskFailures([script('异常', ['异常'])])).toEqual({ scripts: 1, users: 1 })
    expect(
      countTaskFailures([
        script('完成', ['完成', '异常', '异常'], 'a'),
        script('完成', ['完成'], 'b'),
      ])
    ).toEqual({ scripts: 1, users: 2 })
  })

  it('只有脚本级异常（没轮到用户就失败）：用户数为 0', () => {
    expect(countTaskFailures([script('异常', ['等待'])])).toEqual({ scripts: 1, users: 0 })
  })

  it('全部成功或跳过：都是 0', () => {
    expect(
      countTaskFailures([script('完成', ['完成', '跳过'], 'a'), script('完成', [], 'b')])
    ).toEqual({ scripts: 0, users: 0 })
  })

  it('task_info 为空或缺失：都是 0', () => {
    expect(countTaskFailures([])).toEqual({ scripts: 0, users: 0 })
    expect(countTaskFailures(undefined)).toEqual({ scripts: 0, users: 0 })
    expect(countTaskFailures(null)).toEqual({ scripts: 0, users: 0 })
  })

  it('userList 缺失不报错', () => {
    const bare = { script_id: 's', name: 's', status: '异常' } as WSTaskScriptInfoData
    expect(countTaskFailures([bare])).toEqual({ scripts: 1, users: 0 })
  })
})

describe('resolveTaskCompletionFeedback', () => {
  it('outcome=success 但唯一用户异常：不报任务完成', () => {
    expect(
      resolveTaskCompletionFeedback({
        outcome: 'success',
        task_info: [script('异常', ['异常'])],
      })
    ).toEqual({ kind: 'partialFailure', failures: { scripts: 1, users: 1 } })
  })

  it('outcome=success 且全部成功：照旧报完成', () => {
    expect(
      resolveTaskCompletionFeedback({ outcome: 'success', task_info: [script('完成', ['完成'])] })
    ).toEqual({ kind: 'success' })
    expect(resolveTaskCompletionFeedback({ outcome: 'success', task_info: [] })).toEqual({
      kind: 'success',
    })
  })

  it('error / cancelled 不受 task_info 影响', () => {
    const failed = [script('异常', ['异常'])]
    expect(resolveTaskCompletionFeedback({ outcome: 'error', task_info: failed })).toEqual({
      kind: 'error',
    })
    expect(resolveTaskCompletionFeedback({ outcome: 'error', task_info: [] })).toEqual({
      kind: 'error',
    })
    expect(resolveTaskCompletionFeedback({ outcome: 'cancelled', task_info: failed })).toEqual({
      kind: 'cancelled',
    })
  })
})
