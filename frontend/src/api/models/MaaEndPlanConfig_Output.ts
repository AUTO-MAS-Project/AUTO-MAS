/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndPlanConfig_Info } from './MaaEndPlanConfig_Info';
import type { MaaEndPlanConfig_Item } from './MaaEndPlanConfig_Item';
export type MaaEndPlanConfig_Output = {
    /**
     * 基础信息
     */
    Info?: (MaaEndPlanConfig_Info | null);
    /**
     * 全局
     */
    ALL?: (MaaEndPlanConfig_Item | null);
    /**
     * 每天的槽位：周计划用 Monday~Sunday 做键，多天轮换用 "1"~"N" 做键
     */
    Days?: Record<string, MaaEndPlanConfig_Item>;
};

