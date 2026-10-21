/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndPlanConfig_Info } from './MaaEndPlanConfig_Info';
import type { MaaEndPlanConfig_Item } from './MaaEndPlanConfig_Item';
export type MaaEndPlanConfig_Input = {
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
    /**
     * 周一（兼容旧接口）
     */
    Monday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周二（兼容旧接口）
     */
    Tuesday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周三（兼容旧接口）
     */
    Wednesday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周四（兼容旧接口）
     */
    Thursday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周五（兼容旧接口）
     */
    Friday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周六（兼容旧接口）
     */
    Saturday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周日（兼容旧接口）
     */
    Sunday?: (MaaEndPlanConfig_Item | null);
};

