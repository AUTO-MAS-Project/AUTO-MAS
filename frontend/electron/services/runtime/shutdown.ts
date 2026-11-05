// Runtime 的提交后恢复最多使用 60 秒独立 context；退出先留足收口时间，再结束进程。
export const RUNTIME_STOP_TIMEOUT_MS = 65_000
export const RUNTIME_KILL_WAIT_MS = 2_000

/** 等待任务落地，超时只返回 false，不把未完成视为成功。 */
export function waitForSettle(target: Promise<unknown>, timeoutMs: number): Promise<boolean> {
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve(false), timeoutMs)
    const done = (): void => {
      clearTimeout(timer)
      resolve(true)
    }
    target.then(done, done)
  })
}
