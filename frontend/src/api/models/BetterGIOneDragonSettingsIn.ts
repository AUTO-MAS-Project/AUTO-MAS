/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 一条龙设置项写入请求
 */
export type BetterGIOneDragonSettingsIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 所属用户ID
     */
    userId: string;
    /**
     * 一条龙配置名
     */
    configName: string;
    /**
     * 要覆盖写入的设置项（camelCase 键）
     */
    settings?: Record<string, any>;
};

