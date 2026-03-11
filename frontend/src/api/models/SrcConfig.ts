/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SrcConfig_Emulator } from './SrcConfig_Emulator';
import type { SrcConfig_Info } from './SrcConfig_Info';
import type { SrcConfig_Run } from './SrcConfig_Run';
export type SrcConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (SrcConfig_Info | null);
    /**
     * 模拟器配置
     */
    Emulator?: (SrcConfig_Emulator | null);
    /**
     * 脚本运行配置
     */
    Run?: (SrcConfig_Run | null);
};

