/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Webhook_DataInput = {
    /**
     * 请求头
     */
    Headers?: (string | null);
    /**
     * 请求方法
     */
    Method?: ('POST' | 'GET' | null);
    /**
     * 消息模板
     */
    Template?: (string | null);
    /**
     * Webhook URL 地址
     */
    Url?: (string | null);
};

