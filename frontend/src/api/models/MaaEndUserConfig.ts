/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndUserConfig_Data } from './MaaEndUserConfig_Data';
import type { MaaEndUserConfig_Info } from './MaaEndUserConfig_Info';
import type { MaaEndUserConfig_Task } from './MaaEndUserConfig_Task';
export type MaaEndUserConfig = {
    /**
     * 用户信息
     */
    Info?: (MaaEndUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (MaaEndUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (MaaEndUserConfig_Data | null);
};
