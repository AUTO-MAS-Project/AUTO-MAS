/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkefConfig_Game } from './OkefConfig_Game';
import type { OkefConfig_Info } from './OkefConfig_Info';
import type { OkefConfig_Run } from './OkefConfig_Run';
import type { OkefConfig_Script } from './OkefConfig_Script';
export type OkefConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (OkefConfig_Info | null);
    /**
     * 脚本配置
     */
    Script?: (OkefConfig_Script | null);
    /**
     * 游戏配置
     */
    Game?: (OkefConfig_Game | null);
    /**
     * 运行配置
     */
    Run?: (OkefConfig_Run | null);
};

