/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkefUserConfig_Data } from './OkefUserConfig_Data';
import type { OkefUserConfig_Info } from './OkefUserConfig_Info';
import type { OkefUserConfig_Notify } from './OkefUserConfig_Notify';
import type { OkefUserConfig_Task } from './OkefUserConfig_Task';
export type OkefUserConfig = {
    /**
     * 用户信息
     */
    Info?: (OkefUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (OkefUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (OkefUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (OkefUserConfig_Notify | null);
};

