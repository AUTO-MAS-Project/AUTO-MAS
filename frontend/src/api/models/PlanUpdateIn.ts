/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHPlanConfig_Input } from './BAAHPlanConfig_Input';
import type { MaaEndPlanConfig_Input } from './MaaEndPlanConfig_Input';
import type { MaaPlanConfig } from './MaaPlanConfig';
import type { MSSPlanConfig_Input } from './MSSPlanConfig_Input';
export type PlanUpdateIn = {
    /**
     * 计划ID
     */
    planId: string;
    /**
     * 计划更新数据
     */
    data: (MaaPlanConfig | MaaEndPlanConfig_Input | BAAHPlanConfig_Input | MSSPlanConfig_Input);
};

