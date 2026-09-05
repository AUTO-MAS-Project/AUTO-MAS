/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 配置组 json 写入请求（保存到 per-user 副本，不触碰 BGI 同名实配）
 */
export type BetterGIScriptGroupSaveIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 所属用户ID
     */
    userId: string;
    /**
     * 配置组名（文件名）
     */
    name: string;
    /**
     * 要保存的完整配置组 json（projects 数组为新顺序与各项目设置）
     */
    data?: Record<string, any>;
};
