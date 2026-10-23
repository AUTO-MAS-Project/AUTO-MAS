import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type WebhookTestIn } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { translate as t } from '@/i18n'

interface WebhookTestItem {
  uid: string
  name: string
}

/** 测试请求与加载状态由同一流程管理，业务载荷不进入统计。 */
export function useWebhookTest<T extends WebhookTestItem>(
  buildRequest: (item: T) => WebhookTestIn,
  getScope: () => 'global' | 'script'
) {
  const testingWebhooks = ref<Record<string, boolean>>({})
  const logger = window.electronAPI.getLogger('Webhook测试')
  const testWebhook = async (item: T) => {
    const operation = beginAnalyticsOperation('webhook_test_finished')
    const scope_kind = getScope()
    testingWebhooks.value[item.uid] = true
    try {
      const response = await Service.testWebhookApiSettingWebhookTestPost(buildRequest(item))
      operation.finish({ scope_kind, outcome: response.code === 200 ? 'success' : 'failure' })
      if (response.code === 200) {
        message.success(t('comp.webhookP0TestedSuccessfully', { p0: item.name }))
      } else {
        message.error(t('comp.webhookTestFailedP0', { p0: response.message || '未知错误' }))
      }
    } catch (error: any) {
      operation.finish({ scope_kind, outcome: 'unknown' })
      const errorMsg =
        error.response?.data?.message || (error instanceof Error ? error.message : '网络错误')
      logger.error(`Webhook测试错误: ${errorMsg}`)
      message.error(t('comp.webhookTestFailedP0', { p0: errorMsg }))
    } finally {
      testingWebhooks.value[item.uid] = false
    }
  }
  return { testingWebhooks, testWebhook }
}
