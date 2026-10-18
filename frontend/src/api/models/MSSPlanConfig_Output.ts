/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSPlanConfig_Info } from './MSSPlanConfig_Info';
import type { MSSPlanConfig_Item } from './MSSPlanConfig_Item';
export type MSSPlanConfig_Output = {
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
    /**
     * 周一（兼容旧接口）
     */
    Monday?: (MSSPlanConfig_Item | null);
    /**
     * 周二（兼容旧接口）
     */
    Tuesday?: (MSSPlanConfig_Item | null);
    /**
     * 周三（兼容旧接口）
     */
    Wednesday?: (MSSPlanConfig_Item | null);
    /**
     * 周四（兼容旧接口）
     */
    Thursday?: (MSSPlanConfig_Item | null);
    /**
     * 周五（兼容旧接口）
     */
    Friday?: (MSSPlanConfig_Item | null);
    /**
     * 周六（兼容旧接口）
     */
    Saturday?: (MSSPlanConfig_Item | null);
    /**
     * 周日（兼容旧接口）
     */
    Sunday?: (MSSPlanConfig_Item | null);
};

