/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSPlanConfig_Info } from './MSSPlanConfig_Info';
import type { MSSPlanConfig_Item } from './MSSPlanConfig_Item';
export type MSSPlanConfig_Input = {
    /**
     * 基础信息
     */
    Info?: (MSSPlanConfig_Info | null);
    /**
     * 全局
     */
    ALL?: (MSSPlanConfig_Item | null);
    /**
     * 每天的槽位：周计划用 Monday~Sunday 做键，多天轮换用 "1"~"N" 做键
     */
    Days?: Record<string, MSSPlanConfig_Item>;
};

