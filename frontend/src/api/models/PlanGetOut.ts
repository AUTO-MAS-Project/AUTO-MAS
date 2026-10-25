/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PlanConfigData } from './PlanConfigData';
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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 计划索引列表
     */
    index: Array<PlanIndexItem>;
    /**
     * 计划列表或单个计划数据
     */
    data: Record<string, PlanConfigData>;
};

