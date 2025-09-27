/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaUserConfig_Data } from './MaaUserConfig_Data';
import type { MaaUserConfig_Info } from './MaaUserConfig_Info';
import type { MaaUserConfig_Task } from './MaaUserConfig_Task';
import type { UserConfig_Notify } from './UserConfig_Notify';
export type MaaUserConfig_Output = {
    /**
     * 基础信息
     */
    Info?: (MaaUserConfig_Info | null);
    /**
     * 用户数据
     */
    Data?: (MaaUserConfig_Data | null);
    /**
     * 任务列表
     */
    Task?: (MaaUserConfig_Task | null);
    /**
     * 单独通知
     */
    Notify?: (UserConfig_Notify | null);
};

