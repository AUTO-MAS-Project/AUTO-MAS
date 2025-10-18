/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Webhook } from './Webhook';
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
     * 新创建的Webhook ID
     */
    webhookId: string;
    /**
     * Webhook配置数据
     */
    data: Webhook;
};

