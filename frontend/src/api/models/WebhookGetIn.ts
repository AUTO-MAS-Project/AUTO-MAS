/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebhookGetIn = {
    /**
     * 所属脚本ID, 获取全局设置的Webhook数据时无需携带
     */
    scriptId?: (string | null);
    /**
     * 所属用户ID, 获取全局设置的Webhook数据时无需携带
     */
    userId?: (string | null);
    /**
     * Webhook ID, 未携带时表示获取所有Webhook数据
     */
    webhookId?: (string | null);
};

