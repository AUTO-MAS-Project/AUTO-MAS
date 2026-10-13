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
     * 周一
     */
    Monday?: (MSSPlanConfig_Item | null);
    /**
     * 周二
     */
    Tuesday?: (MSSPlanConfig_Item | null);
    /**
     * 周三
     */
    Wednesday?: (MSSPlanConfig_Item | null);
    /**
     * 周四
     */
    Thursday?: (MSSPlanConfig_Item | null);
    /**
     * 周五
     */
    Friday?: (MSSPlanConfig_Item | null);
    /**
     * 周六
     */
    Saturday?: (MSSPlanConfig_Item | null);
    /**
     * 周日
     */
    Sunday?: (MSSPlanConfig_Item | null);
};

