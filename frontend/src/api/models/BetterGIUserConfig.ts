/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIUserConfig_Data } from './BetterGIUserConfig_Data';
import type { BetterGIUserConfig_Info } from './BetterGIUserConfig_Info';
import type { BetterGIUserConfig_Notify } from './BetterGIUserConfig_Notify';
import type { BetterGIUserConfig_OneDragon } from './BetterGIUserConfig_OneDragon';
import type { BetterGIUserConfig_Switch } from './BetterGIUserConfig_Switch';
import type { BetterGIUserConfig_Task } from './BetterGIUserConfig_Task';
export type BetterGIUserConfig = {
    /**
     * 用户信息
     */
    Info?: (BetterGIUserConfig_Info | null);
    /**
     * 任务配置
     */
    Task?: (BetterGIUserConfig_Task | null);
    /**
     * 切换账号配置
     */
    Switch?: (BetterGIUserConfig_Switch | null);
    /**
     * 一条龙配置
     */
    OneDragon?: (BetterGIUserConfig_OneDragon | null);
    /**
     * 用户数据
     */
    Data?: (BetterGIUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (BetterGIUserConfig_Notify | null);
};

