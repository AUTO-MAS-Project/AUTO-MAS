/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdConfig_Game } from './ZzzOdConfig_Game';
import type { ZzzOdConfig_Info } from './ZzzOdConfig_Info';
import type { ZzzOdConfig_Run } from './ZzzOdConfig_Run';
export type ZzzOdConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (ZzzOdConfig_Info | null);
    /**
     * 游戏配置
     */
    Game?: (ZzzOdConfig_Game | null);
    /**
     * 运行配置
     */
    Run?: (ZzzOdConfig_Run | null);
};

