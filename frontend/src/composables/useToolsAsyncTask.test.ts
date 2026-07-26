/**
 * Lane 8：工具页异步任务状态管理测试。
 *
 * 覆盖：
 * - 状态转换：idle → running → success/failure/cancelled
 * - 进度更新
 * - AbortController 取消信号
 * - run() 自动状态管理
 * - canCancel / canRetry / progressPercent 计算属性
 */
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { useToolsAsyncTask } from './useToolsAsyncTask'

describe('useToolsAsyncTask', () => {
  it('starts in idle state', () => {
    const task = useToolsAsyncTask({ taskName: '测试任务' })
    expect(task.status.value).toBe('idle')
    expect(task.error.value).toBeNull()
    expect(task.progress.value).toBeNull()
    expect(task.isRunning.value).toBe(false)
    expect(task.canCancel.value).toBe(false)
    expect(task.canRetry.value).toBe(false)
  })

  describe('start', () => {
    it('transitions to running and returns an AbortSignal', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      const signal = task.start()
      expect(task.status.value).toBe('running')
      expect(signal.aborted).toBe(false)
      expect(task.isRunning.value).toBe(true)
      expect(task.canCancel.value).toBe(true)
    })

    it('initializes progress when total is provided', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start(5)
      expect(task.progress.value).toEqual({ current: 0, total: 5 })
      expect(task.progressPercent.value).toBe(0)
    })

    it('does not initialize progress when total is not provided', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start()
      expect(task.progress.value).toBeNull()
    })
  })

  describe('updateProgress', () => {
    it('updates current and currentLabel', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start(3)
      task.updateProgress(1, '用户A')
      expect(task.progress.value).toEqual({ current: 1, total: 3, currentLabel: '用户A' })
      expect(task.progressPercent.value).toBeCloseTo(33.33, 1)
    })

    it('does nothing when progress is null', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start()
      task.updateProgress(1)
      expect(task.progress.value).toBeNull()
    })
  })

  describe('succeed', () => {
    it('transitions to success', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start()
      task.succeed()
      expect(task.status.value).toBe('success')
      expect(task.isFinished.value).toBe(true)
      expect(task.finishedAt.value).not.toBeNull()
    })
  })

  describe('fail', () => {
    it('transitions to failure with reason', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start()
      task.fail('网络超时')
      expect(task.status.value).toBe('failure')
      expect(task.error.value).toBe('网络超时')
      expect(task.canRetry.value).toBe(true)
    })
  })

  describe('cancel', () => {
    it('aborts the AbortController and sets cancelled status', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      const signal = task.start()
      task.cancel()
      expect(signal.aborted).toBe(true)
      expect(task.status.value).toBe('cancelled')
      expect(task.canRetry.value).toBe(true)
    })
  })

  describe('reset', () => {
    it('returns to idle state', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start()
      task.fail('err')
      task.reset()
      expect(task.status.value).toBe('idle')
      expect(task.error.value).toBeNull()
      expect(task.progress.value).toBeNull()
    })
  })

  describe('run', () => {
    it('auto-manages success state when fn completes', async () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      await task.run(async () => {
        // success
      })
      expect(task.status.value).toBe('success')
    })

    it('auto-manages failure state when fn throws', async () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      await task.run(async () => {
        throw new Error('执行失败')
      })
      expect(task.status.value).toBe('failure')
      expect(task.error.value).toBe('执行失败')
    })

    it('transitions to cancelled when signal is aborted inside fn', async () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      await task.run(async signal => {
        task.cancel()
        expect(signal.aborted).toBe(true)
      })
      expect(task.status.value).toBe('cancelled')
    })

    it('handles AbortError thrown by fetch-like calls', async () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      await task.run(async () => {
        const err = new DOMException('Aborted', 'AbortError')
        throw err
      })
      expect(task.status.value).toBe('cancelled')
    })

    it('passes total to progress when provided', async () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      await task.run(async signal => {
        expect(task.progress.value).toEqual({ current: 0, total: 3 })
        task.updateProgress(1, 'A')
        task.updateProgress(2, 'B')
        task.updateProgress(3, 'C')
      }, 3)
      expect(task.status.value).toBe('success')
      expect(task.progressPercent.value).toBe(100)
    })

    it('ignores a stale task completion after retry starts a new generation', async () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      let resolveOldTask: (() => void) | undefined
      const oldRun = task.run(
        () =>
          new Promise<void>(resolve => {
            resolveOldTask = resolve
          })
      )

      task.cancel()
      await task.run(async () => undefined)
      expect(task.status.value).toBe('success')

      resolveOldTask?.()
      await oldRun
      expect(task.status.value).toBe('success')
    })
  })

  describe('progressPercent', () => {
    it('returns 0 when progress is null', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      expect(task.progressPercent.value).toBe(0)
    })

    it('returns 0 when total is 0', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start(0)
      expect(task.progressPercent.value).toBe(0)
    })

    it('caps at 100', () => {
      const task = useToolsAsyncTask({ taskName: '测试' })
      task.start(2)
      task.updateProgress(5)
      expect(task.progressPercent.value).toBe(100)
    })
  })
})
