/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndPlanConfig_Input } from './MaaEndPlanConfig_Input';
import type { MaaPlanConfig } from './MaaPlanConfig';
export type PlanUpdateIn = {
    /**
     * 计划ID
     */
    planId: string;
    /**
     * 计划更新数据
     */
    data: (MaaPlanConfig | MaaEndPlanConfig_Input);
};

