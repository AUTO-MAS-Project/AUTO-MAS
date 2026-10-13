/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CollectionOrderItem } from './CollectionOrderItem';
import type { Webhook_Output } from './Webhook_Output';
export type WebhookGetOut = {
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
     * Webhook 顺序
     */
    order?: Array<CollectionOrderItem>;
    /**
     * Webhook 数据，key 为 uid
     */
    data?: Record<string, Webhook_Output>;
};

