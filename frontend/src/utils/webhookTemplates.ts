// Webhook 模板配置
export interface WebhookTemplate {
  name: string
  /** 词表 key：本文件是模块级常量，t() 在这里会被冻结在初始语言 */
  descriptionKey: string
  template: string
  headers?: Record<string, string>
  method: 'POST' | 'GET'
  example?: string
}

export const WEBHOOK_TEMPLATES: WebhookTemplate[] = [
  {
    name: 'Bark (iOS推送)',
    descriptionKey: 'misc.barkPushNotificationApp',
    template: '{"title": "{title}", "body": "{content}", "sound": "default"}',
    method: 'POST',
    example: 'https://api.day.app/your_key/',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'Server酱 (微信推送)',
    descriptionKey: 'misc.serverchanWechatPushService',
    template: '{"title": "{title}", "desp": "{content}"}',
    method: 'POST',
    example: 'https://sctapi.ftqq.com/your_key.send',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: '企业微信机器人',
    descriptionKey: 'misc.wecomGroupBot',
    template: '{"msgtype": "text", "text": {"content": "{title}\\n{content}"}}',
    method: 'POST',
    example: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'DingTalk (钉钉机器人)',
    descriptionKey: 'misc.dingtalkGroupBot',
    template: '{"msgtype": "text", "text": {"content": "{title}\\n{content}"}}',
    method: 'POST',
    example: 'https://oapi.dingtalk.com/robot/send?access_token=your_token',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'Telegram Bot',
    descriptionKey: 'misc.telegramBot',
    template: '{"chat_id": "your_chat_id", "text": "{title}\\n{content}"}',
    method: 'POST',
    example: 'https://api.telegram.org/bot{your_bot_token}/sendMessage',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'Discord Webhook',
    descriptionKey: 'misc.discordChannelWebhook',
    template: '{"content": "**{title}**\\n{content}"}',
    method: 'POST',
    example: 'https://discord.com/api/webhooks/your_webhook_url',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'Slack Webhook',
    descriptionKey: 'misc.slackChannelWebhook',
    template: '{"text": "{title}\\n{content}"}',
    method: 'POST',
    example: 'https://hooks.slack.com/services/your/webhook/url',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'PushPlus (微信推送)',
    descriptionKey: 'misc.pushplusWechatPushService',
    template: '{"token": "your_token", "title": "{title}", "content": "{content}"}',
    method: 'POST',
    example: 'http://www.pushplus.plus/send',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: 'OneBot 私聊',
    descriptionKey: 'misc.qqDirectMessageOver',
    template:
      '{"user_id": "YOUR_QQ_NUMBER", "message": [{"type": "text", "data": {"text": "{title}\\n{content}"}}]}',
    method: 'POST',
    example: 'http://服务器IP:端口/send_private_msg?access_token=YOUR_ACCESS_TOKEN',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: '自定义JSON',
    descriptionKey: 'misc.customJsonPayload',
    template: '{"message": "{title}: {content}", "timestamp": "{datetime}"}',
    method: 'POST',
    example: 'https://your-api.com/webhook',
    headers: {
      'Content-Type': 'application/json',
    },
  },
  {
    name: '自定义GET请求',
    descriptionKey: 'misc.notifyGetRequest',
    template: 'title={title}&content={content}&time={datetime}',
    method: 'GET',
    example: 'https://your-api.com/notify',
    headers: {},
  },
]

// 获取模板变量说明
export const TEMPLATE_VARIABLES = [
  { name: '{title}', description: '通知标题' },
  { name: '{content}', description: '通知内容' },
  { name: '{datetime}', description: '完整日期时间 (YYYY-MM-DD HH:MM:SS)' },
  { name: '{date}', description: '日期 (YYYY-MM-DD)' },
  { name: '{time}', description: '时间 (HH:MM:SS)' },
  { name: '{gamedate}', description: '游戏日 (YYYY-MM-DD，东4区，与历史记录归档一致)' },
]
