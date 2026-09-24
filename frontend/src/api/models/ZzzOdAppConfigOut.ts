/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdAppConfigFieldOut } from './ZzzOdAppConfigFieldOut';
export type ZzzOdAppConfigOut = {
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
     * 应用ID
     */
    appId: string;
    /**
     * 配置字段列表
     */
    fields: Array<ZzzOdAppConfigFieldOut>;
};

