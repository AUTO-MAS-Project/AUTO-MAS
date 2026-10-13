/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShareAppearanceMineItem } from './ShareAppearanceMineItem';
export type ShareAppearanceMineOut = {
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
     * 当前账号在分享站上的全部外观
     */
    data?: Array<ShareAppearanceMineItem>;
};

