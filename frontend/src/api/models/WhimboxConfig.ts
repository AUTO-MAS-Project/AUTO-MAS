/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralConfig_Info } from './GeneralConfig_Info';
import type { WhimboxConfig_Run } from './WhimboxConfig_Run';
/**
 * 奇想盒脚本配置（无限暖暖，BetterGI 线）
 */
export type WhimboxConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (GeneralConfig_Info | null);
    /**
     * 运行配置
     */
    Run?: (WhimboxConfig_Run | null);
};

