/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkwwConfig_Game } from './OkwwConfig_Game';
import type { OkwwConfig_Info } from './OkwwConfig_Info';
import type { OkwwConfig_Run } from './OkwwConfig_Run';
import type { OkwwConfig_Script } from './OkwwConfig_Script';
export type OkwwConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (OkwwConfig_Info | null);
    /**
     * 脚本配置
     */
    Script?: (OkwwConfig_Script | null);
    /**
     * 游戏配置
     */
    Game?: (OkwwConfig_Game | null);
    /**
     * 运行配置
     */
    Run?: (OkwwConfig_Run | null);
};

