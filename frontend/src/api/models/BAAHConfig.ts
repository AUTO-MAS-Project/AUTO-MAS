/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHConfig_Emulator } from './BAAHConfig_Emulator';
import type { BAAHConfig_Info } from './BAAHConfig_Info';
import type { BAAHConfig_Run } from './BAAHConfig_Run';
import type { BAAHConfig_Script } from './BAAHConfig_Script';
export type BAAHConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (BAAHConfig_Info | null);
    /**
     * 脚本配置
     */
    Script?: (BAAHConfig_Script | null);
    /**
     * 运行配置
     */
    Run?: (BAAHConfig_Run | null);
    /**
     * 模拟器配置
     */
    Emulator?: (BAAHConfig_Emulator | null);
};

