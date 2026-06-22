/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRDynamicStageM7A } from './HSRDynamicStageM7A';
import type { HSRDynamicStageSRA } from './HSRDynamicStageSRA';
export type HSRDynamicStageOption = {
    /**
     * 副本展示名称
     */
    label: string;
    /**
     * 副本说明
     */
    detail?: (string | null);
    /**
     * 副本选项值
     */
    value: string;
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
     * M7A 原生字段
     */
    m7a?: (HSRDynamicStageM7A | null);
    /**
     * SRA 原生字段
     */
    sra?: (HSRDynamicStageSRA | null);
};
