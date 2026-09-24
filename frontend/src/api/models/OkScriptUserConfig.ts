/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkScriptUserConfig_Data } from './OkScriptUserConfig_Data';
import type { OkScriptUserConfig_Info } from './OkScriptUserConfig_Info';
import type { OkScriptUserConfig_Notify } from './OkScriptUserConfig_Notify';
import type { OkScriptUserConfig_Task } from './OkScriptUserConfig_Task';
export type OkScriptUserConfig = {
    /**
     * 用户信息
     */
    Info?: (OkScriptUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (OkScriptUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (OkScriptUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (OkScriptUserConfig_Notify | null);
};

