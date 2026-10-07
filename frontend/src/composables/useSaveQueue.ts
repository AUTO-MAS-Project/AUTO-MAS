import { computed, reactive, ref } from 'vue'
import type { SaveState } from '@/utils/saveState'
import { toAppError } from '@/utils/appError'

/** 一次保存的终态：SaveState 去掉 idle / dirty / saving 三个过程态 */
export type SaveOutcome = Exclude<SaveState, 'idle' | 'dirty' | 'saving'>

/** 显式保存契约的返回：调用方按后端 reason 判定终态 */
export interface SaveOutcomeReport {
  outcome: SaveOutcome
  error?: unknown
}

interface EntryResult {
  outcome: SaveOutcome
  error?: unknown
  /** 原样交还调用方的值（enqueue 用它 resolve） */
  value: unknown
  /** run 自身是否抛错（enqueue 需要保持 reject 语义） */
  threw: boolean
}

interface Settler {
  settle: (result: EntryResult) => void
}

interface QueuedSave {
  key: string | undefined
  exec: () => Promise<EntryResult>
  settlers: Settler[]
}

const UNRESOLVED_STATES: ReadonlySet<SaveState> = new Set<SaveState>([
  'failed_draft_kept',
  'failed_reverted',
  'rejected',
  'unknown',
])

/**
 * 把未归类的异常映射为保存终态。
 *
 * 只有调用方无法自行判定时才走到这里；判定依据是后端 reason / HTTP 状态，
 * 不是「前端看起来成功」——网络类异常一律落 unknown，禁止显示为已保存。
 */
export function classifySaveError(error: unknown): SaveOutcome {
  const appError = toAppError(error)
  switch (appError.kind) {
    case 'invalid_input':
    case 'conflict':
    case 'permission_denied':
    case 'protected_discard':
      return 'rejected'
    case 'network_unavailable':
    case 'backend_unavailable':
      return 'unknown'
    default:
      return 'failed_draft_kept'
  }
}

/**
 * 编辑页即时保存串行队列 + 保存状态机。
 *
 * 以「按序执行的队列」取代布尔 isSaving 互斥：布尔守卫会在「上一次保存尚未返回」时
 * 直接丢弃紧随其后的改动，造成前后端状态失步；队列则逐条按序写回，不再丢保存。
 *
 * - `enqueue(run)`：把一次保存排到队尾，返回该次保存自身的结果；正常返回＝后端已确认落盘；
 * - `enqueue(run, key)`：同一 key 的连续改动在尚未开始执行时只保留最后一次，
 *   早先排队的调用方与最后一次共享同一结果；
 * - `enqueueSave(run, key)`：显式契约，由调用方按后端 reason 返回终态（草稿保留 / 已回读旧值 /
 *   拒绝 / 丢弃 / 未知），队列只负责记录，不猜；
 * - 任一保存抛错只让它自己的 promise 拒绝，不阻塞后面的保存；
 * - `state` 是页面级状态（dirty → saving → 终态），`fieldStates` 是字段级状态；
 * - `canLeave` 为 false 时禁止离开：仍有在途保存，或存在失败草稿 / 结果未知；
 * - `unknown` 只能经查询终态（`markResolved`）或下一次成功保存转出，不会自愈为已保存。
 */
export const useSaveQueue = () => {
  const running = ref(false)
  const queueLength = ref(0)
  const lastOutcome = ref<SaveState>('idle')
  const fieldStates = reactive<Record<string, SaveState>>({})

  const queue: QueuedSave[] = []
  const idleWaiters: Array<() => void> = []
  let draining = false

  /** 页面级状态：有排队＝dirty，正在写＝saving，否则＝最后一次保存的终态 */
  const state = computed<SaveState>(() =>
    running.value ? 'saving' : queueLength.value > 0 ? 'dirty' : lastOutcome.value
  )

  /** 队列非空（含在途）期间为 true，供模板 :loading / :disabled 复用 */
  const isSaving = computed(() => running.value || queueLength.value > 0)

  const hasQueuedForKey = (key: string | undefined) =>
    key !== undefined && queue.some(entry => entry.key === key)

  const setFieldState = (key: string | undefined, value: SaveState) => {
    if (key !== undefined) fieldStates[key] = value
  }

  const flushIdleWaiters = () => {
    if (running.value || queue.length > 0) return
    idleWaiters.splice(0, idleWaiters.length).forEach(resolve => resolve())
  }

  const drain = async () => {
    if (draining) return
    draining = true
    running.value = true
    try {
      while (queue.length > 0) {
        const entry = queue.shift() as QueuedSave
        queueLength.value = queue.length
        // 同一 key 还有更新的保存排队时，字段保持 dirty 而不是假装正在写最新值
        setFieldState(entry.key, hasQueuedForKey(entry.key) ? 'dirty' : 'saving')
        const result = await entry.exec()
        const settled: SaveState = hasQueuedForKey(entry.key) ? 'dirty' : result.outcome
        lastOutcome.value = settled
        setFieldState(entry.key, settled)
        entry.settlers.forEach(settler => settler.settle(result))
      }
    } finally {
      draining = false
      running.value = false
      queueLength.value = queue.length
      flushIdleWaiters()
    }
  }

  const push = (key: string | undefined, exec: () => Promise<EntryResult>, settler: Settler) => {
    setFieldState(key, 'dirty')
    const pending = key === undefined ? undefined : queue.find(entry => entry.key === key)
    if (pending) {
      pending.exec = exec
      pending.settlers.push(settler)
    } else {
      queue.push({ key, exec, settlers: [settler] })
    }
    queueLength.value = queue.length
    void drain()
  }

  const enqueue = <T>(run: () => Promise<T>, key?: string): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      const exec = async (): Promise<EntryResult> => {
        try {
          const value = await run()
          return { outcome: 'saved', value, threw: false }
        } catch (error) {
          return { outcome: classifySaveError(error), error, value: undefined, threw: true }
        }
      }
      push(key, exec, {
        settle: result => (result.threw ? reject(result.error) : resolve(result.value as T)),
      })
    })

  const enqueueSave = (
    run: () => Promise<SaveOutcomeReport | void>,
    key?: string
  ): Promise<SaveOutcomeReport> =>
    new Promise<SaveOutcomeReport>(resolve => {
      const exec = async (): Promise<EntryResult> => {
        try {
          const report = (await run()) ?? { outcome: 'saved' as SaveOutcome }
          return { outcome: report.outcome, error: report.error, value: report, threw: false }
        } catch (error) {
          const outcome = classifySaveError(error)
          return { outcome, error, value: { outcome, error }, threw: true }
        }
      }
      push(key, exec, { settle: result => resolve(result.value as SaveOutcomeReport) })
    })

  /** 当前还排着（含正在执行）的保存数：调用方据此判断自己是不是最后一个 */
  const pendingCount = () => queueLength.value + (running.value ? 1 : 0)

  /** 等待队列彻底排空（含在途请求），供离开守卫 / 应用关闭使用 */
  const waitForIdle = (): Promise<void> => {
    if (!running.value && queue.length === 0) return Promise.resolve()
    return new Promise<void>(resolve => {
      idleWaiters.push(resolve)
    })
  }

  /** 外部查询确认了 unknown / 失败态的终值（例如回读后端真值后），由调用方驱动 */
  const markResolved = (key: string | undefined, outcome: SaveOutcome) => {
    lastOutcome.value = outcome
    setFieldState(key, outcome)
  }

  const hasUnresolved = computed(
    () =>
      UNRESOLVED_STATES.has(state.value) ||
      Object.values(fieldStates).some(fieldState => UNRESOLVED_STATES.has(fieldState))
  )

  /** 允许离开：没有在途保存，也没有失败草稿 / 结果未知 */
  const canLeave = computed(() => !isSaving.value && !hasUnresolved.value)

  const reset = () => {
    Object.keys(fieldStates).forEach(key => {
      delete fieldStates[key]
    })
    lastOutcome.value = 'idle'
  }

  return {
    isSaving,
    state,
    fieldStates,
    hasUnresolved,
    canLeave,
    enqueue,
    enqueueSave,
    pendingCount,
    waitForIdle,
    markResolved,
    reset,
  }
}

export type SaveQueue = ReturnType<typeof useSaveQueue>
