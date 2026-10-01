import { describe, expect, it } from 'vitest'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { buildStartTaskRequest } from './schedulerStartRequest'

describe('buildStartTaskRequest', () => {
  it('脚本自动代理显式发送不连续的 A+C 用户', () => {
    expect(buildStartTaskRequest('script', TaskCreateIn.mode.AUTO_PROXY, null, ['a', 'c'])).toEqual(
      {
        taskId: 'script',
        mode: TaskCreateIn.mode.AUTO_PROXY,
        userIds: ['a', 'c'],
      }
    )
  })

  it('空数组仍发送 userIds，不能退化为运行全部用户', () => {
    expect(buildStartTaskRequest('script', TaskCreateIn.mode.AUTO_PROXY, null, [])).toEqual({
      taskId: 'script',
      mode: TaskCreateIn.mode.AUTO_PROXY,
      userIds: [],
    })
  })

  it('队列和非自动代理模式不发送用户范围', () => {
    expect(buildStartTaskRequest('queue', TaskCreateIn.mode.CYCLE_RUN, 'script-2', ['a'])).toEqual({
      taskId: 'queue',
      mode: TaskCreateIn.mode.CYCLE_RUN,
      resumeFromScriptId: 'script-2',
    })
    expect(buildStartTaskRequest('script', TaskCreateIn.mode.AUTO_PROXY, null, undefined)).toEqual({
      taskId: 'script',
      mode: TaskCreateIn.mode.AUTO_PROXY,
    })
  })
})
