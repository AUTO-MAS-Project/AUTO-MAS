/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndPlanConfig_Info } from './MaaEndPlanConfig_Info';
import type { MaaEndPlanConfig_Item } from './MaaEndPlanConfig_Item';
export type MaaEndPlanConfig = {
    /**
     * 基础信息
     */
    Info?: (MaaEndPlanConfig_Info | null);
    /**
     * 全局
     */
    ALL?: (MaaEndPlanConfig_Item | null);
    /**
     * 周一
     */
    Monday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周二
     */
    Tuesday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周三
     */
    Wednesday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周四
     */
    Thursday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周五
     */
    Friday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周六
     */
    Saturday?: (MaaEndPlanConfig_Item | null);
    /**
     * 周日
     */
    Sunday?: (MaaEndPlanConfig_Item | null);
};
