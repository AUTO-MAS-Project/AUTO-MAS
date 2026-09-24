import { describe, expect, it } from 'vitest'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { buildStartTaskRequest } from './schedulerStartRequest'

const AUTO = TaskCreateIn.mode.AUTO_PROXY
const empty = { resumeFromScriptId: null, selectedUserId: null, resumeFromUserId: null }

describe('buildStartTaskRequest', () => {
  it('什么都不选时只带任务与模式（从第一个用户开始 = 不传字段）', () => {
    expect(buildStartTaskRequest('s', AUTO, empty)).toEqual({ taskId: 's', mode: AUTO })
  })

  it('选了从某用户开始时带上 resumeFromUserId', () => {
    expect(buildStartTaskRequest('s', AUTO, { ...empty, resumeFromUserId: 'u2' })).toEqual({
      taskId: 's',
      mode: AUTO,
      resumeFromUserId: 'u2',
    })
  })

  it('单独运行指定用户时带上 userId', () => {
    expect(buildStartTaskRequest('s', AUTO, { ...empty, selectedUserId: 'u1' })).toEqual({
      taskId: 's',
      mode: AUTO,
      userId: 'u1',
    })
  })

  it('两者都有值时只带 userId，绝不同时发给后端', () => {
    const body = buildStartTaskRequest('s', AUTO, {
      ...empty,
      selectedUserId: 'u1',
      resumeFromUserId: 'u2',
    })
    expect(body.userId).toBe('u1')
    expect(body).not.toHaveProperty('resumeFromUserId')
  })

  it('非自动代理模式不带任何用户范围', () => {
    const body = buildStartTaskRequest('q', TaskCreateIn.mode.CYCLE_RUN, {
      ...empty,
      selectedUserId: 'u1',
      resumeFromUserId: 'u2',
    })
    expect(body).toEqual({ taskId: 'q', mode: TaskCreateIn.mode.CYCLE_RUN })
  })

  it('队列从某脚本开始照旧带 resumeFromScriptId', () => {
    expect(buildStartTaskRequest('q', AUTO, { ...empty, resumeFromScriptId: 's2' })).toEqual({
      taskId: 'q',
      mode: AUTO,
      resumeFromScriptId: 's2',
    })
  })
})
