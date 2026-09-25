/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIScriptRepoCategory } from './BetterGIScriptRepoCategory';
/**
 * BetterGI 本地脚本仓库目录（解析自 repo.json 索引）。
 */
export type BetterGIScriptRepoCatalogOut = {
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
     * 本地仓库索引是否存在
     */
    repoExists?: boolean;
    /**
     * 索引时间
     */
    updateTime?: (string | null);
    /**
     * 分类键 -> 分类内容
     */
    categories?: Record<string, BetterGIScriptRepoCategory>;
};

