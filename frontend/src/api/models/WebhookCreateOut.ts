/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Webhook_Output } from './Webhook_Output';
export type WebhookCreateOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 新 Webhook ID
     */
    webhookId?: string;
    /**
     * Webhook 配置
     */
    data?: Webhook_Output;
};

