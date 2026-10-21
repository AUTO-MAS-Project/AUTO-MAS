// 配置中心授权为全局设备会话；页面重挂载也必须先完成旧弹窗的撤销。
let authTail: Promise<unknown> = Promise.resolve()

export function queueGeneralShareAuthAction<T>(action: () => Promise<T>): Promise<T> {
  const run = authTail.then(action, action)
  authTail = run.then(
    () => undefined,
    () => undefined
  )
  return run
}

export const waitForGeneralShareAuth = () => authTail
