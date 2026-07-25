/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkNteUserConfig_Data } from './OkNteUserConfig_Data';
import type { OkNteUserConfig_Info } from './OkNteUserConfig_Info';
import type { OkNteUserConfig_Notify } from './OkNteUserConfig_Notify';
import type { OkNteUserConfig_Task } from './OkNteUserConfig_Task';
export type OkNteUserConfig = {
    /**
     * 用户信息
     */
    Info?: (OkNteUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (OkNteUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (OkNteUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (OkNteUserConfig_Notify | null);
};

