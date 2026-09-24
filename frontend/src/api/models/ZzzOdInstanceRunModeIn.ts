/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 直控：设置运行实例（one_dragon.yml 全局 instance_run，与编辑所选实例无关）
 */
export type ZzzOdInstanceRunModeIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 运行实例取值（仅运行当前/全部实例；后端白名单校验，非法取值拒绝）
     */
    instanceRun: string;
};

