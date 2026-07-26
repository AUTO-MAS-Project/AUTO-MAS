/**
 * Lane 8：工具页异步任务状态管理。
 *
 * 解决问题：
 * 1. 异步任务（如手动签到、批量操作）需要显示 running/success/failure/cancelled 状态。
 * 2. 失败时需要保留具体原因，支持重试。
 * 3. 长时间运行的任务需要支持取消（前端发起取消信号）。
 * 4. 批量任务需要显示进度（current/total）。
 *
 * 设计：
 * - 单实例任务：status + error + lastRunAt
 * - 批量任务：额外 progress = { current, total }
 * - 不引入 Pinia store，仅局部状态 + composable。
 * - 取消信号通过 AbortController 实现；调用方在 fetch 中传递 signal。
 */

import { ref, computed } from 'vue'

export type AsyncTaskStatus = 'idle' | 'running' | 'success' | 'failure' | 'cancelled'

export interface AsyncTaskProgress {
  /** 当前已完成数量（1-based） */
  current: number
  /** 总数 */
  total: number
  /** 当前正在处理的项描述（如账号名） */
  currentLabel?: string
}

export interface AsyncTaskState {
  status: AsyncTaskStatus
  error: string | null
  progress: AsyncTaskProgress | null
  startedAt: string | null
  finishedAt: string | null
}

export interface UseToolsAsyncTaskOptions {
  /** 任务名称，用于日志和 UI 展示 */
  taskName: string
}

export function useToolsAsyncTask(options: UseToolsAsyncTaskOptions) {
  const { taskName } = options

  const status = ref<AsyncTaskStatus>('idle')
  const error = ref<string | null>(null)
  const progress = ref<AsyncTaskProgress | null>(null)
  const startedAt = ref<string | null>(null)
  const finishedAt = ref<string | null>(null)

  /** 当前任务的 AbortController，用于取消 */
  let currentController: AbortController | null = null
  /** 隔离旧 Promise，防止取消或重试后的迟到结果覆盖当前任务。 */
  let taskGeneration = 0

  const isRunning = computed(() => status.value === 'running')
  const isFinished = computed(
    () => status.value === 'success' || status.value === 'failure' || status.value === 'cancelled'
  )
  const canCancel = computed(() => status.value === 'running')
  const canRetry = computed(() => status.value === 'failure' || status.value === 'cancelled')

  const progressPercent = computed(() => {
    if (!progress.value || progress.value.total === 0) return 0
    return Math.min((progress.value.current / progress.value.total) * 100, 100)
  })

  function reset(): void {
    taskGeneration += 1
    currentController?.abort()
    status.value = 'idle'
    error.value = null
    progress.value = null
    startedAt.value = null
    finishedAt.value = null
    currentController = null
  }

  function start(total?: number): AbortSignal {
    taskGeneration += 1
    currentController?.abort()
    status.value = 'running'
    error.value = null
    progress.value = total && total > 0 ? { current: 0, total } : null
    startedAt.value = new Date().toISOString()
    finishedAt.value = null

    currentController = new AbortController()
    return currentController.signal
  }

  function updateProgress(current: number, currentLabel?: string): void {
    if (!progress.value) return
    progress.value = {
      ...progress.value,
      current,
      currentLabel,
    }
  }

  function succeed(): void {
    status.value = 'success'
    finishedAt.value = new Date().toISOString()
    currentController = null
  }

  function fail(reason: string): void {
    status.value = 'failure'
    error.value = reason
    finishedAt.value = new Date().toISOString()
    currentController = null
  }

  function cancel(): void {
    if (currentController) {
      currentController.abort()
      currentController = null
    }
    taskGeneration += 1
    status.value = 'cancelled'
    finishedAt.value = new Date().toISOString()
  }

  /**
   * 运行一个异步任务，自动管理状态。
   *
   * @param fn 任务函数，接收 AbortSignal
   * @param total 批量任务的总数（可选）
   */
  async function run(fn: (signal: AbortSignal) => Promise<void>, total?: number): Promise<void> {
    const signal = start(total)
    const activeGeneration = taskGeneration
    try {
      await fn(signal)
      if (activeGeneration === taskGeneration && status.value === 'running') {
        succeed()
      }
    } catch (err) {
      if (activeGeneration !== taskGeneration) return
      if (signal.aborted || (err instanceof Error && err.name === 'AbortError')) {
        // 已通过 cancel() 设置状态
        if (status.value === 'running') {
          cancel()
        }
        return
      }
      const reason = err instanceof Error ? err.message : String(err)
      fail(reason)
    }
  }

  return {
    taskName,
    status,
    error,
    progress,
    startedAt,
    finishedAt,
    isRunning,
    isFinished,
    canCancel,
    canRetry,
    progressPercent,
    reset,
    start,
    updateProgress,
    succeed,
    fail,
    cancel,
    run,
  }
}
