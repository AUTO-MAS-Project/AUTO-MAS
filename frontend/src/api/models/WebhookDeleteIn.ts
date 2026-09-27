/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebhookDeleteIn = {
    /**
     * 所属脚本ID, 获取全局设置的Webhook数据时无需携带
     */
    scriptId?: (string | null);
    /**
     * 所属用户ID, 获取全局设置的Webhook数据时无需携带
     */
    userId?: (string | null);
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * Webhook ID
     */
    webhookId: string;
};

