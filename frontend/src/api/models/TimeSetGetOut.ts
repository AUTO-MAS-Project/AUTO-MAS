/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CollectionOrderItem } from './CollectionOrderItem';
import type { TimeSetEntry_Output } from './TimeSetEntry_Output';
export type TimeSetGetOut = {
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
     * 定时项顺序
     */
    order?: Array<CollectionOrderItem>;
    /**
     * 定时项数据，key 为 uid
     */
    data?: Record<string, TimeSetEntry_Output>;
};

