/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 脚本仓库索引树节点（源自 BGI repo.json）。
 */
export type BetterGIScriptRepoNode = {
    /**
     * 节点名（目录名或文件名）
     */
    name: string;
    /**
     * 节点类型：directory / file
     */
    type?: string;
    /**
     * 仓库相对路径（订阅定位用）
     */
    path: string;
    /**
     * 版本
     */
    version?: string;
    /**
     * 作者
     */
    author?: string;
    /**
     * 描述
     */
    description?: string;
    /**
     * 标签
     */
    tags?: Array<string>;
    /**
     * 最近更新时间
     */
    lastUpdated?: string;
    /**
     * 子节点（仅目录）
     */
    children?: Array<BetterGIScriptRepoNode>;
};

