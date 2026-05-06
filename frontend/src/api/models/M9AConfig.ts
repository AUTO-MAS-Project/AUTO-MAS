/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { M9AConfig_Emulator } from './M9AConfig_Emulator';
import type { M9AConfig_Info } from './M9AConfig_Info';
import type { M9AConfig_Run } from './M9AConfig_Run';
export type M9AConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (M9AConfig_Info | null);
    /**
     * 模拟器配置
     */
    Emulator?: (M9AConfig_Emulator | null);
    /**
     * 脚本运行配置
     */
    Run?: (M9AConfig_Run | null);
};

