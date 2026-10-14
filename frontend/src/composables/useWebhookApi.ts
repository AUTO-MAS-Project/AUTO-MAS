import { Service, type WebhookUpdateIn, type WebhookTestIn, type WebhookInBase } from '@/api'
import { translate as t } from '@/i18n'
import { requestApi } from '@/utils/apiResult'

export function useWebhookApi() {
  return {
    getWebhooks: (scope: WebhookInBase = {}) =>
      requestApi(
        () => Service.getWebhookApiSettingWebhookGetPost({ webhookId: null, ...scope }),
        t('comp.couldNotLoadWebhook')
      ),
    addWebhook: (scope: WebhookInBase = {}) =>
      requestApi(
        () => Service.addWebhookApiSettingWebhookAddPost(scope),
        t('comp.couldNotSaveWebhook')
      ),
    updateWebhook: (body: WebhookUpdateIn) =>
      requestApi(
        () => Service.updateWebhookApiSettingWebhookUpdatePost(body),
        t('comp.couldNotSaveWebhook')
      ),
    deleteWebhook: (webhookId: string, scope: WebhookInBase = {}) =>
      requestApi(
        () => Service.deleteWebhookApiSettingWebhookDeletePost({ webhookId, ...scope }),
        t('comp.couldNotSaveWebhook')
      ),
    testWebhook: (body: WebhookTestIn) =>
      requestApi(
        () => Service.testWebhookApiSettingWebhookTestPost(body),
        t('comp.webhookTestFailedP0')
      ),
  }
}
