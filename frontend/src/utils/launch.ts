/**
 * 「比平时慢一些」这句提示的阈值。
 *
 * 按实测的后端启动耗时定：`auto_mas.backend.startup.duration` 打点近 30 天成功 3018 次，
 * p50 5.3s、p90 14.7s、p95 19.5s；本机冷启动 4.3–13.5s，热启动 1.5–4s。取 20s ≈ p95，
 * 既不会在正常启动里亮起来，离 `waitUntilReady` 的 60s 硬超时也还有 40s 可用。
 *
 * 受管链路每次多跑 `workspace check` 与 `bootstrap --if-needed`，比上面的样本更慢，
 * 所以 20s 是下限；受管链路铺开后应按 release 过滤同一指标重新核一次。
 */
export const SLOW_LAUNCH_THRESHOLD_MS = 20_000

/**
 * 启动卡住时唯一能给用户的出口：把日志窗口打开。
 *
 * 固定落在前端日志：这一路径上后端多半还没起来，`debug/app.log` 要么不存在、要么还停在
 * 上一轮，日志页默认选中它的话打开就是一片空白；启动这一程的记录全在主进程写的
 * `debug/frontend.log` 里。
 */
export async function openLaunchLogWindow(scope: string): Promise<void> {
  try {
    const result = await window.electronAPI.openLogWindow?.('frontend')
    if (result?.success === false) {
      window.electronAPI.getLogger(scope).error(`打开日志窗口失败: ${result.error ?? '未知原因'}`)
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    window.electronAPI.getLogger(scope).error(`打开日志窗口失败: ${errorMessage}`)
  }
}
