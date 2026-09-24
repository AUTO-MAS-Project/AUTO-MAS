import type { NotifyChannelFieldOut } from '@/api/models/NotifyChannelFieldOut'
import type { NotifyChannelOut } from '@/api/models/NotifyChannelOut'

/** 词表取值函数；单独传入便于纯逻辑测试。 */
export type Translate = (key: string, params?: Record<string, unknown>) => string

export type ChannelScope = 'global' | 'user'

const KNOWN_CONTROLS = ['bool', 'text', 'password', 'url', 'select', 'json'] as const
export type FieldControl = (typeof KNOWN_CONTROLS)[number]

/** 未知 control 一律按文本框渲染，描述表新增控件类型时页面不至于空白。 */
export function normalizeControl(control: string): FieldControl {
  return (KNOWN_CONTROLS as readonly string[]).includes(control)
    ? (control as FieldControl)
    : 'text'
}

/** 未知分组归入「自定义」，避免描述表出现新分组时渠道卡片整张丢失。 */
export function normalizeGroup(group: string): 'builtin' | 'custom' {
  return group === 'builtin' ? 'builtin' : 'custom'
}

export function sortChannels<T extends { order: number }>(channels: readonly T[]): T[] {
  return [...channels].sort((a, b) => a.order - b.order)
}

export interface ChannelExtras {
  /** 各 custom_block 的 Claw 绑定状态，键为 custom_block（claw:weixin / claw:qq）。 */
  clawConnected: Record<string, boolean>
  /** Webhook 条目名，来自 WebhookManager 列表重载后的 emit。 */
  webhookNames: string[]
}

export interface ChannelGroups {
  policy: NotifyChannelOut | null
  active: NotifyChannelOut[]
  idle: NotifyChannelOut[]
  custom: NotifyChannelOut[]
}

/** 开关配置值是否打开；无开关的渠道（自定义 Webhook）恒为 false。 */
export function isChannelEnabled(
  channel: NotifyChannelOut,
  values: Record<string, unknown>
): boolean {
  const name = channel.enableField?.[1]
  return name != null && values[name] === true
}

/** 未启用行的状态文案键：Claw 未绑定时显示「未绑定」，其余显示「未启用」。 */
export function idleStateKey(
  channel: NotifyChannelOut,
  extras: ChannelExtras
): 'stateDisabled' | 'stateUnbound' {
  const block = channel.customBlock
  if (block != null && block in extras.clawConnected) {
    return extras.clawConnected[block] ? 'stateDisabled' : 'stateUnbound'
  }
  return 'stateDisabled'
}

export function groupChannels(
  channels: readonly NotifyChannelOut[],
  scope: ChannelScope,
  values: Record<string, unknown>
): ChannelGroups {
  const policy: NotifyChannelOut[] = []
  const active: NotifyChannelOut[] = []
  const idle: NotifyChannelOut[] = []
  const custom: NotifyChannelOut[] = []
  for (const channel of channels) {
    if (channel.scopes && !channel.scopes.includes(scope)) continue
    if (channel.kind === 'policy') {
      policy.push(channel)
    } else if (normalizeGroup(channel.group) === 'custom') {
      custom.push(channel)
    } else if (isChannelEnabled(channel, values)) {
      active.push(channel)
    } else {
      idle.push(channel)
    }
  }
  // policy 段唯一；取排序后第一个，多余的描述当脏数据丢弃
  return {
    policy: sortChannels(policy)[0] ?? null,
    active: sortChannels(active),
    idle: sortChannels(idle),
    custom: sortChannels(custom),
  }
}

/**
 * 卡片摘要。Webhook 是唯一例外：非空时直接拼接条目名，不走词表插值。
 * 空值变体的词表键约定为 `${summaryKey}Empty`——后端规格里的 `.empty` 后缀
 * 在 vue-i18n 里与正文键同路径冲突（mail 是字符串叶子就无法再挂 mail.empty），
 * 故用 Empty 后缀区分。
 * 规格对降级条件有两句冲突的表述（「全空才降级」与「不要出现半截串」），
 * 取后者：任一参与字段为空就降级，杜绝 `SMTP:  · 收信: me@qq.com` 这类空洞。
 */
export function channelSummary(
  channel: NotifyChannelOut,
  values: Record<string, unknown>,
  t: Translate,
  extras: ChannelExtras
): string {
  if (channel.customBlock === 'webhook_list') {
    return extras.webhookNames.length
      ? extras.webhookNames.join('、')
      : t(`${channel.summaryKey}Empty`)
  }
  const summaryKey = channel.summaryKey
  if (!summaryKey) return ''
  const fields = channel.summaryFields ?? []
  const hasEmpty = fields.length > 0 && fields.some(name => !values[name])
  const params: Record<string, unknown> = {}
  for (const name of fields) params[name] = values[name] ?? ''
  return t(hasEmpty ? `${summaryKey}Empty` : summaryKey, params)
}

/**
 * 描述端点失败时「通知内容」的兜底字段：字段语义固定，只复用既有词表键，
 * 保住三个全局推送策略可改（保存走 handleSettingChange，不依赖描述表）。
 * 正常态一律以后端描述表为准；下拉选项值是后端配置字面量，不能翻译。
 */
export const FALLBACK_POLICY_FIELDS: NotifyChannelFieldOut[] = [
  {
    group: 'Notify',
    name: 'SendTaskResultTime',
    labelKey: 'setting.notify.resultTime',
    control: 'select',
    options: [
      { value: '不推送', labelKey: 'setting.pushTime.never' },
      { value: '任何时刻', labelKey: 'setting.pushTime.always' },
      { value: '仅失败时', labelKey: 'setting.pushTime.failOnly' },
    ],
    tipKey: 'setting.notify.resultTimeTip',
  },
  {
    group: 'Notify',
    name: 'IfSendStatistic',
    labelKey: 'setting.notify.statistics',
    control: 'bool',
    tipKey: 'setting.notify.statisticsTip',
  },
  {
    group: 'Notify',
    name: 'IfSendSixStar',
    labelKey: 'setting.notify.recruit',
    control: 'bool',
    tipKey: 'setting.notify.recruitTip',
  },
]

/** 渠道在指定作用域下的字段列表；未知作用域返回空。 */
export function scopeFields(
  channel: NotifyChannelOut,
  scope: ChannelScope
): NotifyChannelFieldOut[] {
  return channel.fields?.[scope] ?? []
}
