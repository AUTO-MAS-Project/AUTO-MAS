// 只写本地日志与浏览器 Performance 面板，不增加遥测事件。
const logger = () => window.electronAPI.getLogger('启动计时')

export function finishStartupStage(name: string, startedAt: number): void {
  const finishedAt = performance.now()
  // 生产 Sentry 会自动采集 Performance 条目；阶段计时只写本地日志。
  if (import.meta.env.DEV) {
    performance.measure(`启动/${name}`, { start: startedAt, end: finishedAt })
  }
  logger().info(
    `[启动计时] 前端/${name} 完成，阶段 ${(finishedAt - startedAt).toFixed(1)} ms，累计 ${finishedAt.toFixed(1)} ms`
  )
}

export async function measureStartup<T>(name: string, action: () => Promise<T>): Promise<T> {
  const startedAt = performance.now()
  logger().info(`[启动计时] 前端/${name} 开始`)
  try {
    const result = await action()
    finishStartupStage(name, startedAt)
    return result
  } catch (error) {
    logger().warn(
      `[启动计时] 前端/${name} 中断，阶段 ${(performance.now() - startedAt).toFixed(1)} ms`
    )
    throw error
  }
}
