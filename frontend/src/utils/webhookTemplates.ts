// Webhook 模板配置
export interface WebhookTemplate {
  name: string
  description: string
  template: string
  headers?: Record<string, string>
  method: 'POST' | 'GET'
  example?: string
}

export const WEBHOOK_TEMPLATES: WebhookTemplate[] = [
  {
    name: 'Bark (iOS推送)',
    description: 'Bark是一款iOS推送通知应用',
    template: '{"title": "{title}", "body": "{content}", "sound": "default"}',
    method: 'POST',
    example: 'https://api.day.app/your_key/',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: 'Server酱 (微信推送)',
    description: 'Server酱微信推送服务',
    template: '{"title": "{title}", "desp": "{content}"}',
    method: 'POST',
    example: 'https://sctapi.ftqq.com/your_key.send',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: '企业微信机器人',
    description: '企业微信群机器人推送',
    template: '{"msgtype": "text", "text": {"content": "{title}\\n{content}"}}',
    method: 'POST',
    example: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: 'DingTalk (钉钉机器人)',
    description: '钉钉群机器人推送',
    template: '{"msgtype": "text", "text": {"content": "{title}\\n{content}"}}',
    method: 'POST',
    example: 'https://oapi.dingtalk.com/robot/send?access_token=your_token',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: 'Telegram Bot',
    description: 'Telegram机器人推送',
    template: '{"chat_id": "your_chat_id", "text": "{title}\\n{content}"}',
    method: 'POST',
    example: 'https://api.telegram.org/bot{your_bot_token}/sendMessage',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: 'Discord Webhook',
    description: 'Discord频道Webhook推送',
    template: '{"content": "**{title}**\\n{content}"}',
    method: 'POST',
    example: 'https://discord.com/api/webhooks/your_webhook_url',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: 'Slack Webhook',
    description: 'Slack频道Webhook推送',
    template: '{"text": "{title}\\n{content}"}',
    method: 'POST',
    example: 'https://hooks.slack.com/services/your/webhook/url',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: 'PushPlus (微信推送)',
    description: 'PushPlus微信推送服务',
    template: '{"token": "your_token", "title": "{title}", "content": "{content}"}',
    method: 'POST',
    example: 'http://www.pushplus.plus/send',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: '自定义JSON',
    description: '自定义JSON格式推送',
    template: '{"message": "{title}: {content}", "timestamp": "{datetime}"}',
    method: 'POST',
    example: 'https://your-api.com/webhook',
    headers: {
      'Content-Type': 'application/json'
    }
  },
  {
    name: '自定义GET请求',
    description: '通过GET请求发送通知',
    template: 'title={title}&content={content}&time={datetime}',
    method: 'GET',
    example: 'https://your-api.com/notify',
    headers: {}
  }
]

// 获取模板变量说明
export const TEMPLATE_VARIABLES = [
  { name: '{title}', description: '通知标题' },
  { name: '{content}', description: '通知内容' },
  { name: '{datetime}', description: '完整日期时间 (YYYY-MM-DD HH:MM:SS)' },
  { name: '{date}', description: '日期 (YYYY-MM-DD)' },
  { name: '{time}', description: '时间 (HH:MM:SS)' }
]