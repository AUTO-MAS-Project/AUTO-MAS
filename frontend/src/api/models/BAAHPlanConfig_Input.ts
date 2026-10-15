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
     * 周一
     */
    Monday?: (BAAHPlanConfig_Item | null);
    /**
     * 周二
     */
    Tuesday?: (BAAHPlanConfig_Item | null);
    /**
     * 周三
     */
    Wednesday?: (BAAHPlanConfig_Item | null);
    /**
     * 周四
     */
    Thursday?: (BAAHPlanConfig_Item | null);
    /**
     * 周五
     */
    Friday?: (BAAHPlanConfig_Item | null);
    /**
     * 周六
     */
    Saturday?: (BAAHPlanConfig_Item | null);
    /**
     * 周日
     */
    Sunday?: (BAAHPlanConfig_Item | null);
};

