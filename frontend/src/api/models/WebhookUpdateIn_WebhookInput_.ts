/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WebhookInput } from './WebhookInput';
export type WebhookUpdateIn_WebhookInput_ = {
    /**
     * 所属脚本ID, 获取全局设置的Webhook数据时无需携带
     */
    scriptId?: (string | null);
    /**
     * 所属用户ID, 获取全局设置的Webhook数据时无需携带
     */
    userId?: (string | null);
    /**
     * Webhook ID
     */
    webhookId: string;
    /**
     * Webhook更新数据
     */
    data: WebhookInput;
};

