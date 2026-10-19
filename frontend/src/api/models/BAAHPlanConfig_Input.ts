/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHPlanConfig_Info } from './BAAHPlanConfig_Info';
import type { BAAHPlanConfig_Item } from './BAAHPlanConfig_Item';
export type BAAHPlanConfig_Input = {
    /**
     * 基础信息
     */
    Info?: (BAAHPlanConfig_Info | null);
    /**
     * 全局
     */
    ALL?: (BAAHPlanConfig_Item | null);
    /**
     * 每天的槽位：周计划用 Monday~Sunday 做键，多天轮换用 "1"~"N" 做键
     */
    Days?: Record<string, BAAHPlanConfig_Item>;
    /**
     * 周一（兼容旧接口）
     */
    Monday?: (BAAHPlanConfig_Item | null);
    /**
     * 周二（兼容旧接口）
     */
    Tuesday?: (BAAHPlanConfig_Item | null);
    /**
     * 周三（兼容旧接口）
     */
    Wednesday?: (BAAHPlanConfig_Item | null);
    /**
     * 周四（兼容旧接口）
     */
    Thursday?: (BAAHPlanConfig_Item | null);
    /**
     * 周五（兼容旧接口）
     */
    Friday?: (BAAHPlanConfig_Item | null);
    /**
     * 周六（兼容旧接口）
     */
    Saturday?: (BAAHPlanConfig_Item | null);
    /**
     * 周日（兼容旧接口）
     */
    Sunday?: (BAAHPlanConfig_Item | null);
};

