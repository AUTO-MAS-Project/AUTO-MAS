/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Webhook } from './Webhook';
import type { WebhookIndexItem } from './WebhookIndexItem';
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
     * Webhook索引列表
     */
    index: Array<WebhookIndexItem>;
    /**
     * Webhook数据字典, key来自于index列表的uid
     */
    data: Record<string, Webhook>;
};

