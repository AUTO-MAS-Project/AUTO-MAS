import { describe, expect, it } from 'vitest'
import type { NotifyChannelOut } from '@/api/models/NotifyChannelOut'
import {
  channelSummary,
  groupChannels,
  idleStateKey,
  normalizeControl,
  normalizeGroup,
  sortChannels,
} from './notifyChannelView'

const channel = (overrides: Partial<NotifyChannelOut>): NotifyChannelOut => ({
  key: 'mail',
  nameKey: 'setting.notify.mailSection',
  group: 'builtin',
  order: 20,
  kind: 'fields',
  scopes: ['global'],
  ...overrides,
})

const CLAW_EXTRAS = {
  clawConnected: { 'claw:weixin': false, 'claw:qq': true },
  webhookNames: ['飞书群机器人', '自建 ntfy'],
}

describe('normalizeControl / normalizeGroup', () => {
  it('未知控件降级为 text，未知分组归入 custom', () => {
    expect(normalizeControl('password')).toBe('password')
    expect(normalizeControl('rating')).toBe('text')
    expect(normalizeGroup('builtin')).toBe('builtin')
    expect(normalizeGroup('partner')).toBe('custom')
  })
})

describe('sortChannels', () => {
  it('按 order 升序且不改原数组', () => {
    const input = [channel({ key: 'b', order: 60 }), channel({ key: 'a', order: 10 })]
    const sorted = sortChannels(input)
    expect(sorted.map(c => c.key)).toEqual(['a', 'b'])
    expect(input.map(c => c.key)).toEqual(['b', 'a'])
  })
})

describe('groupChannels', () => {
  const channels = [
    channel({ key: 'system', order: 10, enableField: ['Notify', 'IfPushPlyer'] }),
    channel({ key: 'mail', enableField: ['Notify', 'IfSendMail'] }),
    channel({
      key: 'openclaw_weixin',
      order: 70,
      customBlock: 'claw:weixin',
      enableField: ['Notify', 'IfOpenClawWeixin'],
    }),
    channel({ key: 'webhook', order: 50, group: 'custom', kind: 'custom', customBlock: 'webhook_list' }),
    channel({ key: 'policy', order: 90, kind: 'policy' }),
    channel({ key: 'user_only', order: 95, scopes: ['user'], enableField: ['Notify', 'IfSendMail'] }),
  ]

  it('按开关分到已激活/未激活，policy 与 custom 单列，过滤未知作用域', () => {
    const values = { IfPushPlyer: true, IfSendMail: false }
    const groups = groupChannels(channels, 'global', values)
    expect(groups.active.map(c => c.key)).toEqual(['system'])
    expect(groups.idle.map(c => c.key)).toEqual(['mail', 'openclaw_weixin'])
    expect(groups.custom.map(c => c.key)).toEqual(['webhook'])
    expect(groups.policy?.key).toBe('policy')
  })

  it('未绑定的 Claw 未启用行显示「未绑定」，已绑定但开关关着显示「未启用」', () => {
    const weixin = channel({ key: 'openclaw_weixin', customBlock: 'claw:weixin' })
    const qq = channel({ key: 'openclaw_qq', customBlock: 'claw:qq' })
    const mail = channel({ key: 'mail' })
    expect(idleStateKey(weixin, CLAW_EXTRAS)).toBe('stateUnbound')
    expect(idleStateKey(qq, CLAW_EXTRAS)).toBe('stateDisabled')
    expect(idleStateKey(mail, CLAW_EXTRAS)).toBe('stateDisabled')
  })
})

describe('channelSummary', () => {
  const t: (key: string, params?: Record<string, unknown>) => string = (key, params) => {
    const texts: Record<string, string> = {
      'setting.notify.summary.mail': 'SMTP: {SMTPServerAddress} · 收信: {ToAddress}',
      'setting.notify.summary.mailEmpty': '邮箱配置不完整',
      'setting.notify.summary.serverchan': 'SendKey 已配置',
      'setting.notify.summary.serverchanEmpty': 'SendKey 未配置',
      'setting.notify.summary.webhookEmpty': '尚未添加 Webhook',
    }
    let text = texts[key] ?? key
    for (const [name, value] of Object.entries(params ?? {})) {
      text = text.split(`{${name}}`).join(String(value))
    }
    return text
  }

  it('插值参与字段；任一为空即降级到 Empty 变体，不出现半截串', () => {
    const mail = channel({ summaryKey: 'setting.notify.summary.mail', summaryFields: ['SMTPServerAddress', 'ToAddress'] })
    expect(channelSummary(mail, { SMTPServerAddress: 'smtp.qq.com', ToAddress: 'me@qq.com' }, t, CLAW_EXTRAS)).toBe(
      'SMTP: smtp.qq.com · 收信: me@qq.com'
    )
    expect(channelSummary(mail, { SMTPServerAddress: '', ToAddress: 'me@qq.com' }, t, CLAW_EXTRAS)).toBe('邮箱配置不完整')
    expect(channelSummary(mail, { SMTPServerAddress: '', ToAddress: '' }, t, CLAW_EXTRAS)).toBe('邮箱配置不完整')
  })

  it('没有参与字段的静态摘要不降级；键缺失时返回空串', () => {
    const serverchan = channel({ summaryKey: 'setting.notify.summary.serverchan', summaryFields: [] })
    expect(channelSummary(serverchan, {}, t, CLAW_EXTRAS)).toBe('SendKey 已配置')
    expect(channelSummary(channel({ summaryKey: null }), {}, t, CLAW_EXTRAS)).toBe('')
  })

  it('Webhook 例外：非空拼接条目名，空列表用 Empty 变体', () => {
    const webhook = channel({ customBlock: 'webhook_list', summaryKey: 'setting.notify.summary.webhook' })
    expect(channelSummary(webhook, {}, t, CLAW_EXTRAS)).toBe('飞书群机器人、自建 ntfy')
    expect(channelSummary(webhook, {}, t, { ...CLAW_EXTRAS, webhookNames: [] })).toBe('尚未添加 Webhook')
  })
})
