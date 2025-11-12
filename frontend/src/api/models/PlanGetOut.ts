/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaPlanConfig } from './MaaPlanConfig';
import type { PlanIndexItem } from './PlanIndexItem';
export type PlanGetOut = {
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
     * 计划索引列表
     */
    index: Array<PlanIndexItem>;
    /**
     * 计划列表或单个计划数据
     */
    data: Record<string, MaaPlanConfig>;
};

