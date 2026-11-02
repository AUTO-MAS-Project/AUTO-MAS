import { describe, expect, it } from 'vite-plus/test'
import { sanitizeMainSentryEvent } from './sentryPrivacy'

describe('主进程恢复诊断脱敏', () => {
  it('保留恢复诊断数值，移除自由文本、用户与未知字段', () => {
    const event = sanitizeMainSentryEvent({
      tags: { component: 'electron-main', renderer_gone_reason: 'killed' },
      user: { email: 'private@example.invalid' },
      extra: {
        exitCode: 1073807364,
        crashCount: 2,
        detail: 'C:\\Users\\private\\config',
        command: 'private command',
      },
    })
    expect(event.extra).toEqual({ exitCode: 1073807364, crashCount: 2 })
    expect(event.user).toBeUndefined()
  })

  it('普通事件与非法数值不获得恢复诊断豁免', () => {
    expect(sanitizeMainSentryEvent({ extra: { exitCode: 1 } }).extra).toBeUndefined()
    expect(
      sanitizeMainSentryEvent({
        tags: { component: 'electron-main', renderer_gone_reason: 'killed' },
        extra: { exitCode: '1', crashCount: { value: 1 }, durationMs: Infinity },
      }).extra
    ).toBeUndefined()
  })
})
