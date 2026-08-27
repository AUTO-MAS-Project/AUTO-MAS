/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWConfig_Info } from './MaaFWConfig_Info';
import type { MaaFWConfig_Run } from './MaaFWConfig_Run';
import type { MaaFWConfig_Selection } from './MaaFWConfig_Selection';
export type MaaFWConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (MaaFWConfig_Info | null);
    /**
     * 脚本运行配置
     */
    Run?: (MaaFWConfig_Run | null);
    /**
     * controller、resource 与 task 选择
     */
    Selection?: (MaaFWConfig_Selection | null);
};

