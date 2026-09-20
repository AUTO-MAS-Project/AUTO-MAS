// 自定义Webhook配置
export interface CustomWebhook {
  id: string
  name: string
  url: string
  template: string
  enabled: boolean
  headers?: Record<string, string>
  method?: 'POST' | 'GET'
}
