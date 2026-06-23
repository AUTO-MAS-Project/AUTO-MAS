/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRDynamicStageOption } from './HSRDynamicStageOption';
export type HSRDynamicStageCategory = {
    /**
     * 副本分类键
     */
    categoryKey: string;
    /**
     * 副本分类名称
     */
    categoryLabel: string;
    /**
     * 单次体力消耗
     */
    cost?: (number | null);
    /**
     * 最大执行次数
     */
    maxCount?: (number | null);
    /**
     * 副本选项列表
     */
    options?: Array<HSRDynamicStageOption>;
};
