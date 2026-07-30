/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRUserConfig_Abyss } from './HSRUserConfig_Abyss';
import type { HSRUserConfig_Data } from './HSRUserConfig_Data';
import type { HSRUserConfig_Info } from './HSRUserConfig_Info';
import type { HSRUserConfig_Notify } from './HSRUserConfig_Notify';
import type { HSRUserConfig_Stage } from './HSRUserConfig_Stage';
import type { HSRUserConfig_TaskOpt } from './HSRUserConfig_TaskOpt';
import type { HSRUserConfig_TaskSwitch } from './HSRUserConfig_TaskSwitch';
export type HSRUserConfig = {
    /**
     * 基础信息
     */
    Info?: (HSRUserConfig_Info | null);
    /**
     * 用户数据
     */
    Data?: (HSRUserConfig_Data | null);
    /**
     * 模块执行开关
     */
    TaskSwitch?: (HSRUserConfig_TaskSwitch | null);
    /**
     * 关卡配置
     */
    Stage?: (HSRUserConfig_Stage | null);
    /**
     * 模块执行参数
     */
    TaskOpt?: (HSRUserConfig_TaskOpt | null);
    /**
     * 单独通知
     */
    Notify?: (HSRUserConfig_Notify | null);
    /**
     * 三深渊配置
     */
    Abyss?: (HSRUserConfig_Abyss | null);
};

