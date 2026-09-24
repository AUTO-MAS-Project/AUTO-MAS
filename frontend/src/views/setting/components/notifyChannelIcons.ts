import {
  ApiOutlined,
  BellOutlined,
  MailOutlined,
  MessageOutlined,
  QqOutlined,
  SendOutlined,
  SignalFilled,
  WechatOutlined,
} from '@ant-design/icons-vue'
import type { Component } from 'vue'

// 描述表 icon 标识 → antd 图标组件；未知标识降级为铃铛
const ICONS: Record<string, Component> = {
  bell: BellOutlined,
  mail: MailOutlined,
  plane: SendOutlined,
  chat: MessageOutlined,
  signal: SignalFilled,
  wechat: WechatOutlined,
  qq: QqOutlined,
  webhook: ApiOutlined,
}

// 图标主色（微信绿 / QQ 蓝等品牌色，其余按语义就近取色）
const COLORS: Record<string, string> = {
  bell: '#8c8c8c',
  mail: '#1677ff',
  plane: '#13c2c2',
  chat: '#722ed1',
  signal: '#fa8c16',
  wechat: '#07c160',
  qq: '#12b7f5',
  webhook: '#597ef7',
}

export function channelIcon(icon: string | null | undefined): Component {
  return (icon != null && ICONS[icon]) || BellOutlined
}

export function channelIconColor(icon: string | null | undefined): string {
  return (icon != null && COLORS[icon]) || '#8c8c8c'
}
