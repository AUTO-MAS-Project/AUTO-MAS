/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type app__models__config__setting__Webhook__Data = {
    /**
     * Webhook URL
     */
    url?: string;
    /**
     * 消息模板
     */
    template?: string;
    /**
     * 自定义请求头
     */
    headers?: string;
    /**
     * 请求方法
     */
    method?: app__models__config__setting__Webhook__Data.method;
};
export namespace app__models__config__setting__Webhook__Data {
    /**
     * 请求方法
     */
    export enum method {
        POST = 'POST',
        GET = 'GET',
    }
}

