/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSConfig_Emulator } from './MSSConfig_Emulator';
import type { MSSConfig_Game } from './MSSConfig_Game';
import type { MSSConfig_Info } from './MSSConfig_Info';
import type { MSSConfig_Run } from './MSSConfig_Run';
export type MSSConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (MSSConfig_Info | null);
    /**
     * 模拟器配置（模拟器端暂不适配）
     */
    Emulator?: (MSSConfig_Emulator | null);
    /**
     * 游戏配置
     */
    Game?: (MSSConfig_Game | null);
    /**
     * 脚本运行配置
     */
    Run?: (MSSConfig_Run | null);
};

