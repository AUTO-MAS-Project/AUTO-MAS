/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 幽境危战设置写入请求（per-user 副本；userId 为空时直控 BGI 全局 config.json）
 */
export type BetterGIGlobalStygianSettingsIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 所属用户ID（空=写 BGI 全局实配）
     */
    userId?: (string | null);
    /**
     * 右栏当前编辑的实例组名（形如 自动幽境危战-3；战斗4项按此做逐实例 Plan 路由，空则回落到基名）
     */
    groupName?: string;
    /**
     * 要覆盖写入的幽境危战设置键值（camelCase 扁平键）
     */
    settings?: Record<string, any>;
};

