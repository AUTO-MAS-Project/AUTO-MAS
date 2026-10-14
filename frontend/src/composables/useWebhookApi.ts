import { Service, type WebhookUpdateIn, type WebhookTestIn } from '@/api'
import { translate as t } from '@/i18n'
import { requestApi } from '@/utils/apiResult'

export function useWebhookApi() {
  return {
    getWebhooks: () =>
      requestApi(
        () => Service.getWebhookApiSettingWebhookGetPost({ webhookId: null }),
        t('comp.couldNotLoadWebhook')
      ),
    addWebhook: () =>
      requestApi(() => Service.addWebhookApiSettingWebhookAddPost(), t('comp.couldNotSaveWebhook')),
    updateWebhook: (body: WebhookUpdateIn) =>
      requestApi(
        () => Service.updateWebhookApiSettingWebhookUpdatePost(body),
        t('comp.couldNotSaveWebhook')
      ),
    deleteWebhook: (webhookId: string) =>
      requestApi(
        () => Service.deleteWebhookApiSettingWebhookDeletePost({ webhookId }),
        t('comp.couldNotSaveWebhook')
      ),
    testWebhook: (body: WebhookTestIn) =>
      requestApi(
        () => Service.testWebhookApiSettingWebhookTestPost(body),
        t('comp.webhookTestFailedP0')
      ),
  }
}
