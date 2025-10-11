/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimeSet } from './TimeSet';
import type { TimeSetIndexItem } from './TimeSetIndexItem';
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
     * 时间设置索引列表
     */
    index: Array<TimeSetIndexItem>;
    /**
     * 时间设置数据字典, key来自于index列表的uid
     */
    data: Record<string, TimeSet>;
};

