/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 秘境刷取配置写入请求（per-user 副本；userId 为空时直控 BGI 全局 config.json）
 */
export type BetterGIGlobalDomainSettingsIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 所属用户ID（空=写 BGI 全局实配）
     */
    userId?: (string | null);
    /**
     * 要覆盖写入的秘境刷取配置键值（camelCase 扁平键）
     */
    settings?: Record<string, any>;
};

