/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWUserConfig_Data } from './MaaFWUserConfig_Data';
import type { MaaFWUserConfig_Device } from './MaaFWUserConfig_Device';
import type { MaaFWUserConfig_Info } from './MaaFWUserConfig_Info';
import type { MaaFWUserConfig_Notify } from './MaaFWUserConfig_Notify';
import type { MaaFWUserConfig_Task } from './MaaFWUserConfig_Task';
export type MaaFWUserConfig = {
    /**
     * 基础信息
     */
    Info?: (MaaFWUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (MaaFWUserConfig_Task | null);
    /**
     * 设备覆盖配置
     */
    Device?: (MaaFWUserConfig_Device | null);
    /**
     * 用户数据
     */
    Data?: (MaaFWUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (MaaFWUserConfig_Notify | null);
};

