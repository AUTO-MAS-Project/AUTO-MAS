/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWConfig_Device } from './MaaFWConfig_Device';
import type { MaaFWConfig_Emulator } from './MaaFWConfig_Emulator';
import type { MaaFWConfig_Game } from './MaaFWConfig_Game';
import type { MaaFWConfig_Info } from './MaaFWConfig_Info';
import type { MaaFWConfig_Run } from './MaaFWConfig_Run';
import type { MaaFWConfig_Update } from './MaaFWConfig_Update';
export type MaaFWConfig = {
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
     * 脚本运行配置
     */
    Run?: (MaaFWConfig_Run | null);
};

