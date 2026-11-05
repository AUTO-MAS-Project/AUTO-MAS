import { getLogger } from './logger'

/** 主进程的本地启动计时；累计值以 Node Performance 的进程起点为准。 */
export function recordDesktopStartup(name: string, startedAt = 0): void {
  const finishedAt = performance.now()
  getLogger('启动计时').info(
    `[启动计时] 桌面/${name}，阶段 ${(finishedAt - startedAt).toFixed(1)} ms，累计 ${finishedAt.toFixed(1)} ms`
  )
}
