/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRConfig_Game } from './HSRConfig_Game';
import type { HSRConfig_Info } from './HSRConfig_Info';
import type { HSRConfig_Run } from './HSRConfig_Run';
import type { HSRConfig_TaskMapping } from './HSRConfig_TaskMapping';
export type HSRConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (HSRConfig_Info | null);
    /**
     * 游戏配置
     */
    Game?: (HSRConfig_Game | null);
    /**
     * 运行配置
     */
    Run?: (HSRConfig_Run | null);
    /**
     * 模块脚本分配
     */
    TaskMapping?: (HSRConfig_TaskMapping | null);
};

