/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaPlanConfig_Info } from './MaaPlanConfig_Info';
import type { MaaPlanConfig_Item } from './MaaPlanConfig_Item';
export type MaaPlanConfig = {
    /**
     * 基础信息
     */
    Info?: (MaaPlanConfig_Info | null);
    /**
     * 全局
     */
    ALL?: (MaaPlanConfig_Item | null);
    /**
     * 每天的槽位：周计划用 Monday~Sunday 做键，多天轮换用 "1"~"N" 做键
     */
    Days?: Record<string, MaaPlanConfig_Item>;
    /**
     * 周一（兼容旧接口）
     */
    Monday?: (MaaPlanConfig_Item | null);
    /**
     * 周二（兼容旧接口）
     */
    Tuesday?: (MaaPlanConfig_Item | null);
    /**
     * 周三（兼容旧接口）
     */
    Wednesday?: (MaaPlanConfig_Item | null);
    /**
     * 周四（兼容旧接口）
     */
    Thursday?: (MaaPlanConfig_Item | null);
    /**
     * 周五（兼容旧接口）
     */
    Friday?: (MaaPlanConfig_Item | null);
    /**
     * 周六（兼容旧接口）
     */
    Saturday?: (MaaPlanConfig_Item | null);
    /**
     * 周日（兼容旧接口）
     */
    Sunday?: (MaaPlanConfig_Item | null);
};

