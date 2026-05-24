/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkwwUserConfig_Data } from './OkwwUserConfig_Data';
import type { OkwwUserConfig_Info } from './OkwwUserConfig_Info';
import type { OkwwUserConfig_Notify } from './OkwwUserConfig_Notify';
import type { OkwwUserConfig_Task } from './OkwwUserConfig_Task';
export type OkwwUserConfig = {
    /**
     * 用户信息
     */
    Info?: (OkwwUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (OkwwUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (OkwwUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (OkwwUserConfig_Notify | null);
};

