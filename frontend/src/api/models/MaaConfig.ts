/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaConfig_Emulator } from './MaaConfig_Emulator';
import type { MaaConfig_Info } from './MaaConfig_Info';
import type { MaaConfig_Run } from './MaaConfig_Run';
import type { MaaConfig_Update } from './MaaConfig_Update';
export type MaaConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (MaaConfig_Info | null);
    /**
     * 模拟器配置
     */
    Emulator?: (MaaConfig_Emulator | null);
    /**
     * 脚本运行配置
     */
    Run?: (MaaConfig_Run | null);
    /**
     * 更新接管配置
     */
    Update?: (MaaConfig_Update | null);
};

