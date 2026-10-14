/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Webhook_Input } from './Webhook_Input';
export type WebhookUpdateIn = {
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
     * Webhook 补丁（文档形状）
     */
    data: Webhook_Input;
};

