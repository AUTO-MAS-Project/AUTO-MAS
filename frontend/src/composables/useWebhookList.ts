import { message } from 'ant-design-vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Service } from '@/api/services/Service'
import { useConfigLoader } from '@/services/configUiSync'

export interface WebhookItem {
  uid: string
  name: string
  url: string
  template: string
  method: 'POST' | 'GET'
  enabled: boolean
  headers?: Record<string, string>
}

interface WebhookListScope {
  mode?: 'global' | 'user'
  scriptId?: string | null
  userId?: string | null
}

export function useWebhookList(
  props: WebhookListScope,
  onListed: (webhooks: WebhookItem[]) => void
) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('Webhook管理器')
  const loading = ref(false)
  const apiWebhooks = ref<WebhookItem[]>([])
  // 加载Webhook数据
  const loadWebhooks = useConfigLoader(
    () => ['config', 'webhooks', props.mode, props.scriptId, props.userId],
    async read => {
      if (props.mode !== 'global' && !props.scriptId && !props.userId) {
        return // 本地模式不需要加载
      }

      loading.value = true
      try {
        let response

        if (props.mode === 'global') {
          // 全局模式：使用setting接口
          response = await Service.getWebhookApiSettingWebhookGetPost({
            scriptId: null,
            userId: null,
            webhookId: null,
          })
        } else {
          // 用户模式：使用scripts接口
          response = await Service.getWebhookApiScriptsWebhookGetPost({
            scriptId: props.scriptId || null,
            userId: props.userId || null,
            webhookId: null,
          })
        }

        read(response)
        if (response.code === 200) {
          // 转换API数据为内部格式
          apiWebhooks.value = response.index.map(item => {
            const webhookData = response.data[item.uid]
            return {
              uid: item.uid,
              name: webhookData.Info?.Name || '',
              url: webhookData.Data?.Url || '',
              template: webhookData.Data?.Template || '',
              method: (webhookData.Data?.Method || 'POST') as 'POST' | 'GET',
              enabled: webhookData.Info?.Enabled || false,
              headers: webhookData.Data?.Headers ? JSON.parse(webhookData.Data.Headers) : undefined,
            }
          })
          onListed(apiWebhooks.value)
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`加载Webhook失败: ${errorMsg}`)
        message.error(t('core.comp.couldNotLoadWebhook'))
      } finally {
        loading.value = false
      }
    }
  )

  return { loading, apiWebhooks, loadWebhooks }
}
