/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 配置组 json 详情（per-user 副本 → BGI 实配）
 */
export type BetterGIScriptGroupDetailOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 配置组 json 内容（含 name/index/config/projects，projects 为执行顺序）
     */
    data?: Record<string, any>;
};

