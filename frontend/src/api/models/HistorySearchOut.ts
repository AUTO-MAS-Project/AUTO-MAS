/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryData } from './HistoryData';
export type HistorySearchOut = {
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
     * 历史记录索引数据字典, 格式为 { '日期': { '用户名': [历史记录信息] } }
     */
    data: Record<string, Record<string, HistoryData>>;
};

