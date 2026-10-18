/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_Notify } from './GeneralUserConfig_Notify';
import type { WhimboxUserConfig_Data } from './WhimboxUserConfig_Data';
import type { WhimboxUserConfig_Info } from './WhimboxUserConfig_Info';
import type { WhimboxUserConfig_OneDragon } from './WhimboxUserConfig_OneDragon';
import type { WhimboxUserConfig_Task } from './WhimboxUserConfig_Task';
/**
 * 奇想盒用户配置（一条龙配置档）
 */
export type WhimboxUserConfig = {
    /**
     * 用户信息
     */
    Info?: (WhimboxUserConfig_Info | null);
    /**
     * 一条龙流程配置
     */
    OneDragon?: (WhimboxUserConfig_OneDragon | null);
    /**
     * 任务覆盖集
     */
    Task?: (WhimboxUserConfig_Task | null);
    /**
     * 用户数据
     */
    Data?: (WhimboxUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (GeneralUserConfig_Notify | null);
};

