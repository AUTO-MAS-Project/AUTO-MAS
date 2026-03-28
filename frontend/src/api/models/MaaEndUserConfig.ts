/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndUserConfig_Info } from './MaaEndUserConfig_Info';
import type { MaaEndUserConfig_Notify } from './MaaEndUserConfig_Notify';
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
     * 通知配置
     */
    Notify?: (MaaEndUserConfig_Notify | null);
};

