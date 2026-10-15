// 只协调当前 renderer 的设置操作，不保存配置；页面卸载不代表在途写入已结束。
let tail: Promise<void> = Promise.resolve()
const cancelled = Symbol('settings-operation-cancelled')

/** 每个页面拥有独立作用域，共享执行顺序；只有读取可以提前停止等待。 */
export function createSettingsOperationQueue() {
  let active = true
  const pendingCallers = new Set<() => void>()
  const pendingReads = new Set<() => void>()

  const ensureActive = () => {
    if (!active) throw cancelled
  }

  const enqueue = <T>(operation: () => Promise<T>, cancelledValue: T): Promise<T> => {
    if (!active) return Promise.resolve(cancelledValue)

    return new Promise<T>((resolve, reject) => {
      const cancel = () => resolve(cancelledValue)
      pendingCallers.add(cancel)
      const result = tail.then(() => {
        ensureActive()
        return operation()
      })
      // 调用方取消只能结算外层 Promise；队列仍等待实际操作结束。
      tail = result.then(
        value => {
          pendingCallers.delete(cancel)
          resolve(value)
        },
        error => {
          pendingCallers.delete(cancel)
          if (error === cancelled) resolve(cancelledValue)
          else reject(error)
        }
      )
    })
  }

  const read = async <T>(request: () => Promise<T>): Promise<T> => {
    ensureActive()
    let cancel!: () => void
    const cancellation = new Promise<never>((_resolve, reject) => {
      cancel = () => reject(cancelled)
    })
    pendingReads.add(cancel)
    try {
      return await Promise.race([
        Promise.resolve().then(() => {
          ensureActive()
          return request()
        }),
        cancellation,
      ])
    } finally {
      pendingReads.delete(cancel)
    }
  }

  const dispose = () => {
    active = false
    for (const cancel of pendingCallers) cancel()
    for (const cancel of pendingReads) cancel()
    pendingCallers.clear()
    pendingReads.clear()
  }

  return { enqueue, read, ensureActive, isActive: () => active, dispose }
}
