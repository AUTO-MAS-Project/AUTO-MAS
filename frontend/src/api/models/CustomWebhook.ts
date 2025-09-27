/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CustomWebhook = {
    /**
     * Webhook唯一标识
     */
    id: string;
    /**
     * Webhook名称
     */
    name: string;
    /**
     * Webhook URL
     */
    url: string;
    /**
     * 消息模板
     */
    template: string;
    /**
     * 是否启用
     */
    enabled?: boolean;
    /**
     * 自定义请求头
     */
    headers?: (Record<string, string> | null);
    /**
     * 请求方法
     */
    method?: ('POST' | 'GET' | null);
};

