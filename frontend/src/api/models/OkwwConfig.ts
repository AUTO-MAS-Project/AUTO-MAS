/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralConfig_Info } from './GeneralConfig_Info';
import type { GeneralConfig_Run } from './GeneralConfig_Run';
import type { OkwwConfig_Game } from './OkwwConfig_Game';
export type OkwwConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (GeneralConfig_Info | null);
    /**
     * 游戏配置
     */
    Game?: (OkwwConfig_Game | null);
    /**
     * 运行配置
     */
    Run?: (GeneralConfig_Run | null);
};

