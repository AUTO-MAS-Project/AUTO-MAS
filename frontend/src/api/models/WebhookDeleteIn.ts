/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebhookDeleteIn = {
    /**
     * 所属托管ID, 获取全局设置的Webhook数据时无需携带
     */
    scriptId?: (string | null);
    /**
     * 所属账号ID, 获取全局设置的Webhook数据时无需携带
     */
    userId?: (string | null);
    /**
     * Webhook ID
     */
    webhookId: string;
};

