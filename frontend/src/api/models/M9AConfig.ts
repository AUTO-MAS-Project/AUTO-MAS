/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWConfig_Device } from './MaaFWConfig_Device';
import type { MaaFWConfig_Embedded } from './MaaFWConfig_Embedded';
import type { MaaFWConfig_Emulator } from './MaaFWConfig_Emulator';
import type { MaaFWConfig_Game } from './MaaFWConfig_Game';
import type { MaaFWConfig_Info } from './MaaFWConfig_Info';
import type { MaaFWConfig_Run } from './MaaFWConfig_Run';
import type { MaaFWConfig_Selection } from './MaaFWConfig_Selection';
import type { MaaFWConfig_Update } from './MaaFWConfig_Update';
/**
 * M9A 脚本配置：与 MaaFW 脚本配置同形（M9A 是 MaaFW 的特调类型）。
 */
export type M9AConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (MaaFWConfig_Info | null);
    /**
     * 模拟器配置
     */
    Emulator?: (MaaFWConfig_Emulator | null);
    /**
     * 设备配置
     */
    Device?: (MaaFWConfig_Device | null);
    /**
     * 游戏生命周期配置
     */
    Game?: (MaaFWConfig_Game | null);
    /**
     * 项目更新配置
     */
    Update?: (MaaFWConfig_Update | null);
    /**
     * 内嵌副本
     */
    Embedded?: (MaaFWConfig_Embedded | null);
    /**
     * 脚本运行配置
     */
    Run?: (MaaFWConfig_Run | null);
    /**
     * controller、resource 与 task 选择
     */
    Selection?: (MaaFWConfig_Selection | null);
};

