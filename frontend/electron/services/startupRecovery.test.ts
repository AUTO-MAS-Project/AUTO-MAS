import { describe, expect, it } from 'vite-plus/test'

import { canRetryStartup } from './startupRecovery'

describe('桌面启动的下载失败分类', () => {
  it.each(['RUNTIME_LATEST_UNAVAILABLE', 'RUNTIME_BINARY_DOWNLOAD_FAILED'])(
    '%s 只在网络边界确认失败时自动重试',
    code => {
      const failure = { code, retryable: true, networkUnavailable: true as const }
      expect(canRetryStartup(failure)).toBe(true)
      expect(canRetryStartup({ code, retryable: true })).toBe(false)
    }
  )

  it('未知对齐异常保留手动处置，不自动重试', () => {
    expect(
      canRetryStartup({
        code: 'RUNTIME_BINARY_ALIGN_ERROR',
        retryable: true,
        remediation: ['retry', 'open-log'],
      })
    ).toBe(false)
  })
})
