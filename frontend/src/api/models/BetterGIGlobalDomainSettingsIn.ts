/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 全局 config.json 的秘境刷取配置写入请求
 */
export type BetterGIGlobalDomainSettingsIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 要覆盖写入的秘境刷取配置键值（camelCase 扁平键）
     */
    settings?: Record<string, any>;
};
