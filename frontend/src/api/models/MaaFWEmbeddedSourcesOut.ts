/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWEmbeddedSourceItem } from './MaaFWEmbeddedSourceItem';
export type MaaFWEmbeddedSourcesOut = {
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
     * 有健康副本的其它 MFW 脚本
     */
    data?: Array<MaaFWEmbeddedSourceItem>;
};

