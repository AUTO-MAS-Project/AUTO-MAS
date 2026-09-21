/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSUserConfig_Data } from './MSSUserConfig_Data';
import type { MSSUserConfig_Info } from './MSSUserConfig_Info';
import type { MSSUserConfig_Notify } from './MSSUserConfig_Notify';
import type { MSSUserConfig_Task } from './MSSUserConfig_Task';
export type MSSUserConfig = {
    /**
     * 基础信息
     */
    Info?: (MSSUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (MSSUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (MSSUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (MSSUserConfig_Notify | null);
};

