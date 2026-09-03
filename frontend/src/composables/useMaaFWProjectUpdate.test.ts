import { describe, expect, it } from 'vitest'

import {
  resolveAutoUpdateMode,
  resolveCdkExpiry,
  resolveCdkWarning,
} from './useMaaFWProjectUpdate'

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

  it('其他状态返回后端文案', () => {
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

describe('resolveCdkExpiry', () => {
  const now = Date.UTC(2026, 8, 2, 12, 0, 0) // 2026-09-02T12:00:00Z
  const DAY = 24 * 60 * 60 * 1000
  const secondsAt = (ms: number) => Math.floor(ms / 1000)

  it('7 天内到期时给出剩余天数与日期', () => {
    const expiry = resolveCdkExpiry({ cdkExpiredTime: secondsAt(now + 3 * DAY) }, now)
    expect(expiry).not.toBeNull()
    expect(expiry?.daysLeft).toBe(3)
    expect(expiry?.dateText).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(expiry?.expiresAt.getTime()).toBe(secondsAt(now + 3 * DAY) * 1000)
  })

  it('恰好 7 天算在提示范围内，超过 7 天不提示', () => {
    expect(resolveCdkExpiry({ cdkExpiredTime: secondsAt(now + 7 * DAY) }, now)?.daysLeft).toBe(7)
    expect(resolveCdkExpiry({ cdkExpiredTime: secondsAt(now + 7 * DAY + 1000) }, now)).toBeNull()
    expect(resolveCdkExpiry({ cdkExpiredTime: secondsAt(now + 30 * DAY) }, now)).toBeNull()
  })

  it('已过期也返回，daysLeft 为 0 或负数', () => {
    expect(resolveCdkExpiry({ cdkExpiredTime: secondsAt(now - 2 * DAY) }, now)?.daysLeft).toBe(-2)
  })

  it('接受字符串形式的秒数', () => {
    expect(
      resolveCdkExpiry({ cdkExpiredTime: String(secondsAt(now + 1 * DAY)) }, now)?.daysLeft
    ).toBe(1)
  })

  it('缺失、非数字、非正数不提示', () => {
    expect(resolveCdkExpiry({}, now)).toBeNull()
    expect(resolveCdkExpiry(null, now)).toBeNull()
    expect(resolveCdkExpiry({ cdkExpiredTime: null }, now)).toBeNull()
    expect(resolveCdkExpiry({ cdkExpiredTime: 0 }, now)).toBeNull()
    expect(resolveCdkExpiry({ cdkExpiredTime: 'soon' }, now)).toBeNull()
  })
})
