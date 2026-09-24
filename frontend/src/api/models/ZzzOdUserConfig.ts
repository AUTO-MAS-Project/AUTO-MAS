/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdUserConfig_Data } from './ZzzOdUserConfig_Data';
import type { ZzzOdUserConfig_Game } from './ZzzOdUserConfig_Game';
import type { ZzzOdUserConfig_Info } from './ZzzOdUserConfig_Info';
import type { ZzzOdUserConfig_Notify } from './ZzzOdUserConfig_Notify';
import type { ZzzOdUserConfig_OneDragon } from './ZzzOdUserConfig_OneDragon';
export type ZzzOdUserConfig = {
    /**
     * 用户信息
     */
    Info?: (ZzzOdUserConfig_Info | null);
    /**
     * 游戏账号配置
     */
    Game?: (ZzzOdUserConfig_Game | null);
    /**
     * 一条龙任务编排
     */
    OneDragon?: (ZzzOdUserConfig_OneDragon | null);
    /**
     * 用户数据
     */
    Data?: (ZzzOdUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (ZzzOdUserConfig_Notify | null);
};

