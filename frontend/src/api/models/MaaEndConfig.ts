/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndConfig_Info } from './MaaEndConfig_Info';
import type { MaaEndConfig_MaaEnd } from './MaaEndConfig_MaaEnd';
import type { MaaEndConfig_Run } from './MaaEndConfig_Run';
export type MaaEndConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (MaaEndConfig_Info | null);
    /**
     * 运行配置
     */
    Run?: (MaaEndConfig_Run | null);
    /**
     * MaaEnd 配置
     */
    MaaEnd?: (MaaEndConfig_MaaEnd | null);
};
