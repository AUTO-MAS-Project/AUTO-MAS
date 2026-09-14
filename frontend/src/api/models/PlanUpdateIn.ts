/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndPlanConfig } from './MaaEndPlanConfig';
import type { MaaPlanConfig } from './MaaPlanConfig';
export type PlanUpdateIn = {
    /**
     * 计划ID
     */
    planId: string;
    /**
     * 计划更新数据
     */
    data: (MaaPlanConfig | MaaEndPlanConfig);
};

