import {
  createUserWebhookApiScriptsScriptIdUsersUserIdWebhooksPost,
  createWebhookApiSettingWebhooksPost,
  deleteUserWebhookApiScriptsScriptIdUsersUserIdWebhooksWebhookIdDelete,
  deleteWebhookApiSettingWebhooksWebhookIdDelete,
  getSettingApiSettingGet,
  getUserWebhookApiScriptsScriptIdUsersUserIdWebhooksWebhookIdGet,
  getWebhookApiSettingWebhooksWebhookIdGet,
  listUserWebhooksApiScriptsScriptIdUsersUserIdWebhooksGet,
  listWebhooksApiSettingWebhooksGet,
  reorderUserWebhooksApiScriptsScriptIdUsersUserIdWebhooksOrderPatch,
  reorderWebhooksApiSettingWebhooksOrderPatch,
  testNotifyApiSettingActionsTestNotifyPost,
  testWebhookApiSettingWebhooksTestPost,
  updateSettingApiSettingPatch,
  updateUserWebhookApiScriptsScriptIdUsersUserIdWebhooksWebhookIdPatch,
  updateWebhookApiSettingWebhooksWebhookIdPatch,
} from '../generated/sdk.gen'
import type { GlobalConfigRead, IndexOrderPatch, WebhookRead } from '../generated/types.gen'

export const settingApi = {
  get() {
    return getSettingApiSettingGet()
  },

  update(payload: GlobalConfigRead) {
    return updateSettingApiSettingPatch({ body: payload })
  },

  testNotify() {
    return testNotifyApiSettingActionsTestNotifyPost()
  },
}

export const webhookApi = {
  listGlobal() {
    return listWebhooksApiSettingWebhooksGet()
  },

  createGlobal() {
    return createWebhookApiSettingWebhooksPost()
  },

  getGlobal(webhookId: string) {
    return getWebhookApiSettingWebhooksWebhookIdGet({
      path: { webhook_id: webhookId },
    })
  },

  updateGlobal(webhookId: string, payload: WebhookRead) {
    return updateWebhookApiSettingWebhooksWebhookIdPatch({
      path: { webhook_id: webhookId },
      body: payload,
    })
  },

  removeGlobal(webhookId: string) {
    return deleteWebhookApiSettingWebhooksWebhookIdDelete({
      path: { webhook_id: webhookId },
    })
  },

  reorderGlobal(payload: IndexOrderPatch) {
    return reorderWebhooksApiSettingWebhooksOrderPatch({ body: payload })
  },

  testGlobal(payload: WebhookRead) {
    return testWebhookApiSettingWebhooksTestPost({ body: payload })
  },

  listUser(scriptId: string, userId: string) {
    return listUserWebhooksApiScriptsScriptIdUsersUserIdWebhooksGet({
      path: { script_id: scriptId, user_id: userId },
    })
  },

  createUser(scriptId: string, userId: string) {
    return createUserWebhookApiScriptsScriptIdUsersUserIdWebhooksPost({
      path: { script_id: scriptId, user_id: userId },
    })
  },

  getUser(scriptId: string, userId: string, webhookId: string) {
    return getUserWebhookApiScriptsScriptIdUsersUserIdWebhooksWebhookIdGet({
      path: { script_id: scriptId, user_id: userId, webhook_id: webhookId },
    })
  },

  updateUser(scriptId: string, userId: string, webhookId: string, payload: WebhookRead) {
    return updateUserWebhookApiScriptsScriptIdUsersUserIdWebhooksWebhookIdPatch({
      path: { script_id: scriptId, user_id: userId, webhook_id: webhookId },
      body: payload,
    })
  },

  removeUser(scriptId: string, userId: string, webhookId: string) {
    return deleteUserWebhookApiScriptsScriptIdUsersUserIdWebhooksWebhookIdDelete({
      path: { script_id: scriptId, user_id: userId, webhook_id: webhookId },
    })
  },

  reorderUser(scriptId: string, userId: string, payload: IndexOrderPatch) {
    return reorderUserWebhooksApiScriptsScriptIdUsersUserIdWebhooksOrderPatch({
      path: { script_id: scriptId, user_id: userId },
      body: payload,
    })
  },
}
