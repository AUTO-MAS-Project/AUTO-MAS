/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRConfig_Cloud } from './HSRConfig_Cloud';
import type { HSRConfig_Game } from './HSRConfig_Game';
import type { HSRConfig_Info } from './HSRConfig_Info';
import type { HSRConfig_Managed } from './HSRConfig_Managed';
import type { HSRConfig_Run } from './HSRConfig_Run';
import type { HSRConfig_Stage } from './HSRConfig_Stage';
import type { HSRConfig_TaskMapping } from './HSRConfig_TaskMapping';
import type { HSRConfig_TaskOpt } from './HSRConfig_TaskOpt';
import type { HSRConfig_TaskSwitch } from './HSRConfig_TaskSwitch';
import type { HSRConfig_Update } from './HSRConfig_Update';
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
     * 云·星穹铁道配置
     */
    Cloud?: (HSRConfig_Cloud | null);
    /**
     * 运行配置
     */
    Run?: (HSRConfig_Run | null);
    /**
     * 外部脚本更新配置
     */
    Update?: (HSRConfig_Update | null);
    /**
     * 模块脚本分配
     */
    TaskMapping?: (HSRConfig_TaskMapping | null);
    /**
     * 共享计划：模块执行开关（脚本来源用户共用）
     */
    TaskSwitch?: (HSRConfig_TaskSwitch | null);
    /**
     * 共享计划：关卡配置（脚本来源用户共用）
     */
    Stage?: (HSRConfig_Stage | null);
    /**
     * 共享计划：模块执行参数（脚本来源用户共用）
     */
    TaskOpt?: (HSRConfig_TaskOpt | null);
    /**
     * 共享计划：托管覆盖（脚本来源用户共用）
     */
    Managed?: (HSRConfig_Managed | null);
};

