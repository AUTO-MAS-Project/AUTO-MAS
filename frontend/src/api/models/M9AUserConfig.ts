/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { M9AUserConfig_Data } from './M9AUserConfig_Data';
import type { M9AUserConfig_Info } from './M9AUserConfig_Info';
import type { M9AUserConfig_Notify } from './M9AUserConfig_Notify';
import type { M9AUserConfig_Task } from './M9AUserConfig_Task';
export type M9AUserConfig = {
    /**
     * 基础信息
     */
    Info?: (M9AUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (M9AUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (M9AUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (M9AUserConfig_Notify | null);
};

