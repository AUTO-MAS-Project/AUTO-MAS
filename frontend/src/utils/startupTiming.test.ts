import { afterEach, expect, it, vi } from 'vite-plus/test'

import { finishStartupStage } from './startupTiming'

const measureName = '启动/local-stage'

afterEach(() => {
  performance.clearMeasures(measureName)
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

it.each([false, true])('DEV=%s 时保留本地日志，仅开发环境生成 Performance 条目', development => {
  vi.stubEnv('DEV', development)
  const info = vi.fn()
  vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ info }) } })

  finishStartupStage('local-stage', performance.now())

  expect(info).toHaveBeenCalledWith(expect.stringContaining('local-stage'))
  expect(performance.getEntriesByName(measureName)).toHaveLength(development ? 1 : 0)
})
