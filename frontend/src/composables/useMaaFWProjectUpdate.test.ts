import { describe, expect, it } from 'vitest'

import { resolveAutoUpdateMode, resolveCdkHint, resolveCdkWarning } from './useMaaFWProjectUpdate'

describe('resolveAutoUpdateMode', () => {
  it('新字段合法时直接采用', () => {
    expect(resolveAutoUpdateMode({ AutoUpdateMode: 'Off', IfAutoUpdate: true })).toBe('Off')
    expect(resolveAutoUpdateMode({ AutoUpdateMode: 'AfterRun', IfAutoUpdate: false })).toBe(
      'AfterRun'
    )
    expect(resolveAutoUpdateMode({ AutoUpdateMode: 'BeforeRun' })).toBe('BeforeRun')
  })

  it('旧配置 IfAutoUpdate=false 映射为不更新', () => {
    expect(resolveAutoUpdateMode({ IfAutoUpdate: false })).toBe('Off')
  })

  it('旧配置 IfAutoUpdate=true 或缺失映射为运行前', () => {
    expect(resolveAutoUpdateMode({ IfAutoUpdate: true })).toBe('BeforeRun')
    expect(resolveAutoUpdateMode({})).toBe('BeforeRun')
    expect(resolveAutoUpdateMode(null)).toBe('BeforeRun')
    expect(resolveAutoUpdateMode(undefined)).toBe('BeforeRun')
  })

  it('新字段非法时退回旧字段映射', () => {
    expect(resolveAutoUpdateMode({ AutoUpdateMode: 'Sometimes', IfAutoUpdate: false })).toBe('Off')
    expect(resolveAutoUpdateMode({ AutoUpdateMode: 1, IfAutoUpdate: true })).toBe('BeforeRun')
    expect(resolveAutoUpdateMode({ AutoUpdateMode: '' })).toBe('BeforeRun')
  })
})

describe('resolveCdkWarning', () => {
  it('ok / absent / 缺失 不提示', () => {
    expect(resolveCdkWarning({ cdkStatus: 'ok', cdkMessage: '正常' })).toBeNull()
    expect(resolveCdkWarning({ cdkStatus: 'absent', cdkMessage: '未填写' })).toBeNull()
    expect(resolveCdkWarning({})).toBeNull()
    expect(resolveCdkWarning(null)).toBeNull()
    expect(resolveCdkWarning({ cdkStatus: '   ' })).toBeNull()
  })

  it('未填 CDK 只在更新源是 Mirror 酱时才提示：后端不会替用户改走 GitHub', () => {
    expect(resolveCdkWarning({ cdkStatus: 'absent' }, 'GitHub')).toBeNull()
    expect(resolveCdkWarning({ cdkStatus: 'absent' }, null)).toBeNull()
    expect(
      resolveCdkWarning({ cdkStatus: 'absent', cdkMessage: '未填写 CDK' }, 'MirrorChyan')
    ).toEqual({ status: 'absent', message: '未填写 CDK' })
    expect(resolveCdkWarning({ cdkStatus: 'absent' }, 'MirrorChyan')).toEqual({
      status: 'absent',
      message: '',
    })
    // ok 与更新源无关，永远不提示
    expect(resolveCdkWarning({ cdkStatus: 'ok' }, 'MirrorChyan')).toBeNull()
  })

  it('其他状态返回后端文案，与更新源无关', () => {
    expect(resolveCdkWarning({ cdkStatus: 'expired', cdkMessage: 'CDK 已过期' }, 'GitHub')).toEqual(
      { status: 'expired', message: 'CDK 已过期' }
    )
    expect(resolveCdkWarning({ cdkStatus: 'expired', cdkMessage: 'CDK 已过期' })).toEqual({
      status: 'expired',
      message: 'CDK 已过期',
    })
    expect(resolveCdkWarning({ cdkStatus: 'quota', cdkMessage: ' 今日次数用尽 ' })).toEqual({
      status: 'quota',
      message: '今日次数用尽',
    })
  })

  it('后端没给文案时 message 为空串，交给页面兜底', () => {
    expect(resolveCdkWarning({ cdkStatus: 'blocked' })).toEqual({ status: 'blocked', message: '' })
    expect(resolveCdkWarning({ cdkStatus: 'invalid', cdkMessage: null })).toEqual({
      status: 'invalid',
      message: '',
    })
  })
})

describe('resolveCdkHint', () => {
  // 一律用本地时区构造时间：剩余天数按本地日历算，测试在哪个时区跑都一样
  const now = new Date(2026, 9, 11, 14, 0, 0).getTime() // 2026-10-11 14:00 本地
  const secondsAt = (date: Date) => Math.floor(date.getTime() / 1000)

  it('正常且剩余多于 7 天：普通灰色，天数按本地日历整天算', () => {
    const hint = resolveCdkHint('ok', secondsAt(new Date(2026, 10, 3, 9, 30)), now)
    expect(hint).toEqual({
      kind: 'remaining',
      warning: false,
      daysLeft: 23,
      dateText: '2026-11-03',
    })
  })

  it('剩余不超过 7 天用警告色，恰好 7 天也算', () => {
    expect(resolveCdkHint('ok', secondsAt(new Date(2026, 9, 18, 23, 0)), now)).toEqual({
      kind: 'remaining',
      warning: true,
      daysLeft: 7,
      dateText: '2026-10-18',
    })
    expect(resolveCdkHint('ok', secondsAt(new Date(2026, 9, 19, 0, 30)), now)?.warning).toBe(false)
  })

  it('今天晚些时候到期记 0 天（页面写不足 1 天）；明天凌晨到期记 1 天', () => {
    expect(resolveCdkHint('ok', secondsAt(new Date(2026, 9, 11, 23, 59)), now)).toEqual({
      kind: 'remaining',
      warning: true,
      daysLeft: 0,
      dateText: '2026-10-11',
    })
    expect(resolveCdkHint('ok', secondsAt(new Date(2026, 9, 12, 0, 5)), now)?.daysLeft).toBe(1)
  })

  it('到期时间已过按已过期提示，带上日期', () => {
    expect(resolveCdkHint('ok', secondsAt(new Date(2026, 9, 11, 13, 0)), now)).toEqual({
      kind: 'expired',
      warning: true,
      daysLeft: null,
      dateText: '2026-10-11',
    })
  })

  it('正常但服务端没给到期时间：什么都不显示', () => {
    expect(resolveCdkHint('ok', null, now)).toBeNull()
    expect(resolveCdkHint('ok', undefined, now)).toBeNull()
    expect(resolveCdkHint('ok', 0, now)).toBeNull()
    expect(resolveCdkHint('ok', 'soon', now)).toBeNull()
  })

  it('接受字符串形式的秒数', () => {
    expect(
      resolveCdkHint('ok', String(secondsAt(new Date(2026, 10, 3, 9, 30))), now)?.daysLeft
    ).toBe(23)
  })

  it('7001-7005 各自一种警告；过期知道日期就带上', () => {
    expect(resolveCdkHint('expired', null, now)).toEqual({
      kind: 'expired',
      warning: true,
      daysLeft: null,
      dateText: null,
    })
    expect(resolveCdkHint('expired', secondsAt(new Date(2026, 9, 1, 8, 0)), now)?.dateText).toBe(
      '2026-10-01'
    )
    for (const status of ['invalid', 'mismatched', 'blocked'] as const) {
      expect(resolveCdkHint(status, null, now)).toEqual({
        kind: status,
        warning: true,
        daysLeft: null,
        dateText: null,
      })
    }
  })

  it('次数用尽时知道剩余天数就一并给出', () => {
    expect(resolveCdkHint('quota', secondsAt(new Date(2026, 10, 3, 9, 30)), now)).toEqual({
      kind: 'quota',
      warning: true,
      daysLeft: 23,
      dateText: '2026-11-03',
    })
    expect(resolveCdkHint('quota', null, now)).toEqual({
      kind: 'quota',
      warning: true,
      daysLeft: null,
      dateText: null,
    })
  })

  it('没填、项目不支持、查询失败、未知状态：什么都不显示', () => {
    for (const status of ['absent', 'unsupported', 'error', '', '  ', 'weird', null, undefined]) {
      expect(resolveCdkHint(status, secondsAt(new Date(2026, 10, 3)), now)).toBeNull()
    }
  })
})
