import { describe, expect, it, vi, beforeEach } from 'vite-plus/test'
import { TaskMode } from '@/api'

const probe = vi.hoisted(() => ({ start: vi.fn(), finish: vi.fn() }))
vi.mock('@/api/services/Service', () => ({ Service: { addTaskApiDispatchStartPost: probe.start } }))
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: (event: string) => ({
    finish: (props: unknown) => probe.finish(event, props),
  }),
  analyticsScriptType: () => 'general',
  getAnalyticsScriptType: () => 'general',
}))
vi.mock('@/composables/useTaskRuntimeState', () => ({
  getTaskRuntimeStates: () => [],
  registerAcceptedTask: vi.fn(),
  reconcileStoppedTask: vi.fn(),
}))
import { requestTaskStart } from './useTaskApi'

beforeEach(() => vi.clearAllMocks())

describe('任务要求树请求与统计边界', () => {
  it('直接发送同一要求树，每个受理事件只记录一次且不发送业务标识', async () => {
    const request = {
      mode: TaskMode.AUTO_PROXY,
      tasks: { '0': { uid: 'private-queue', children: { '0': { uid: 'private-item' } } } },
    }
    probe.start.mockResolvedValue({ code: 200, taskId: 'private-run' })
    await requestTaskStart(request, { source: 'scheduler', target_kind: 'queue' })
    expect(probe.start).toHaveBeenCalledExactlyOnceWith(request)
    expect(probe.finish.mock.calls).toEqual([
      [
        'task_resume_requested',
        {
          source: 'scheduler',
          resume_kind: 'scoped_users',
          scope_kind: 'queue_users',
          request_outcome: 'accepted',
        },
      ],
      [
        'task_start_result',
        {
          source: 'scheduler',
          target_kind: 'queue',
          mode: TaskMode.AUTO_PROXY,
          outcome: 'accepted',
        },
      ],
    ])
    expect(JSON.stringify(probe.finish.mock.calls)).not.toContain('private-')
  })
  it('请求失败只记录一次失败并继续抛出原错误', async () => {
    const error = new Error('offline')
    probe.start.mockRejectedValue(error)
    await expect(
      requestTaskStart({
        mode: TaskMode.AUTO_PROXY,
        tasks: { '0': { uid: '-', children: { '0': { uid: 'private-script' } } } },
      })
    ).rejects.toBe(error)
    expect(probe.finish.mock.calls).toEqual([
      [
        'task_start_result',
        { source: 'unknown', target_kind: 'script', mode: TaskMode.AUTO_PROXY, outcome: 'failure' },
      ],
    ])
  })
})
