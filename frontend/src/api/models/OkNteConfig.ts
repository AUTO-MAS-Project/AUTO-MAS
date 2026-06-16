/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkNteConfig_Game } from './OkNteConfig_Game';
import type { OkNteConfig_Info } from './OkNteConfig_Info';
import type { OkNteConfig_Run } from './OkNteConfig_Run';
import type { OkNteConfig_Script } from './OkNteConfig_Script';
export type OkNteConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (OkNteConfig_Info | null);
    /**
     * 脚本配置
     */
    Script?: (OkNteConfig_Script | null);
    /**
     * 游戏配置
     */
    Game?: (OkNteConfig_Game | null);
    /**
     * 运行配置
     */
    Run?: (OkNteConfig_Run | null);
};



